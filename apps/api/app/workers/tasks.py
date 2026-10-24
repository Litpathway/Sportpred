import httpx
import redis
import sentry_sdk
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ml.features import features_for
from app.models.entities import AuditLog, Fixture, JobRun, Prediction, utcnow
from app.providers.api_football import RequestBudgetExceeded
from app.providers.booking import booking_provider
from app.providers.fixtures import ProviderFailure, fixture_provider
from app.services.analytics import drift_report, settle_results
from app.services.ingestion import sync_fixtures
from app.services.predictions import generate_predictions, latest_prediction_ids, refilter, train_and_register
from app.services.publication import build_slip, monitor_codes, publish_candidates
from app.workers.celery_app import celery

JOB_NAMES = {"sync", "odds", "enrich", "train", "predict", "filter", "slips", "publish", "settle", "monitor", "drift", "pipeline"}


def execute_job(name, db):
    settings = get_settings()
    if name in {"sync", "odds"}:
        # Feed contract includes timestamped odds, statistics and results; one
        # authorized request refreshes all three without unofficial endpoints.
        return sync_fixtures(db, fixture_provider(settings))
    if name == "enrich":
        history = list(db.scalars(select(Fixture).where(Fixture.status == "finished")))
        rows = list(db.scalars(select(Fixture).where(Fixture.status == "scheduled")))
        for fixture in rows:
            features = features_for(fixture, history, cutoff=utcnow())
            db.add(AuditLog(action="fixture.enriched", entity=str(fixture.id), detail={"quality": features.quality if features else 0,
                "status": "available" if features else "insufficient_data", "missing": features.detail["missing"] if features else ["history"]}))
        db.commit()
        return {"enriched": len(rows)}
    if name == "train":
        model = train_and_register(db)
        return {"id": model.id, "version": model.version, "approved": model.approved}
    if name == "predict":
        return generate_predictions(db)
    if name == "filter":
        return refilter(db)
    if name == "slips":
        rows = list(db.scalars(select(Prediction).where(Prediction.id.in_(latest_prediction_ids()), Prediction.eligible.is_(True)).order_by(Prediction.probability.desc())))
        count, seen = 0, set()
        for p in rows:
            if p.fixture_id in seen:
                continue
            try:
                build_slip(db, [p.id])
                seen.add(p.fixture_id)
                count += 1
            except ValueError:
                continue
        return {"candidates": count}
    if name == "publish":
        return publish_candidates(db, booking_provider(settings))
    if name == "settle":
        return settle_results(db)
    if name == "monitor":
        return monitor_codes(db, booking_provider(settings))
    if name == "drift":
        return drift_report(db)
    if name == "pipeline":
        return {stage: execute_job(stage, db) for stage in ("sync", "enrich", "settle", "predict", "filter", "slips", "publish", "monitor")}
    raise ValueError("Unknown job")


@celery.task(bind=True, name="sportpredict.run_job", max_retries=3, rate_limit="6/m")
def run_job(self, name: str):
    if name not in JOB_NAMES:
        raise ValueError("Unknown job")
    settings = get_settings()
    # All pipeline mutations share a lease; periodic and manually requested runs
    # cannot race. Domain unique constraints remain the second line of defense.
    client = redis.Redis.from_url(settings.redis_url)
    lock = client.lock("sportpredict:pipeline", timeout=900, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        return {"status": "busy"}
    key = f"{name}:{self.request.id}"
    try:
        with SessionLocal() as db:
            job = db.scalar(select(JobRun).where(JobRun.key == key))
            if job and job.status == "succeeded":
                return {"status": "already_completed"}
            if not job:
                job = JobRun(key=key, name=name, attempts=0)
                db.add(job)
            job.status, job.attempts = "running", job.attempts + 1
            db.commit()
            job_id = job.id
            try:
                result = execute_job(name, db)
                job = db.get(JobRun, job_id)
                job.status, job.finished_at = "succeeded", utcnow()
                db.execute(update(JobRun).where(JobRun.name == name, JobRun.status == "dead_letter",
                    JobRun.id != job_id).values(status="superseded"))
                db.commit()
                return result
            except Exception as exc:
                db.rollback()
                job = db.get(JobRun, job_id)
                if isinstance(exc, RequestBudgetExceeded):
                    job.status = "deferred"
                    job.error = str(exc)[:500]
                    job.finished_at = utcnow()
                    db.commit()
                    return {"status": "deferred", "reason": job.error}
                final = self.request.retries >= self.max_retries
                job.status = "dead_letter" if final else "retrying"
                job.error = (str(exc)[:500] if isinstance(exc, ProviderFailure) else type(exc).__name__)
                job.finished_at = utcnow()
                db.commit()
                if final:
                    sentry_sdk.capture_exception(exc)
                    if settings.alert_webhook_url:
                        try:
                            httpx.post(settings.alert_webhook_url, json={"event": "sportpredict.dead_letter", "job": name, "job_id": job_id}, timeout=5)
                        except httpx.HTTPError:
                            pass
                    raise
                raise self.retry(exc=RuntimeError(type(exc).__name__), countdown=min(300, 10 * 2 ** self.request.retries))
    finally:
        if lock.owned():
            lock.release()
