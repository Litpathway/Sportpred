from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models.entities import AuditLog, Competition, Fixture, Prediction, Slip, Team, utcnow
from app.providers.booking import CodeValidation, MockBookingProvider, UnavailableBookingProvider
from app.services.analytics import performance, settle_results
from app.services.ingestion import platform_settings
from app.services.predictions import eligibility, refilter
from app.services.publication import build_slip, monitor_codes, publish_candidates, publish_slip


def test_79_percent_fails_80_percent_filter(db, selection):
    selection.probability = .79
    assert "below_probability_threshold" in eligibility(selection, db)
    selection.probability = .8
    assert eligibility(selection, db) == []


def test_poor_quality_rejected_even_above_threshold(db, selection):
    selection.probability, selection.quality = .96, .4
    assert "poor_data_quality" in eligibility(selection, db)
    with pytest.raises(ValueError, match="poor_data_quality"):
        build_slip(db, [selection.id])


@pytest.mark.parametrize("change,reason", [
    ("approval", "model_not_approved"), ("status", "fixture_not_upcoming"),
    ("odds", "stale_or_missing_odds"), ("freshness", "stale_fixture_data"),
    ("domain", "model_data_domain_mismatch"), ("temporal", "model_temporal_leakage"),
])
def test_eligibility_guards(db, selection, change, reason):
    if change == "approval": selection.model.approved = False
    if change == "status": selection.fixture.status = "live"
    if change == "odds": selection.odds_at = utcnow() - timedelta(hours=1)
    if change == "freshness": selection.fixture.synced_at = utcnow() - timedelta(days=1)
    if change == "domain": selection.model.simulated = True
    if change == "temporal": selection.model.trained_until = selection.fixture.kickoff
    assert reason in eligibility(selection, db)


def test_fake_code_cannot_publish_as_verified(db, selection):
    slip = build_slip(db, [selection.id])
    result = publish_slip(db, slip.id, MockBookingProvider())
    assert result.status == "prediction_only"
    assert not result.verified and result.code is None


def test_provider_outage_falls_back_to_prediction_only(db, selection):
    class Offline(UnavailableBookingProvider):
        def create_code(self, selections, idempotency_key):
            raise ConnectionError("provider unreachable")
    slip = publish_slip(db, build_slip(db, [selection.id]).id, Offline())
    assert slip.status == "prediction_only" and slip.published_at and not slip.verified


def test_retries_do_not_duplicate_publications_or_request_codes_twice(db, selection):
    class Counting(UnavailableBookingProvider):
        calls = 0
        def create_code(self, selections, idempotency_key):
            self.calls += 1
            return None
    provider = Counting()
    for _ in range(3):
        publish_candidates(db, provider)
    assert db.scalar(select(func.count()).select_from(Slip)) == 1
    assert provider.calls == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "slip.published")) == 1


def test_authorized_code_requires_exact_selection_verification(db, selection):
    class Authorized(UnavailableBookingProvider):
        name, genuine_capable = "authorized-test", True
        def create_code(self, selections, idempotency_key): return "VERIFIED-TEST-ONLY"
        def validate_code(self, code): return CodeValidation(True, True, (selection.id,))
    slip = publish_slip(db, build_slip(db, [selection.id]).id, Authorized())
    assert slip.status == "published" and slip.verified


def test_wrong_selections_reject_genuine_code(db, selection):
    class Wrong(UnavailableBookingProvider):
        genuine_capable = True
        def create_code(self, selections, idempotency_key): return "WRONG-TEST-ONLY"
        def validate_code(self, code): return CodeValidation(True, True, (99999,))
    slip = publish_slip(db, build_slip(db, [selection.id]).id, Wrong())
    assert not slip.verified and slip.status == "prediction_only"


def test_simulated_selections_never_sent_to_genuine_provider(db, selection, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    selection.fixture.simulated = selection.model.simulated = True
    class Genuine(UnavailableBookingProvider):
        genuine_capable = True
        def create_code(self, selections, idempotency_key):
            pytest.fail("Simulated data sent to genuine provider")
    slip = publish_slip(db, build_slip(db, [selection.id]).id, Genuine())
    assert slip.status == "prediction_only" and not slip.verified


def test_publication_pause_and_revoked_approval(db, selection):
    slip = build_slip(db, [selection.id])
    platform_settings(db).publication_paused = True
    db.commit()
    assert publish_slip(db, slip.id, UnavailableBookingProvider()).published_at is None
    platform_settings(db).publication_paused = False
    selection.model.approved = False
    db.commit()
    assert publish_slip(db, slip.id, UnavailableBookingProvider()).status == "cancelled"


def test_single_slip_probability_and_ev(db, selection):
    slip = build_slip(db, [selection.id])
    assert slip.joint_probability == .85
    assert slip.combined_odds == 1.2
    assert slip.expected_value == pytest.approx(.85 * 1.2 - 1)
    assert build_slip(db, [selection.id]).id == slip.id


def test_duplicate_selections_rejected(db, selection):
    platform_settings(db).max_legs = 3
    with pytest.raises(ValueError, match="unique"):
        build_slip(db, [selection.id, selection.id])


def test_conflicting_markets_same_fixture_rejected(db, selection):
    platform_settings(db).max_legs = 3
    other = Prediction(fixture=selection.fixture, model=selection.model, market="over_2_5", probability=.82,
        raw_probability=.83, quality=.85, odds=1.5, odds_at=utcnow(), features={}, explanation="test", created_at=utcnow())
    db.add(other); db.commit()
    with pytest.raises(ValueError, match="same fixture"):
        build_slip(db, [selection.id, other.id])


def test_multi_match_joint_probability_is_withheld(db, selection):
    platform_settings(db).max_legs = 3
    teams = [Team(name=name, identity=name, country="Other") for name in ("Other home", "Other away")]
    comp = Competition(name="Other competition", identity="other", country="Other")
    db.add_all([*teams, comp]); db.flush()
    f = Fixture(provider="test", external_id="two", competition_id=comp.id, home_id=teams[0].id, away_id=teams[1].id,
                kickoff=selection.fixture.kickoff, status="scheduled", simulated=False, synced_at=utcnow())
    p = Prediction(fixture=f, model=selection.model, market="home_win", probability=.83, raw_probability=.85,
                   quality=.85, odds=1.3, odds_at=utcnow(), features={}, explanation="test", created_at=utcnow())
    db.add(p); db.commit()
    slip = build_slip(db, [selection.id, p.id])
    assert slip.joint_probability is None and slip.expected_value is None
    assert slip.combined_odds == pytest.approx(1.2 * 1.3)


@pytest.mark.parametrize("score,outcome", [((2, 0), "won"), ((0, 2), "lost"), ((1, 1), "won")])
def test_completed_match_settles_correctly_and_once(db, selection, score, outcome):
    selection.fixture.status = "finished"
    selection.fixture.home_goals, selection.fixture.away_goals = score
    db.commit()
    assert settle_results(db)["settled"] == 1
    assert selection.outcome == outcome
    assert settle_results(db)["settled"] == 0
    metrics = performance(db, simulated=False)
    assert metrics[outcome] == 1 and metrics["total"] == 1


def test_cancelled_match_void_and_code_expires(db, selection):
    slip = publish_slip(db, build_slip(db, [selection.id]).id, UnavailableBookingProvider())
    selection.fixture.status = "cancelled"
    settle_results(db); monitor_codes(db, UnavailableBookingProvider())
    assert selection.outcome == "void" and slip.status == "cancelled"


def test_no_wager_or_funds_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(word in p for p in paths for word in ("stake", "deposit", "withdraw", "wager", "place-bet"))
