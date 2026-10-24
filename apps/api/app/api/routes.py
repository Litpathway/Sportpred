from datetime import timedelta
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.leagues import EUROPEAN_LEAGUES
from app.core.security import DUMMY_HASH, administrator, issue_token, login_identity, operator, password_hasher, reader
from app.db.session import get_db
from app.models.entities import AuditLog, Competition, Fixture, JobRun, LoginAttempt, ModelVersion, Prediction, Slip, Team, User, utcnow
from app.schemas.contracts import ApprovalInput, ClearDataInput, LoginInput, MARKET_LABELS, SettingsInput, SlipInput
from app.services.analytics import performance
from app.services.ingestion import platform_settings
from app.services.predictions import latest_prediction_ids, refilter
from app.services.publication import build_slip
from app.services.csv_training import import_training_csv

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]


def stamp(value):
    return value.isoformat() + "Z" if value else None


def team_logo(team: Team, provider: str) -> str | None:
    """Use the badge URL for a team identity supplied by API-Football only."""
    prefix = "api-football:team:"
    if provider != "api_football" or not team.identity.startswith(prefix):
        return None
    external_id = team.identity.removeprefix(prefix)
    if not external_id.isdigit():
        return None
    return f"https://media.api-sports.io/football/teams/{external_id}.png"


def fixture_json(f: Fixture) -> dict:
    return {"id": f.id, "home": f.home.name, "away": f.away.name, "competition": f.competition.name,
            "home_logo": team_logo(f.home, f.provider), "away_logo": team_logo(f.away, f.provider),
            "country": f.competition.country, "league_slug": f.competition.league_slug,
            "kickoff": stamp(f.kickoff), "status": f.status, "simulated": f.simulated,
            "home_goals": f.home_goals, "away_goals": f.away_goals, "synced_at": stamp(f.synced_at),
            "odds": f.odds or {}, "odds_at": stamp(f.odds_at), "enrichment": f.enrichment,
            "provenance": f.enrichment.get("provenance", {}), "provider": f.provider}


def prediction_json(p: Prediction) -> dict:
    return {"id": p.id, "fixture": fixture_json(p.fixture), "market": p.market, "market_label": MARKET_LABELS.get(p.market, p.market),
            "probability": p.probability, "raw_probability": p.raw_probability, "quality": p.quality,
            "odds": p.odds, "eligible": p.eligible, "reasons": p.reasons, "outcome": p.outcome,
            "explanation": p.explanation, "features": p.features, "created_at": stamp(p.created_at),
            "model": p.model.version, "model_approved": p.model.approved, "generation": p.generation}


def slip_json(s: Slip, db: Session) -> dict:
    predictions = [db.get(Prediction, i) for i in s.prediction_ids]
    return {"id": s.id, "status": s.status, "joint_probability": s.joint_probability, "combined_odds": s.combined_odds,
            "expected_value": s.expected_value, "assumption": s.assumption, "code": s.code if s.verified else None,
            "verified": s.verified, "provider": s.code_provider, "published_at": stamp(s.published_at),
            "predictions": [prediction_json(p) for p in predictions if p], "failure_reason": s.failure_reason}


def model_json(m: ModelVersion) -> dict:
    return {"id": m.id, "version": m.version, "approved": m.approved, "simulated": m.simulated,
            "trained_until": stamp(m.trained_until), "created_at": stamp(m.created_at), "metrics": m.metrics}


def slip_in_current_domain(s: Slip, db: Session) -> bool:
    predictions = [db.get(Prediction, i) for i in s.prediction_ids]
    return bool(predictions) and all(p and p.fixture.simulated == get_settings().demo_mode for p in predictions)


@router.get("/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "SportPredict AI", "demo_mode": get_settings().demo_mode}


@router.get("/overview")
def overview(db: DB):
    settings = platform_settings(db)
    db.commit()
    now = utcnow()
    domain = get_settings().demo_mode
    upcoming = db.scalar(select(func.count()).select_from(Fixture).where(Fixture.simulated == domain, Fixture.status == "scheduled", Fixture.kickoff > now))
    eligible = db.scalar(select(func.count()).select_from(Prediction).where(Prediction.id.in_(latest_prediction_ids()), Prediction.eligible.is_(True), Prediction.fixture.has(Fixture.kickoff > now), Prediction.fixture.has(Fixture.simulated == domain)))
    model = db.scalar(select(ModelVersion).where(ModelVersion.simulated == domain).order_by(ModelVersion.created_at.desc()))
    return {"upcoming_matches": upcoming, "eligible_predictions": eligible,
            "verified_codes": sum(slip_in_current_domain(s, db) for s in db.scalars(select(Slip).where(Slip.verified.is_(True), Slip.status == "published"))),
            "competitions": db.scalar(select(func.count(func.distinct(Fixture.competition_id))).where(Fixture.simulated == domain)), "threshold": settings.threshold,
            "demo_mode": get_settings().demo_mode, "publication_paused": settings.publication_paused,
            "data_mode": "demo" if domain else "personal_research" if get_settings().fixture_provider == "sports_skills" else "authorized_feed",
            "model": model_json(model) if model else None, "performance": performance(db)}


@router.get("/fixtures")
def fixtures(db: DB, q: str = Query(default="", max_length=100), competition: str = "", status: str = "scheduled",
             limit: int = Query(default=40, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    query = select(Fixture).where(Fixture.simulated == get_settings().demo_mode).order_by(Fixture.kickoff)
    if status != "all":
        query = query.where(Fixture.status == status)
    if q:
        query = query.where(or_(Fixture.home.has(Team.name.ilike(f"%{q}%")), Fixture.away.has(Team.name.ilike(f"%{q}%"))))
    if competition:
        query = query.where(Fixture.competition.has(Competition.name == competition))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {"items": [fixture_json(f) for f in db.scalars(query.limit(limit).offset(offset))], "total": total}


@router.get("/competitions")
def competitions(db: DB):
    ids = select(Fixture.competition_id).where(Fixture.simulated == get_settings().demo_mode).distinct()
    return [{"id": c.id, "name": c.name, "country": c.country} for c in db.scalars(select(Competition).where(Competition.id.in_(ids)).order_by(Competition.name))]


@router.get("/league-coverage")
def league_coverage(db: DB):
    # A configured league is not a claim that its provider coverage is complete.
    counts = dict(db.execute(select(Competition.league_slug, func.count(Fixture.id)).join(Fixture)
        .where(Fixture.simulated.is_(False)).group_by(Competition.league_slug)).all())
    return [{"slug": slug, **EUROPEAN_LEAGUES[slug], "fixtures": counts.get(slug, 0),
             "status": "data_received" if counts.get(slug, 0) else "awaiting_feed"}
            for slug in get_settings().league_slugs]


@router.get("/fixtures/{fixture_id}")
def fixture_detail(fixture_id: int, db: DB):
    fixture = db.get(Fixture, fixture_id)
    if not fixture or fixture.simulated != get_settings().demo_mode:
        raise HTTPException(404, "Match not found")
    from app.ml.features import features_for
    history = list(db.scalars(select(Fixture).where(Fixture.status == "finished")))
    evidence = features_for(fixture, history, cutoff=utcnow()) if fixture.status == "scheduled" else None
    return {"fixture": fixture_json(fixture), "predictions": [prediction_json(p) for p in db.scalars(
        select(Prediction).where(Prediction.fixture_id == fixture_id, Prediction.id.in_(latest_prediction_ids())).order_by(Prediction.probability.desc()))],
        "evidence": evidence.detail if evidence else None,
        "data_status": "available" if db.scalar(select(Prediction.id).where(Prediction.fixture_id == fixture_id).limit(1)) else "insufficient_data"}


@router.get("/predictions")
def predictions(db: DB, high_confidence: bool = False, latest_only: bool = True, best_per_match: bool = False,
                q: str = Query(default="", max_length=100), market: str = "",
                outcome: str = "", competition: str = "", limit: int = Query(default=40, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    query = select(Prediction).join(Fixture).where(Fixture.simulated == get_settings().demo_mode).order_by(Prediction.probability.desc(), Prediction.id)
    if latest_only:
        query = query.where(Prediction.id.in_(latest_prediction_ids()))
    if high_confidence:
        query = query.where(Prediction.id.in_(latest_prediction_ids()), Prediction.eligible.is_(True), Fixture.status == "scheduled", Fixture.kickoff > utcnow(),
                            Prediction.odds_at >= utcnow() - timedelta(minutes=30), Prediction.created_at >= utcnow() - timedelta(hours=6),
                            Prediction.model.has(ModelVersion.approved.is_(True)))
    if market:
        query = query.where(Prediction.market == market)
    if outcome:
        query = query.where(Prediction.outcome == outcome)
    if competition:
        query = query.where(Fixture.competition.has(Competition.name == competition))
    if q:
        from app.models.entities import Team
        query = query.where(or_(Fixture.home.has(Team.name.ilike(f"%{q}%")), Fixture.away.has(Team.name.ilike(f"%{q}%"))))
    if best_per_match:
        ranked = query.add_columns(func.row_number().over(
            partition_by=Prediction.fixture_id,
            order_by=(Prediction.probability.desc(), Prediction.id.desc()),
        ).label("match_rank")).subquery()
        query = select(Prediction).join(ranked, ranked.c.id == Prediction.id).where(ranked.c.match_rank == 1)
        query = query.order_by(Prediction.probability.desc(), Prediction.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {"items": [prediction_json(p) for p in db.scalars(query.limit(limit).offset(offset))], "total": total}


@router.get("/slips")
def slips(db: DB, verified_only: bool = False, limit: int = Query(default=40, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    query = select(Slip).where(Slip.published_at.is_not(None)).order_by(Slip.published_at.desc())
    if verified_only:
        query = query.where(Slip.verified.is_(True), Slip.status == "published")
    rows = [s for s in db.scalars(query) if slip_in_current_domain(s, db)]
    return {"items": [slip_json(s, db) for s in rows[offset:offset + limit]], "total": len(rows)}


@router.get("/slips/{slip_id}")
def slip_detail(slip_id: int, db: DB):
    slip = db.get(Slip, slip_id)
    if not slip or not slip.published_at or not slip_in_current_domain(slip, db):
        raise HTTPException(404, "Publication not found")
    return slip_json(slip, db)


@router.get("/performance")
def performance_route(db: DB):
    return performance(db)


@router.post("/auth/login")
def login(payload: LoginInput, request: Request, response: Response, db: DB):
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().origins:
        raise HTTPException(403, "Origin not allowed")
    identity = login_identity(request, payload.email)
    cutoff = utcnow() - timedelta(minutes=15)
    count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.identity == identity, LoginAttempt.created_at > cutoff))
    if count >= 8:
        raise HTTPException(429, "Too many sign-in attempts; try again in 15 minutes")
    db.add(LoginAttempt(identity=identity))
    db.commit()
    user = db.scalar(select(User).where(User.email == payload.email.strip().casefold()))
    valid = password_hasher.verify(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not user.active or not valid:
        raise HTTPException(401, "Invalid email or password")
    token, csrf = issue_token(user)
    response.set_cookie("sp_session", token, httponly=True, secure=get_settings().cookie_secure, samesite="strict", max_age=get_settings().token_minutes * 60, path="/")
    db.add(AuditLog(action="auth.login", actor=user.email, entity=str(user.id)))
    db.commit()
    return {"email": user.email, "role": user.role, "csrf_token": csrf}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(reader)):
    import jwt
    claims = jwt.decode(request.cookies["sp_session"], get_settings().jwt_secret, algorithms=["HS256"],
                        issuer="sportpredict", audience="sportpredict-admin")
    return {"email": user.email, "role": user.role, "csrf_token": claims["csrf"]}


@router.post("/auth/logout")
def logout(response: Response, user: User = Depends(reader)):
    response.delete_cookie("sp_session", path="/")
    return {"ok": True}


@router.get("/admin/overview")
def admin_overview(db: DB, user: User = Depends(reader)):
    return {**overview(db), "user": {"email": user.email, "role": user.role},
            "failed_jobs": db.scalar(select(func.count()).select_from(JobRun).where(JobRun.status == "dead_letter")),
            "settings": settings_read(db, user)}


@router.delete("/admin/data")
def clear_platform_data(payload: ClearDataInput, db: DB, user: User = Depends(administrator)):
    # Coordinate with the worker's shared pipeline lease so a running sync or
    # prediction job cannot repopulate rows while the reset transaction runs.
    lock = redis.Redis.from_url(get_settings().redis_url).lock(
        "sportpredict:pipeline", timeout=900, blocking_timeout=0
    )
    try:
        acquired = lock.acquire(blocking=False)
    except redis.RedisError:
        raise HTTPException(503, "Reset unavailable while the background queue is unreachable") from None
    if not acquired:
        raise HTTPException(409, "A background job is running. Wait for it to finish, then clear data.")
    try:
        deleted = {}
        for key, model in (("slips", Slip), ("predictions", Prediction), ("fixtures", Fixture),
                           ("models", ModelVersion), ("teams", Team), ("competitions", Competition),
                           ("background_jobs", JobRun), ("audit_events", AuditLog)):
            result = db.execute(delete(model).execution_options(synchronize_session=False))
            deleted[key] = max(0, result.rowcount or 0)
        db.add(AuditLog(action="data.cleared", actor=user.email, entity="platform", detail={"deleted": deleted}))
        db.commit()
        return {"status": "cleared", "deleted": deleted, "preserved": ["users", "platform_settings", "login_attempts"]}
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            if lock.owned():
                lock.release()
        except redis.RedisError:
            pass


@router.get("/admin/settings")
def settings_read(db: DB, user: User = Depends(reader)):
    settings = platform_settings(db)
    db.commit()
    return {key: getattr(settings, key) for key in SettingsInput.model_fields}


@router.put("/admin/settings")
def settings_update(payload: SettingsInput, db: DB, user: User = Depends(administrator)):
    settings = platform_settings(db)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    db.add(AuditLog(action="settings.updated", actor=user.email, entity="platform", detail=payload.model_dump()))
    db.commit()
    refilter(db)
    return settings_read(db, user)


@router.get("/admin/models")
def models(db: DB, user: User = Depends(reader)):
    return [model_json(m) for m in db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()))]


@router.post("/admin/training-data/csv")
async def upload_training_csv(file: UploadFile, db: DB, user: User = Depends(administrator)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(422, "Choose a .csv file")
    content = await file.read(3_000_001)
    if len(content) > 3_000_000:
        raise HTTPException(413, "CSV must be 3 MB or smaller")
    try:
        result = import_training_csv(db, content, file.filename, user.email)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return result


@router.put("/admin/models/{model_id}/approval")
def model_approval(model_id: int, payload: ApprovalInput, db: DB, user: User = Depends(administrator)):
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    if model.simulated and not get_settings().demo_mode and payload.approved:
        raise HTTPException(422, "Simulated models cannot be approved for live mode")
    model.approved = payload.approved
    db.add(AuditLog(action="model.approval", actor=user.email, entity=str(model.id), detail=payload.model_dump()))
    db.commit()
    refilter(db)
    return model_json(model)


@router.get("/admin/providers")
def providers(db: DB, user: User = Depends(reader)):
    last_sync = db.scalar(select(AuditLog).where(AuditLog.action == "fixtures.synced").order_by(AuditLog.id.desc()))
    settings = get_settings()
    recent_failures = list(db.scalars(select(JobRun).where(JobRun.status == "dead_letter").order_by(JobRun.id.desc()).limit(5)))
    api_football = {"configured": settings.fixture_provider == "api_football", "key_present": bool(settings.api_football_key),
        "daily_budget": settings.api_football_daily_budget, "pipeline_interval_minutes": settings.pipeline_interval_minutes,
        "account": None, "last_warnings": last_sync.detail.get("warnings", []) if last_sync else []}
    sportybet_odds = {"enabled": settings.sportybet_odds_enabled, "region": settings.sportybet_region.upper(),
                      "status": "disabled" if not settings.sportybet_odds_enabled else "waiting_for_sync"}
    if settings.fixture_provider == "api_football" and settings.api_football_key:
        from app.providers.api_football import RedisApiCache
        from app.providers.fixtures import ProviderFailure
        try:
            cache = RedisApiCache(settings.redis_url, settings.api_football_key.get_secret_value())
            api_football["account"] = cache.get("status_summary")
            latest = cache.get("sync_status")
            if latest:
                api_football["last_warnings"] = latest.get("warnings", [])
            api_football["last_error"] = cache.get("last_error")
            sportybet_odds["sync"] = cache.get("sportybet:sync_status")
        except ProviderFailure:
            api_football["cache_status"] = "unavailable"
    return {"fixtures": {"name": settings.fixture_provider, "enabled": platform_settings(db).provider_enabled,
            "last_sync": stamp(last_sync.created_at) if last_sync else None,
            "status": "never_synced" if not last_sync else "fresh" if last_sync.created_at > utcnow() - timedelta(hours=6) else "stale"},
            "booking": {"name": settings.booking_provider, "genuine_enabled": settings.booking_provider == "authorized" and bool(settings.booking_api_url and settings.booking_api_token) and not settings.demo_mode},
            "recent_failure_count": len(recent_failures),
            "api_football": api_football,
            "sportybet_odds": sportybet_odds,
            "sports_skills": {"configured": settings.fixture_provider == "sports_skills", "personal_use_opt_in": settings.sports_skills_personal_use,
                "production_allowed": False, "competitions": settings.sports_skills_competitions.split(","),
                "source_commit": "bdb972c0625fa337e15f18ca58abd28f57f25e37", "history_enabled": settings.sports_skills_history}}


@router.get("/admin/jobs")
def jobs(db: DB, user: User = Depends(reader)):
    return [{"id": j.id, "key": j.key, "name": j.name, "status": j.status, "attempts": j.attempts,
             "error": j.error, "started_at": stamp(j.started_at), "finished_at": stamp(j.finished_at)}
            for j in db.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(100))]


@router.post("/admin/jobs/{name}")
def trigger_job(name: str, db: DB, user: User = Depends(operator)):
    from app.workers.tasks import JOB_NAMES, run_job
    if name not in JOB_NAMES:
        raise HTTPException(404, "Unknown job")
    try:
        task = run_job.delay(name)
    except Exception:
        raise HTTPException(503, "Worker queue unavailable; check Redis and worker health") from None
    db.add(AuditLog(action="job.requested", actor=user.email, entity=name, detail={"task_id": task.id}))
    db.commit()
    return {"task_id": task.id, "status": "queued"}


@router.post("/admin/slips")
def create_slip(payload: SlipInput, db: DB, user: User = Depends(operator)):
    try:
        slip = build_slip(db, payload.prediction_ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return slip_json(slip, db)


@router.get("/admin/slips")
def admin_slips(db: DB, user: User = Depends(reader)):
    return [slip_json(s, db) for s in db.scalars(select(Slip).order_by(Slip.id.desc()).limit(100))]


@router.get("/admin/audit")
def audit(db: DB, user: User = Depends(reader)):
    return [{"id": a.id, "action": a.action, "actor": a.actor, "entity": a.entity, "detail": a.detail, "created_at": stamp(a.created_at)}
            for a in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100))]
