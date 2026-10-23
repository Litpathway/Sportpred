from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.leagues import DEFAULT_LEAGUES, EUROPEAN_LEAGUES
from app.models.entities import Competition, User
from app.providers.fixtures import AuthorizedFixtureProvider, ProviderFailure
from app.services.ingestion import sync_fixtures


def feed_rows():
    return [{"external_id": str(i), "competition": league["name"], "league_slug": slug,
             "country": league["country"], "home": f"Home {i}", "away": f"Away {i}",
             "kickoff": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "status": "scheduled"}
            for i, (slug, league) in enumerate(EUROPEAN_LEAGUES.items())]


def provider(monkeypatch, rows, **kwargs):
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"fixtures": rows}))
    monkeypatch.setattr(httpx, "Client", lambda **options: original(transport=transport, **options))
    return AuthorizedFixtureProvider(Settings(_env_file=None, jwt_secret="x" * 48,
        fixture_api_url="https://licensed.example.test", fixture_api_token="test", **kwargs))


def test_ten_leagues_ingest_and_coverage_is_based_on_received_data(db, client, monkeypatch):
    before = client.get("/api/league-coverage").json()
    assert len(before) == 10 and all(row["status"] == "awaiting_feed" for row in before)
    assert sync_fixtures(db, provider(monkeypatch, feed_rows()))["created"] == 10
    assert db.scalar(select(func.count()).select_from(Competition)) == 10
    after = client.get("/api/league-coverage").json()
    assert {row["slug"] for row in after} == set(EUROPEAN_LEAGUES)
    assert all(row["fixtures"] == 1 and row["status"] == "data_received" for row in after)


def test_authorized_feed_filters_disabled_leagues(monkeypatch):
    feed = provider(monkeypatch, feed_rows(), enabled_leagues="premier-league,super-lig")
    assert {row.league_slug for row in feed.fetch()} == {"premier-league", "super-lig"}
    assert len(feed.warnings) == 8


@pytest.mark.parametrize("change, message", [({"league_slug": None}, "league_slug"),
    ({"simulated": True}, "simulated"), ({"country": "Spain"}, "country")])
def test_ambiguous_or_simulated_authorized_records_fail_before_ingestion(db, monkeypatch, change, message):
    rows = feed_rows()
    rows[-1] = {**rows[-1], **change}
    with pytest.raises(ProviderFailure, match=message):
        sync_fixtures(db, provider(monkeypatch, rows))
    assert db.scalar(select(func.count()).select_from(Competition)) == 0


@pytest.mark.parametrize("slugs", ["", "premier-league,premier-league", "unknown-league"])
def test_league_configuration_rejects_mistakes(slugs):
    with pytest.raises(ValidationError, match="ENABLED_LEAGUES"):
        Settings(_env_file=None, jwt_secret="x" * 48, enabled_leagues=slugs)


def test_cloud_bootstrap_migrates_and_preserves_existing_admin(tmp_path, monkeypatch):
    import app.cloud as cloud
    test_engine = create_engine(f"sqlite:///{(tmp_path / 'cloud.db').as_posix()}")
    factory = sessionmaker(test_engine)
    settings = Settings(_env_file=None, jwt_secret="x" * 48, admin_password="unique-test-password")
    monkeypatch.setattr(cloud, "engine", test_engine)
    monkeypatch.setattr(cloud, "SessionLocal", factory)
    monkeypatch.setattr(cloud, "get_settings", lambda: settings)
    try:
        cloud.bootstrap()
        assert "artifact_data" in {c["name"] for c in inspect(test_engine).get_columns("model_versions")}
        with factory() as session:
            original = session.scalar(select(User)).password_hash
        settings.admin_password = "a-different-test-password"
        cloud.bootstrap()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.scalar(select(User)).password_hash == original
    finally:
        test_engine.dispose()


def test_cloud_process_uses_platform_port_and_writable_scheduler_state(monkeypatch):
    from app.cloud import process_command
    monkeypatch.setenv("PORT", "8080")
    api = process_command("api")
    assert api[api.index("--port") + 1] == "8080"
    assert "--schedule=/tmp/sportpredict-beat" in process_command("scheduler")
