from datetime import UTC, datetime

import httpx
import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select

from app.core.config import Settings, get_settings
from app.models.entities import Fixture, Team
from app.providers.fixtures import AuthorizedFixtureProvider, DemoFixtureProvider, normalize
from app.schemas.contracts import FixtureDTO
from app.services.ingestion import sync_fixtures


def test_demo_feed_contract_and_idempotent_ingestion(db):
    provider = DemoFixtureProvider()
    rows = provider.fetch()
    assert all(r.simulated for r in rows)
    first = sync_fixtures(db, provider)
    second = sync_fixtures(db, provider)
    assert first["created"] == len(rows) and second["created"] == 0
    assert db.scalar(select(func.count()).select_from(Fixture)) == len(rows)
    assert db.scalar(select(func.count()).select_from(Team)) == 24


def test_normalization_and_natural_key_prevent_duplicate(db):
    assert normalize("  Atlético   SOL! ") == "atletico sol"
    row = DemoFixtureProvider().fetch()[-1]
    class A:
        name = "a"
        def fetch(self): return [row]
    class B:
        name = "b"
        def fetch(self): return [row.model_copy(update={"external_id":"different","home":row.home.upper()})]
    sync_fixtures(db,A()); sync_fixtures(db,B())
    assert db.scalar(select(func.count()).select_from(Fixture)) == 1


def test_external_data_requires_timezone_and_result_availability():
    row = DemoFixtureProvider().fetch()[0].model_dump()
    row["kickoff"] = datetime(2026,1,1)
    with pytest.raises(ValidationError): FixtureDTO.model_validate(row)
    row["kickoff"] = datetime(2026,1,1,tzinfo=UTC)
    row["result_known_at"] = None
    with pytest.raises(ValidationError): FixtureDTO.model_validate(row)


def test_authorized_provider_contract(monkeypatch):
    row = DemoFixtureProvider().fetch()[0].model_dump(mode="json")
    row.update(simulated=False, league_slug="premier-league")
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"fixtures":[row]})
    monkeypatch.setattr(httpx,"Client",lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    settings = Settings(jwt_secret="x"*48,fixture_api_url="https://authorized.example.test/feed",fixture_api_token="test-token")
    rows = AuthorizedFixtureProvider(settings).fetch()
    assert len(rows) == 1 and calls[0].headers["Authorization"] == "Bearer test-token"


def test_migration_upgrade_downgrade_and_no_schema_drift(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path/'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL",url); get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config,"head")
        engine = create_engine(url)
        assert {"fixtures","users","predictions","slips","audit_logs","job_runs"}.issubset(inspect(engine).get_table_names())
        command.check(config)
        command.downgrade(config,"base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        command.upgrade(config,"head")
        engine.dispose()
    finally:
        get_settings.cache_clear()
