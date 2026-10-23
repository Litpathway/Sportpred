import hashlib
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ml.engine import InsufficientData, deserialize_artifact, load_artifact, predict, serialize_artifact, train_model
from app.ml.features import features_for
from app.models.entities import AuditLog, Fixture, ModelVersion, Prediction, utcnow
from app.schemas.contracts import MARKETS, MARKET_LABELS
from app.services.ingestion import platform_settings


def latest_prediction_ids():
    return select(func.max(Prediction.id)).group_by(Prediction.fixture_id, Prediction.market)


def prediction_generation(model_id: int, fixture: Fixture, market: str, features, odds: float | None) -> str:
    # Ignore the prediction timestamp and small rest-day drift. A new snapshot
    # is created only when match history, meaningful model inputs, or the quote
    # actually changes; repeating the job with the same evidence stays idempotent.
    values = {key: round(value, 4) for key, value in features.detail["values"].items()
              if key not in {"home_rest", "away_rest"}}
    identity = {
        "model": model_id,
        "fixture": fixture.id,
        "market": market,
        "history": features.detail["history_ids"],
        "values": values,
        "quality": round(features.quality, 4),
        "missing": sorted(features.detail["missing"]),
        "home_form": features.detail["home_form"],
        "away_form": features.detail["away_form"],
        "odds": odds,
        "odds_at": fixture.odds_at.isoformat() if fixture.odds_at else None,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()[:40]


def train_and_register(db: Session) -> ModelVersion:
    settings = get_settings()
    history = list(db.scalars(select(Fixture).where(Fixture.status == "finished").order_by(Fixture.kickoff)))
    fingerprint = hashlib.sha256(json.dumps([(f.id, f.kickoff.isoformat(), f.home_goals, f.away_goals,
        f.result_known_at.isoformat() if f.result_known_at else None) for f in history], separators=(",", ":")).encode()).hexdigest()[:16]
    version = f"ensemble-v1-{'demo' if settings.demo_mode else 'live'}-{fingerprint}"
    existing = db.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if existing and existing.artifact_data is not None:
        return existing
    artifact, metrics = train_model(history, simulated=settings.demo_mode)
    data = serialize_artifact(artifact)
    metrics["sha256"] = hashlib.sha256(data).hexdigest()
    if settings.mlflow_tracking_uri:
        import mlflow
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment("sportpredict")
        with mlflow.start_run(run_name=version):
            mlflow.log_params({"seed": 42, "simulated": settings.demo_mode, "split": "chronological-60-20-20"})
            mlflow.log_metrics({"test_brier": metrics["brier"], "test_log_loss": metrics["log_loss"]})
            mlflow.log_dict(metrics, "evaluation.json")
    record = existing or ModelVersion(version=version, simulated=settings.demo_mode)
    record.artifact_path, record.artifact_data = f"database://{version}", data
    record.metrics, record.trained_until, record.approved = metrics, artifact["trained_until"], False
    db.add(record)
    db.add(AuditLog(action="model.trained", entity=version, detail={"fingerprint": fingerprint}))
    db.commit()
    return record


def eligibility(prediction: Prediction, db: Session, now=None) -> list[str]:
    now = now or utcnow()
    settings = platform_settings(db)
    reasons = []
    if prediction.probability < settings.threshold:
        reasons.append("below_probability_threshold")
    if prediction.quality < settings.min_quality:
        reasons.append("poor_data_quality")
    if not prediction.model.approved:
        reasons.append("model_not_approved")
    if prediction.model.simulated != prediction.fixture.simulated:
        reasons.append("model_data_domain_mismatch")
    if prediction.model.trained_until >= prediction.fixture.kickoff:
        reasons.append("model_temporal_leakage")
    if prediction.market not in MARKETS:
        reasons.append("unsupported_market")
    if prediction.fixture.status != "scheduled" or prediction.fixture.kickoff <= now:
        reasons.append("fixture_not_upcoming")
    if prediction.fixture.synced_at < now - timedelta(hours=6):
        reasons.append("stale_fixture_data")
    if not prediction.odds or not prediction.odds_at or not now - timedelta(minutes=30) <= prediction.odds_at <= now:
        reasons.append("stale_or_missing_odds")
    if prediction.created_at > now or prediction.created_at < now - timedelta(hours=6):
        reasons.append("stale_prediction")
    return reasons


def refilter(db: Session) -> dict:
    rows = list(db.scalars(select(Prediction).where(Prediction.outcome == "pending")))
    for p in rows:
        # Quotes are part of the immutable prediction snapshot. New scheduled
        # inference creates a new snapshot instead of rewriting historical ROI.
        p.reasons = eligibility(p, db)
        p.eligible = not p.reasons
        db.add(AuditLog(action="prediction.eligibility", entity=str(p.id), detail={"eligible": p.eligible, "reasons": p.reasons}))
    db.commit()
    return {"checked": len(rows), "eligible": sum(p.eligible for p in rows)}


def generate_predictions(db: Session) -> dict:
    model = db.scalar(select(ModelVersion).where(ModelVersion.approved.is_(True), ModelVersion.simulated == get_settings().demo_mode).order_by(ModelVersion.created_at.desc()))
    if not model:
        return {"status": "insufficient_data", "reason": "No approved model", "created": 0}
    if model.artifact_data is not None:
        artifact = deserialize_artifact(model.artifact_data, model.metrics["sha256"])
    elif model.artifact_path.startswith("database://"):
        return {"status": "insufficient_data", "reason": "Model artifact unavailable", "created": 0}
    else:
        # Existing local installations retain compatibility; retraining moves
        # new versions into durable storage shared by API and worker instances.
        artifact = load_artifact(Path(model.artifact_path), model.metrics["sha256"])
    history = list(db.scalars(select(Fixture).where(Fixture.status == "finished")))
    upcoming = list(db.scalars(select(Fixture).where(Fixture.status == "scheduled", Fixture.kickoff > utcnow(), Fixture.simulated == model.simulated)))
    existing = {(p.fixture_id, p.generation) for p in db.scalars(
        select(Prediction).where(Prediction.model_id == model.id, Prediction.fixture_id.in_([f.id for f in upcoming]))
    )} if upcoming else set()
    created, insufficient = 0, []
    for fixture in upcoming:
        # Use current time rather than kickoff: future lineup/result information is excluded.
        features = features_for(fixture, history, cutoff=utcnow())
        if not features or model.trained_until >= utcnow():
            insufficient.append(fixture.id)
            db.add(AuditLog(action="prediction.insufficient_data", entity=str(fixture.id), detail={"reason": "Insufficient prior history or model cutoff"}))
            continue
        for market, (calibrated, raw) in predict(artifact, features.values).items():
            odds = fixture.odds.get(market)
            generation = prediction_generation(model.id, fixture, market, features, odds)
            if (fixture.id, generation) in existing:
                continue
            p = Prediction(fixture=fixture, model=model, market=market, generation=generation, probability=calibrated, raw_probability=raw,
                quality=features.quality, odds=odds, odds_at=fixture.odds_at,
                features=features.detail, created_at=utcnow(), outcome="pending",
                explanation=f"{MARKET_LABELS[market]} from a calibrated Poisson/XGBoost ensemble. "
                f"Home averages {features.values[0]:.2f} goals scored; away averages {features.values[4]:.2f}. "
                f"Uses {features.detail['home_matches']} home-team and {features.detail['away_matches']} away-team prior matches. "
                f"Missing optional inputs: {', '.join(features.detail['missing']) or 'none'}. "
                "The baseline uses historical form; feed enrichment remains contextual.")
            db.add(p)
            db.flush()
            existing.add((fixture.id, generation))
            p.reasons = eligibility(p, db)
            p.eligible = not p.reasons
            db.add(AuditLog(action="prediction.generated", entity=str(p.id), detail={"model": model.version, "reasons": p.reasons, "feature_as_of": features.detail["as_of"]}))
            created += 1
    db.commit()
    return {"status": "ok", "created": created, "insufficient_fixture_ids": insufficient}
