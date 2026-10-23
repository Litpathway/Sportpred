"""Read-only SportyBet odds overlay based on its documented public web feed.

SportyBet does not publish a supported developer API. Keep this optional,
read-only, rate-limited, and isolated from fixture identity and model history.
"""
import re
import time
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import Settings
from app.core.leagues import EUROPEAN_LEAGUES
from app.providers.fixtures import ProviderFailure, normalize
from app.schemas.contracts import FixtureDTO

BASE_URL = "https://www.sportybet.com"
MARKET_IDS = "1,18,10,29,11,26,36,14,60100"
PAGE_SIZE = 100
MAX_PAGES = 5
MIN_INTERVAL_SECONDS = 0.25
TEAM_MATCH_WINDOW = timedelta(minutes=15)
LEAGUE_NAMES = {
    "premier-league": {"premier league"}, "la-liga": {"laliga", "la liga"},
    "bundesliga": {"bundesliga"}, "serie-a": {"serie a"},
    "ligue-1": {"ligue 1", "ligue 1 uber eats"}, "eredivisie": {"eredivisie"},
    "primeira-liga": {"primeira liga", "liga portugal", "liga portugal betclic"},
    "belgian-pro-league": {"belgian pro league", "jupiler pro league", "pro league"},
    "super-lig": {"super lig", "super lig turkey"},
    "scottish-premiership": {"scottish premiership", "premiership"},
}


def _valid_price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if 1 < price < 1001 else None


def _update_time(value, observed):
    try:
        stamp = float(value)
        stamp /= 1000 if stamp > 100_000_000_000 else 1
        result = datetime.fromtimestamp(stamp, UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if result > observed or result < observed - timedelta(days=1):
        return None
    return result


def _market_quotes(market):
    market_id = str(market.get("id", ""))
    specifier = normalize(str(market.get("specifier", "")))
    quotes = {}
    for outcome in market.get("outcomes", []):
        if not isinstance(outcome, dict) or outcome.get("isActive", 1) not in (1, True, "1"):
            continue
        price = _valid_price(outcome.get("odds"))
        if price is None:
            continue
        label = normalize(str(outcome.get("desc", "")))
        outcome_id = str(outcome.get("id", ""))
        key = None
        if market_id == "1":
            key = {"home": "home_win", "home win": "home_win", "1": "home_win",
                   "draw": "draw", "x": "draw",
                   "away": "away_win", "away win": "away_win", "2": "away_win"}.get(label)
            if key is None:
                key = {"1": "home_win", "2": "draw", "3": "away_win"}.get(outcome_id)
        elif market_id == "10":
            key = {"home draw": "home_or_draw", "1x": "home_or_draw", "home or draw": "home_or_draw",
                   "draw away": "away_or_draw", "x2": "away_or_draw", "draw or away": "away_or_draw",
                   "home away": "home_or_away", "12": "home_or_away", "home or away": "home_or_away"}.get(label)
        elif market_id == "18":
            line = "2 5" in label or "2 5" in specifier
            if line and re.search(r"\bover\b", label):
                key = "over_2_5"
            elif line and re.search(r"\bunder\b", label):
                key = "under_2_5"
        elif market_id == "29":
            if label in {"yes", "gg", "both teams to score yes"}:
                key = "btts_yes"
            elif label in {"no", "ng", "both teams to score no"}:
                key = "btts_no"
        if key and key not in quotes:
            quotes[key] = price
    return quotes


class SportyBetOddsOverlay:
    """Attach only exact team/league/kickoff matches; never creates fixtures."""

    def __init__(self, settings: Settings, cache, *, client=None, sleep=time.sleep):
        self.settings, self.cache, self.client, self.sleep = settings, cache, client, sleep
        self.warnings = []

    def _league_slug(self, tournament):
        name = normalize(str(tournament.get("name", "")))
        country = normalize(str(tournament.get("categoryName", "")))
        for slug, names in LEAGUE_NAMES.items():
            if slug in self.settings.league_slugs and name in {normalize(n) for n in names} and country == normalize(EUROPEAN_LEAGUES[slug]["country"]):
                return slug
        return None

    def _feed(self):
        key = f"sportybet:fixtures:v1:{self.settings.sportybet_region}"
        saved = self.cache.get(key)
        if saved:
            return saved
        tournaments = []
        last_request = 0.0
        with httpx.Client(base_url=BASE_URL, timeout=15, follow_redirects=False) as owned:
            client = self.client or owned
            for page in range(1, MAX_PAGES + 1):
                delay = MIN_INTERVAL_SECONDS - (time.monotonic() - last_request)
                if page > 1 and delay > 0:
                    self.sleep(delay)
                try:
                    response = client.get(f"/api/{self.settings.sportybet_region}/factsCenter/pcUpcomingEvents",
                        params={"sportId": "sr:sport:1", "marketId": MARKET_IDS, "pageSize": PAGE_SIZE,
                                "pageNum": page, "todayGames": "false", "timeline": 720,
                                "_t": int(time.time() * 1000)},
                        headers={"Accept": "application/json", "Content-Type": "application/json",
                                 "Current-Country": self.settings.sportybet_region.upper()})
                except httpx.HTTPError:
                    raise ProviderFailure("SportyBet odds feed is unreachable") from None
                last_request = time.monotonic()
                if response.status_code == 429:
                    raise ProviderFailure("SportyBet odds feed rate limit reached")
                if response.status_code != 200:
                    raise ProviderFailure(f"SportyBet odds feed returned HTTP {response.status_code}")
                try:
                    envelope = response.json()
                    if envelope.get("bizCode") != 10000 or not isinstance(envelope.get("data", {}).get("tournaments"), list):
                        raise ValueError
                    page_tournaments = envelope["data"]["tournaments"]
                except (ValueError, TypeError, AttributeError):
                    raise ProviderFailure("SportyBet odds feed returned an invalid response") from None
                event_count = sum(len(t.get("events", [])) for t in page_tournaments if isinstance(t, dict))
                tournaments.extend(page_tournaments)
                if event_count < PAGE_SIZE:
                    break
        observed = datetime.now(UTC)
        result = {"tournaments": tournaments, "observed_at": observed.isoformat()}
        self.cache.set(key, result, self.settings.sportybet_cache_seconds)
        return result

    def apply(self, rows: list[FixtureDTO]) -> int:
        payload = self._feed()
        observed = datetime.fromisoformat(payload["observed_at"])
        by_teams = {}
        for row in rows:
            if row.status == "scheduled" and row.league_slug:
                by_teams.setdefault((row.league_slug, normalize(row.home), normalize(row.away)), []).append(row)
        matches = 0
        used = set()
        for tournament in payload["tournaments"]:
            if not isinstance(tournament, dict):
                continue
            slug = self._league_slug(tournament)
            if not slug:
                continue
            for event in tournament.get("events", []):
                if not isinstance(event, dict):
                    continue
                home, away = normalize(str(event.get("homeTeamName", ""))), normalize(str(event.get("awayTeamName", "")))
                candidates = by_teams.get((slug, home, away), [])
                try:
                    kickoff = datetime.fromtimestamp(float(event["estimateStartTime"]) / 1000, UTC)
                except (KeyError, TypeError, ValueError, OverflowError, OSError):
                    continue
                choices = [(abs((candidate.kickoff.astimezone(UTC) - kickoff).total_seconds()), candidate)
                           for candidate in candidates if abs((candidate.kickoff.astimezone(UTC) - kickoff).total_seconds()) <= TEAM_MATCH_WINDOW.total_seconds()]
                if not choices:
                    continue
                row = min(choices, key=lambda pair: pair[0])[1]
                if row.external_id in used:
                    continue
                quotes, updates = {}, []
                for market in event.get("markets", []):
                    if not isinstance(market, dict):
                        continue
                    quotes.update({k: v for k, v in _market_quotes(market).items() if k not in quotes})
                    if market.get("lastOddsChangeTime") is not None:
                        stamp = _update_time(market["lastOddsChangeTime"], observed)
                        if stamp:
                            updates.append(stamp)
                if not quotes:
                    continue
                row.odds = quotes
                row.odds_at = min(updates) if updates else observed
                provenance = row.enrichment.setdefault("provenance", {})
                provenance["odds"] = {"source": "SportyBet NG", "event_id": str(event.get("eventId", "")),
                    "provider_updated_at": min(updates).isoformat() if updates else None,
                    "observed_at": observed.isoformat(), "market_count": len(quotes)}
                used.add(row.external_id)
                matches += 1
        return matches
