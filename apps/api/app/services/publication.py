import hashlib
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Prediction, Slip, utcnow
from app.models.entities import Fixture
from app.core.config import get_settings
from app.providers.booking import BookingProvider
from app.services.ingestion import platform_settings
from app.services.predictions import eligibility, latest_prediction_ids


def build_slip(db: Session, prediction_ids: list[int]) -> Slip:
    settings = platform_settings(db)
    if len(prediction_ids) != len(set(prediction_ids)) or not 1 <= len(prediction_ids) <= settings.max_legs:
        raise ValueError(f"Choose 1–{settings.max_legs} unique selections")
    predictions = [db.get(Prediction, i) for i in sorted(prediction_ids)]
    if any(p is None for p in predictions):
        raise ValueError("Prediction not found")
    if any(p.fixture.simulated != get_settings().demo_mode for p in predictions):
        raise ValueError("Selection is outside the current data environment")
    fixtures, teams, competitions = set(), set(), set()
    for p in predictions:
        reasons = eligibility(p, db)
        if reasons:
            raise ValueError(f"Selection {p.id} is ineligible: {', '.join(reasons)}")
        fixture = p.fixture
        if fixture.id in fixtures:
            raise ValueError("Conflicting or correlated selections from the same fixture")
        if teams.intersection((fixture.home_id, fixture.away_id)) or fixture.competition_id in competitions:
            raise ValueError("Multi-leg correlation control: repeated team or competition")
        fixtures.add(fixture.id)
        teams.update((fixture.home_id, fixture.away_id))
        competitions.add(fixture.competition_id)
    key = hashlib.sha256(("slip:v1:" + ",".join(map(str, sorted(prediction_ids)))).encode()).hexdigest()
    existing = db.scalar(select(Slip).where(Slip.idempotency_key == key))
    if existing:
        return existing
    odds = math.prod(p.odds for p in predictions) if all(p.odds for p in predictions) else None
    probability = predictions[0].probability if len(predictions) == 1 else None
    slip = Slip(idempotency_key=key, prediction_ids=sorted(prediction_ids), status="eligible",
        combined_odds=odds, joint_probability=probability,
        expected_value=(probability * odds - 1) if probability is not None and odds else None,
        assumption="Single selection; no joint independence assumption." if len(predictions) == 1 else
        "Joint probability and expected value withheld: cross-match independence has not been established.")
    db.add(slip)
    db.flush()
    db.add(AuditLog(action="slip.created", entity=str(slip.id), detail={"prediction_ids": prediction_ids}))
    db.commit()
    return slip


def publish_slip(db: Session, slip_id: int, provider: BookingProvider) -> Slip:
    # PostgreSQL row lock serializes concurrent verification/publication. Provider
    # receives the same idempotency key if a worker dies after an external request.
    slip = db.scalar(select(Slip).where(Slip.id == slip_id).with_for_update())
    if not slip:
        raise ValueError("Slip not found")
    if slip.status in {"published", "prediction_only", "expired", "cancelled"}:
        return slip
    if platform_settings(db).publication_paused:
        return slip
    predictions = [db.get(Prediction, i) for i in slip.prediction_ids]
    if any(p is None or eligibility(p, db) for p in predictions):
        slip.status = "cancelled"
        slip.failure_reason = "Eligibility changed before publication"
        db.commit()
        return slip
    slip.status = "pending_verification"
    slip.code_provider = provider.name
    selections = [{"prediction_id": p.id, "fixture_id": p.fixture_id, "provider_fixture_id": p.fixture.external_id,
                   "market": p.market, "decimal_odds": p.odds} for p in predictions]
    try:
        if any(p.fixture.simulated for p in predictions) and provider.genuine_capable:
            raise ValueError("Simulated selections cannot be sent to a genuine provider")
        code = provider.create_code(selections, slip.idempotency_key)
        if code:
            check = provider.validate_code(code)
            matching = sorted(check.selection_ids) == sorted(slip.prediction_ids)
            if provider.genuine_capable and check.valid and check.genuine and matching and not code.upper().startswith("MOCK-"):
                slip.code, slip.verified, slip.status = code, True, "published"
            else:
                slip.status = "prediction_only"
                slip.failure_reason = "Code is simulated, unverified, or selections do not match"
        else:
            slip.status = "prediction_only"
    except Exception as exc:
        # Do not persist provider response text: it may contain tokens or sensitive data.
        slip.status, slip.failure_reason = "prediction_only", f"Booking integration unavailable ({type(exc).__name__})"
    slip.published_at = utcnow()
    db.add(AuditLog(action="slip.published", entity=str(slip.id), detail={"status": slip.status, "verified": slip.verified, "provider": provider.name}))
    db.commit()
    return slip


def publish_candidates(db: Session, provider: BookingProvider) -> dict:
    candidates = list(db.scalars(select(Prediction).where(Prediction.id.in_(latest_prediction_ids()), Prediction.eligible.is_(True), Prediction.outcome == "pending", Prediction.fixture.has(Fixture.simulated == get_settings().demo_mode))
                                .order_by(Prediction.probability.desc(), Prediction.id)))
    seen, published = set(), 0
    for p in candidates:
        if p.fixture_id in seen or eligibility(p, db):
            continue
        seen.add(p.fixture_id)
        slip = build_slip(db, [p.id])
        before = slip.status
        slip = publish_slip(db, slip.id, provider)
        published += int(before not in {"published", "prediction_only"} and slip.status in {"published", "prediction_only"})
    return {"published": published}


def monitor_codes(db: Session, provider: BookingProvider) -> dict:
    changed = 0
    for slip in db.scalars(select(Slip).where(Slip.status.in_(["published", "prediction_only"]))):
        predictions = [db.get(Prediction, i) for i in slip.prediction_ids]
        if any(p.fixture.status in {"cancelled", "postponed"} for p in predictions):
            slip.status = "cancelled"
        elif any(p.fixture.kickoff <= utcnow() for p in predictions):
            slip.status = "expired"
        elif slip.verified and slip.code and provider.name == slip.code_provider:
            try:
                status = provider.get_code_status(slip.code)
                if status in {"expired", "cancelled"}:
                    slip.status = status
            except Exception:
                db.add(AuditLog(action="code.monitor_unavailable", entity=str(slip.id)))
        else:
            continue
        changed += 1
        db.add(AuditLog(action="slip.monitored", entity=str(slip.id), detail={"status": slip.status}))
    db.commit()
    return {"changed": changed}
