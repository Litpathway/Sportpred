import copy
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.providers.api_football import ApiFootballProvider, LEAGUE_IDS, RequestBudgetExceeded
from app.providers.fixtures import ProviderFailure


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.used = 0

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def set(self, key, value, ttl):
        self.values[key] = copy.deepcopy(value)

    def reserve(self, now, limit):
        if self.used >= limit:
            return False
        self.used += 1
        return True


def settings(**extra):
    return Settings(_env_file=None, jwt_secret="x" * 48, environment="test", demo_mode=False,
        api_football_key="server-only-test-key", api_football_days_ahead=1, **extra)


def fixture(status="NS", fixture_id=12001):
    final = status in {"FT", "AET", "PEN"}
    kickoff = datetime.now(UTC) + timedelta(days=-2 if final else 1)
    return {"fixture": {"id": fixture_id, "date": kickoff.isoformat(), "status": {"short": status}},
        "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026},
        "teams": {"home": {"id": 33, "name": "Home Club"}, "away": {"id": 34, "name": "Away Club"}},
        "goals": {"home": 3 if final else None, "away": 2 if final else None},
        "score": {"fulltime": {"home": 1, "away": 1} if final else {"home": None, "away": None}}}


def metadata():
    from app.core.leagues import EUROPEAN_LEAGUES
    return [{"league": {"id": native, "name": EUROPEAN_LEAGUES[slug]["name"], "type": "League"},
        "country": {"name": EUROPEAN_LEAGUES[slug]["country"]},
        "seasons": [{"year": 2026, "current": True, "coverage": {"odds": True}}]}
        for slug, native in LEAGUE_IDS.items()]


def odds():
    return {"fixture": {"id": 12001}, "update": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        "bookmakers": [{"id": 2, "name": "Contract Test Book", "bets": [
            {"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": "1.80"}, {"value": "Draw", "odd": "3.50"}, {"value": "Away", "odd": "4.20"}]},
            {"id": 5, "name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.90"}, {"value": "Over 3.5", "odd": "3.10"}, {"value": "Under 2.5", "odd": "1.95"}]},
            {"id": 8, "name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.82"}, {"value": "No", "odd": "2.05"}]},
            {"id": 12, "name": "Double Chance", "values": [{"value": "Home/Draw", "odd": "1.20"}, {"value": "Draw/Away", "odd": "1.90"}, {"value": "Home/Away", "odd": "1.32"}]}]}]}


def client(handler):
    return httpx.Client(base_url="https://v3.football.api-sports.io", transport=httpx.MockTransport(handler))


def wrapped(data, errors=None, total=1):
    return httpx.Response(200, json={"errors": errors or [], "paging": {"current": 1, "total": total}, "response": data})


def test_native_feed_authentication_mapping_cache_and_no_external_prediction_calls():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["x-apisports-key"] == "server-only-test-key"
        if request.url.path == "/status":
            return wrapped({"subscription": {"plan": "Free", "active": True}, "requests": {"current": 1, "limit_day": 100}})
        if request.url.path == "/leagues":
            return wrapped(metadata())
        if request.url.path == "/odds":
            return wrapped([odds()])
        return wrapped([fixture()])
    cache = MemoryCache()
    with client(handler) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=cache)
        rows = provider.fetch()
        assert len(rows) == 1 and rows[0].league_slug == "premier-league"
        assert rows[0].id_namespace == "api-football" and rows[0].home_external_id == "33"
        assert len(rows[0].odds) == 10 and rows[0].odds["over_2_5"] == 1.9
        assert rows[0].odds_at < datetime.now(UTC) - timedelta(minutes=9)
        assert rows[0].enrichment["provenance"]["odds"]["bookmaker_id"] == 2
        assert cache.values["status_summary"]["plan"] == "Free"
        # Cache age is preserved; it never becomes a freshly-observed quote.
        original = provider._read("/odds", {"fixture": 12001})[1]
        again = provider._read("/odds", {"fixture": 12001})[1]
        assert original == again
        assert {r.url.path for r in calls} == {"/status", "/leagues", "/fixtures", "/odds"}


def test_plan_restricted_history_for_one_league_does_not_block_the_next_league():
    history_leagues = []

    def handler(request):
        if request.url.path == "/status":
            return wrapped({"subscription": {"plan": "Free", "active": True}, "requests": {"current": 1, "limit_day": 100}})
        if request.url.path == "/leagues":
            return wrapped(metadata())
        if request.url.path == "/fixtures" and "league" in request.url.params:
            league = int(request.url.params["league"])
            history_leagues.append(league)
            if league == LEAGUE_IDS["premier-league"]:
                return wrapped([], errors={"plan": "competition unavailable"})
            return wrapped([])
        return wrapped([])

    with client(handler) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=MemoryCache())
        provider.fetch()

    assert history_leagues == [LEAGUE_IDS["premier-league"], LEAGUE_IDS["la-liga"]]
    assert any(warning["reason"] == "history_unavailable" for warning in provider.warnings)


@pytest.mark.parametrize("status", ["FT", "AET", "PEN"])
def test_final_scores_use_regulation_time_and_observed_availability(status):
    with client(lambda r: wrapped([])) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=MemoryCache())
        observed = datetime.now(UTC)
        row = provider._fixture(fixture(status), observed)
        assert (row.home_goals, row.away_goals) == (1, 1)
        assert row.result_known_at == observed
        assert row.enrichment["provenance"]["result_time_basis"] == "first_observed_final"


def test_secret_is_masked_and_provider_errors_never_echo_keys():
    configured = settings()
    assert "server-only-test-key" not in repr(configured)
    with client(lambda r: wrapped([], errors={"token": "server-only-test-key rejected"})) as http:
        provider = ApiFootballProvider(configured, client=http, cache=MemoryCache())
        with pytest.raises(ProviderFailure, match="token error") as exc:
            provider._read("/fixtures")
        assert "server-only-test-key" not in str(exc.value)


@pytest.mark.parametrize("error", [{"requests": "quota exceeded"}, {"rateLimit": "too many"}])
def test_http_200_quota_errors_stop_instead_of_repeating(error):
    with client(lambda r: wrapped([], errors=error)) as http:
        with pytest.raises(RequestBudgetExceeded):
            ApiFootballProvider(settings(), client=http, cache=MemoryCache())._read("/fixtures")


def test_request_limit_prevents_network_calls():
    calls = []
    with client(lambda r: calls.append(r) or wrapped([])) as http:
        provider = ApiFootballProvider(settings(api_football_daily_budget=1), client=http, cache=MemoryCache())
        provider._read("/fixtures", {"date": "2026-10-23"})
        with pytest.raises(RequestBudgetExceeded):
            provider._read("/fixtures", {"date": "2026-10-24"})
    assert len(calls) == 1


def test_missing_odds_does_not_fabricate_quotes():
    with client(lambda r: wrapped([])) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=MemoryCache())
        row = provider._fixture(fixture(), datetime.now(UTC))
        empty = odds()
        empty["bookmakers"] = []
        provider._odds(row, empty, datetime.now(UTC))
        assert row.odds == {} and row.odds_at is None


def test_paginated_response_is_not_silently_treated_as_complete():
    with client(lambda r: wrapped([fixture()], total=2)) as http:
        with pytest.raises(ProviderFailure, match="incomplete"):
            ApiFootballProvider(settings(), client=http, cache=MemoryCache())._read("/fixtures")


def test_native_provider_requires_real_data_and_actual_key():
    with pytest.raises(ProviderFailure, match="DEMO_MODE"):
        ApiFootballProvider(Settings(_env_file=None, jwt_secret="x" * 48, api_football_key="test", demo_mode=True))
    with pytest.raises(ProviderFailure, match="API_FOOTBALL_KEY"):
        ApiFootballProvider(settings().model_copy(update={"api_football_key": None}))


def test_native_postgres_connection_strings_select_psycopg():
    configured = settings(database_url="postgresql://user:password@db.test/db", database_url_unpooled="postgres://user:password@direct.test/db")
    assert configured.database_url.startswith("postgresql+psycopg://")
    assert configured.database_url_unpooled.startswith("postgresql+psycopg://")


def test_observed_history_supplies_current_form_without_creating_probabilities(db, client):
    from sqlalchemy import select
    from app.models.entities import Fixture
    from app.services.ingestion import sync_fixtures
    now = datetime.now(UTC)
    with httpx.Client(base_url="https://v3.football.api-sports.io", transport=httpx.MockTransport(lambda r: wrapped([]))) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=MemoryCache())
        rows = []
        for index in range(7):
            event = fixture("FT", fixture_id=13000 + index)
            event["fixture"]["date"] = (now - timedelta(days=(index + 1) * 7)).isoformat()
            rows.append(provider._fixture(event, now))
        rows.append(provider._fixture(fixture(), now))
    class Imported:
        name = "api_football"
        def fetch(self): return rows
    sync_fixtures(db, Imported())
    upcoming = db.scalar(select(Fixture).where(Fixture.status == "scheduled"))
    response = client.get(f"/api/fixtures/{upcoming.id}")
    assert response.status_code == 200
    assert response.json()["predictions"] == []
    assert response.json()["evidence"]["home_form"] == ["D"] * 5
    assert response.json()["data_status"] == "insufficient_data"


def test_older_cached_schedule_cannot_undo_an_observed_final_score(db):
    from sqlalchemy import select
    from app.models.entities import Fixture
    from app.services.ingestion import sync_fixtures
    now = datetime.now(UTC)
    with client(lambda r: wrapped([])) as http:
        provider = ApiFootballProvider(settings(), client=http, cache=MemoryCache())
        old = fixture()
        old["fixture"]["date"] = (now - timedelta(days=2)).isoformat()
        stale = provider._fixture(old, now - timedelta(hours=2))
        final = copy.deepcopy(old)
        final["fixture"]["status"]["short"] = "FT"
        final["score"]["fulltime"] = {"home": 2, "away": 1}
        finished = provider._fixture(final, now)
    class Imported:
        name = "api_football"
        def __init__(self, row): self.row = row
        def fetch(self): return [self.row]
    sync_fixtures(db, Imported(stale))
    sync_fixtures(db, Imported(finished))
    sync_fixtures(db, Imported(stale))
    stored = db.scalar(select(Fixture))
    assert stored.status == "finished" and (stored.home_goals, stored.away_goals) == (2, 1)
    assert stored.synced_at == now.replace(tzinfo=None)
