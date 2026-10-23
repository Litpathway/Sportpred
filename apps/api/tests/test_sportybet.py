from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.providers.sportybet import SportyBetOddsOverlay, _market_quotes
from app.schemas.contracts import FixtureDTO


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl):
        self.values[key] = value


def row(kickoff):
    return FixtureDTO(external_id="1001", competition="Premier League", country="England",
        league_slug="premier-league", home="Home Club", away="Away Club", id_namespace="api-football",
        home_external_id="10", away_external_id="20", competition_external_id="39", kickoff=kickoff,
        status="scheduled", enrichment={"provenance": {}})


def event(kickoff_ms):
    return {"eventId": "sr:match:5001", "homeTeamName": "Home Club", "awayTeamName": "Away Club",
        "estimateStartTime": kickoff_ms, "markets": [
            {"id": "1", "outcomes": [
                {"id": "1", "desc": "1", "odds": "1.80", "isActive": 1},
                {"id": "2", "desc": "X", "odds": "3.40", "isActive": 1},
                {"id": "3", "desc": "2", "odds": "4.20", "isActive": 1}]},
            {"id": "18", "specifier": "total=2.5", "outcomes": [
                {"id": "over", "desc": "Over", "odds": "1.95", "isActive": 1},
                {"id": "under", "desc": "Under", "odds": "1.85", "isActive": 1}]},
            {"id": "29", "outcomes": [
                {"id": "yes", "desc": "Yes", "odds": "1.75", "isActive": 1},
                {"id": "no", "desc": "No", "odds": "2.10", "isActive": 1}]},
        ]}


def test_market_quotes_normalize_only_known_decimal_markets():
    quotes = _market_quotes(event(1_800_000_000_000)["markets"][0])
    assert quotes == {"home_win": 1.8, "draw": 3.4, "away_win": 4.2}
    assert _market_quotes({"id": "18", "specifier": "total=2.5", "outcomes": [
        {"desc": "Over", "odds": "2.0", "isActive": 0}, {"desc": "Under", "odds": "1.8", "isActive": 1}]}) == {"under_2_5": 1.8}


def test_overlay_matches_league_teams_and_kickoff_then_records_source():
    kickoff = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
    match = event(kickoff.timestamp() * 1000)
    client = httpx.Client(base_url="https://www.sportybet.com", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"bizCode": 10000, "data": {"tournaments": [
            {"name": "Premier League", "categoryName": "England", "events": [match]}]}})))
    settings = Settings(_env_file=None, jwt_secret="x" * 48, sportybet_odds_enabled=True)
    overlay = SportyBetOddsOverlay(settings, MemoryCache(), client=client, sleep=lambda _: None)
    fixture = row(kickoff)
    assert overlay.apply([fixture]) == 1
    assert fixture.odds == {"home_win": 1.8, "draw": 3.4, "away_win": 4.2,
                            "over_2_5": 1.95, "under_2_5": 1.85, "btts_yes": 1.75, "btts_no": 2.1}
    assert fixture.enrichment["provenance"]["odds"]["source"] == "SportyBet NG"
    assert fixture.enrichment["provenance"]["odds"]["event_id"] == "sr:match:5001"
    client.close()


def test_overlay_rejects_nearby_but_different_kickoffs():
    kickoff = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
    match = event((kickoff.timestamp() + 16 * 60) * 1000)
    client = httpx.Client(base_url="https://www.sportybet.com", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"bizCode": 10000, "data": {"tournaments": [
            {"name": "Premier League", "categoryName": "England", "events": [match]}]}})))
    overlay = SportyBetOddsOverlay(Settings(_env_file=None, jwt_secret="x" * 48), MemoryCache(), client=client, sleep=lambda _: None)
    fixture = row(kickoff)
    assert overlay.apply([fixture]) == 0
    assert fixture.odds == {}
    client.close()


def test_league_aliases_are_country_scoped_for_all_ten_leagues():
    overlay = SportyBetOddsOverlay(Settings(_env_file=None, jwt_secret="x" * 48), MemoryCache())
    expected = {
        ("Premier League", "England"): "premier-league",
        ("LaLiga", "Spain"): "la-liga",
        ("Bundesliga", "Germany"): "bundesliga",
        ("Serie A", "Italy"): "serie-a",
        ("Ligue 1", "France"): "ligue-1",
        ("Eredivisie", "Netherlands"): "eredivisie",
        ("Liga Portugal", "Portugal"): "primeira-liga",
        ("Pro League", "Belgium"): "belgian-pro-league",
        ("Super Lig", "Turkey"): "super-lig",
        ("Premiership", "Scotland"): "scottish-premiership",
    }
    assert {overlay._league_slug({"name": league, "categoryName": country})
            for (league, country) in expected} == set(expected.values())
