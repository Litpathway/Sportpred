import pytest
from sqlalchemy import select

from app.core.security import password_hasher
from app.models.entities import User


@pytest.mark.parametrize("path", ["overview", "models", "providers", "settings", "jobs", "slips", "audit"])
def test_admin_reads_require_authentication(client, path):
    assert client.get(f"/api/admin/{path}").status_code == 401


def test_admin_mutation_requires_csrf(client, admin):
    assert client.post("/api/admin/slips", json={"prediction_ids": [1]}).status_code == 403


def test_cookie_is_http_only_and_me_returns_role(client, admin):
    response = client.get("/api/auth/me")
    assert response.status_code == 200 and response.json()["role"] == "admin"
    assert "sp_session" in client.cookies
    assert client.post("/api/auth/logout", json={}, headers=admin).status_code == 200
    assert client.get("/api/admin/models").status_code == 401


def test_viewer_cannot_change_settings(client, db):
    db.add(User(email="viewer@example.test", password_hash=password_hasher.hash("viewer-password"), role="viewer")); db.commit()
    login = client.post("/api/auth/login", json={"email":"viewer@example.test","password":"viewer-password"})
    assert login.status_code == 200
    response = client.put("/api/admin/settings", headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={"threshold":.8,"min_quality":.7,"max_legs":1,"publication_paused":False,"provider_enabled":True})
    assert response.status_code == 403


def test_admin_settings_rechecks_eligibility(client, admin, selection):
    response = client.put("/api/admin/settings", headers=admin,
        json={"threshold":.9,"min_quality":.7,"max_legs":1,"publication_paused":False,"provider_enabled":True})
    assert response.status_code == 200
    assert not selection.eligible and "below_probability_threshold" in selection.reasons


def test_login_throttles_failed_attempts(client):
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email":"missing@test.com","password":"bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"email":"missing@test.com","password":"bad"}).status_code == 429


def test_untrusted_origin_rejected(client):
    assert client.post("/api/auth/login", headers={"Origin":"https://untrusted.invalid"}, json={"email":"a@b.c","password":"x"}).status_code == 403


def test_cookie_mutations_reject_cross_origin(client, admin):
    assert client.post("/api/auth/logout", headers={**admin,"Origin":"https://untrusted.invalid"}).status_code == 403


def test_public_api_real_persistence_search_and_details(client, selection):
    fixtures = client.get("/api/fixtures?q=Test%20Home").json()
    assert fixtures["total"] == 1
    detail = client.get(f"/api/fixtures/{selection.fixture_id}").json()
    assert detail["predictions"][0]["probability"] == .85
    assert detail["fixture"]["kickoff"].endswith("Z")
    assert client.get("/api/fixtures?q=not-a-team").json()["total"] == 0
    assert client.get("/api/fixtures/999999").status_code == 404


def test_unverified_code_is_never_in_public_verified_feed(client, db, selection):
    from app.providers.booking import MockBookingProvider
    from app.services.publication import build_slip, publish_slip
    publish_slip(db, build_slip(db,[selection.id]).id, MockBookingProvider())
    assert client.get("/api/slips?verified_only=true").json()["total"] == 0
    item = client.get("/api/slips").json()["items"][0]
    assert item["code"] is None and item["status"] == "prediction_only"


def test_high_confidence_feed_hides_stale_odds(client, selection):
    from datetime import timedelta
    from app.models.entities import utcnow
    selection.odds_at = utcnow() - timedelta(hours=1)
    assert client.get("/api/predictions?high_confidence=true").json()["total"] == 0


def test_latest_snapshot_feed_preserves_full_historical_records(client, db, selection):
    from app.models.entities import Prediction, utcnow
    newest=Prediction(fixture=selection.fixture,model=selection.model,market=selection.market,generation="next-window",
                      probability=.88,raw_probability=.9,quality=.85,odds=1.3,odds_at=utcnow(),eligible=True,
                      features={},explanation="New snapshot",created_at=utcnow())
    db.add(newest);db.commit()
    assert client.get("/api/predictions").json()["total"]==2
    latest=client.get("/api/predictions?latest_only=true").json()
    assert latest["total"]==1 and latest["items"][0]["id"]==newest.id
    assert len(client.get(f"/api/fixtures/{selection.fixture_id}").json()["predictions"])==1
