"""Server-only API-Sports v3 adapter. Never requests provider predictions or bets."""
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

import httpx
import redis
from pydantic import ValidationError

from app.core.config import Settings
from app.core.leagues import EUROPEAN_LEAGUES
from app.providers.fixtures import ProviderFailure, normalize
from app.schemas.contracts import FixtureDTO

BASE_URL = "https://v3.football.api-sports.io"
LEAGUE_IDS = {"premier-league": 39, "la-liga": 140, "bundesliga": 78, "serie-a": 135,
    "ligue-1": 61, "eredivisie": 88, "primeira-liga": 94, "belgian-pro-league": 144,
    "super-lig": 203, "scottish-premiership": 179}
STATUS = {"NS": "scheduled", "1H": "live", "HT": "live", "2H": "live", "BT": "live",
    "ET": "live", "P": "live", "LIVE": "live", "FT": "finished", "AET": "finished",
    "PEN": "finished", "PST": "postponed", "SUSP": "postponed", "INT": "postponed",
    "CANC": "cancelled", "ABD": "cancelled"}


class RequestBudgetExceeded(ProviderFailure):
    pass


class RedisApiCache:
    def __init__(self, url: str, key: str):
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
        self.prefix = "sportpredict:api-football:" + hashlib.sha256(key.encode()).hexdigest()[:16] + ":"

    def get(self, key):
        try:
            value = self.client.get(self.prefix + key)
            return json.loads(value) if value else None
        except (redis.RedisError, ValueError):
            raise ProviderFailure("API-Football cache unavailable; check Redis") from None

    def set(self, key, value, ttl):
        try:
            self.client.set(self.prefix + key, json.dumps(value), ex=ttl)
        except redis.RedisError:
            raise ProviderFailure("API-Football cache unavailable; check Redis") from None

    def reserve(self, now, daily_limit):
        # Atomic limits survive new worker processes and manual job retries.
        script = """
        local d = tonumber(redis.call('GET', KEYS[1]) or '0')
        local m = tonumber(redis.call('GET', KEYS[2]) or '0')
        if d >= tonumber(ARGV[1]) or m >= 8 then return 0 end
        redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], 172800)
        redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], 120)
        return 1
        """
        try:
            return bool(self.client.eval(script, 2, self.prefix + "day:" + now.strftime("%Y-%m-%d"),
                self.prefix + "minute:" + now.strftime("%Y-%m-%dT%H:%M"), daily_limit))
        except redis.RedisError:
            raise ProviderFailure("API-Football quota guard unavailable; check Redis") from None


def aware_time(value):
    if not isinstance(value, str):
        raise ValueError("Missing provider timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Provider timestamp has no timezone")
    return stamp.astimezone(UTC)


class ApiFootballProvider:
    name = "api_football"

    def __init__(self, settings: Settings, *, client=None, cache=None):
        if settings.demo_mode:
            raise ProviderFailure("API-Football requires DEMO_MODE=false")
        if not settings.api_football_key or settings.api_football_key.get_secret_value() == "[SENSITIVE]":
            raise ProviderFailure("Set API_FOOTBALL_KEY in the server environment")
        self.settings = settings
        self.key = settings.api_football_key.get_secret_value()
        self.client = client
        self.cache = cache if cache is not None else RedisApiCache(settings.redis_url, self.key)
        self.slugs = settings.league_slugs
        self.ids = {LEAGUE_IDS[s]: s for s in self.slugs}
        self.calls = 0
        self.warnings = []

    def _read(self, path, params=None, ttl=3600):
        params = params or {}
        key = path + ":" + json.dumps(params, sort_keys=True, separators=(",", ":"))
        if path == "/leagues":
            key += ":" + ",".join(map(str, sorted(self.ids)))
        saved = self.cache.get(key)
        if saved:
            return saved["data"], aware_time(saved["observed_at"])
        now = datetime.now(UTC)
        if self.calls >= self.settings.api_football_max_requests or not self.cache.reserve(now, self.settings.api_football_daily_budget):
            raise RequestBudgetExceeded("API-Football request budget reached; cached data is retained")
        self.calls += 1
        try:
            if self.client is not None:
                response = self.client.get(path, params=params, headers={"x-apisports-key": self.key})
            else:
                with httpx.Client(base_url=BASE_URL, timeout=25, follow_redirects=False) as client:
                    response = client.get(path, params=params, headers={"x-apisports-key": self.key})
        except httpx.HTTPError:
            raise ProviderFailure("API-Football connection unavailable") from None
        if response.status_code in {401, 403}:
            self.cache.set("last_error", {"endpoint": path, "reason": "authentication_or_subscription", "observed_at": datetime.now(UTC).isoformat()}, 3600)
            raise ProviderFailure("API-Football rejected authentication or subscription access")
        if response.status_code == 429:
            raise RequestBudgetExceeded("API-Football rate limit reached")
        if response.status_code != 200:
            raise ProviderFailure(f"API-Football returned HTTP {response.status_code}")
        try:
            envelope = response.json()
        except ValueError:
            raise ProviderFailure("API-Football returned invalid JSON") from None
        if not isinstance(envelope, dict) or "response" not in envelope:
            raise ProviderFailure("Invalid API-Football response envelope")
        if envelope.get("errors"):
            # Providers may echo parameters/credentials in error descriptions.
            # Store only known error-field names, never the raw provider message.
            errors = envelope["errors"]
            kind = next((k for k in ("token", "requests", "rateLimit", "access", "plan", "season") if isinstance(errors, dict) and k in errors), "provider")
            self.cache.set("last_error", {"endpoint": path, "reason": kind, "observed_at": now.isoformat()}, 3600)
            if kind in {"requests", "rateLimit"}:
                raise RequestBudgetExceeded("API-Football request limit reached")
            raise ProviderFailure(f"API-Football {kind} error; check subscription and provider dashboard")
        paging = envelope.get("paging") or {"current": 1, "total": 1}
        if paging.get("total", 1) != 1:
            raise ProviderFailure("Unexpected paginated API-Football response; batch is incomplete")
        data = envelope["response"]
        if path == "/status" and isinstance(data, dict):
            subscription = data.get("subscription") or {}
            requests = data.get("requests") or {}
            data = {"subscription": {k: subscription.get(k) for k in ("plan", "active")},
                    "requests": {k: requests.get(k) for k in ("current", "limit_day")}}
        if path != "/status" and not isinstance(data, list):
            raise ProviderFailure("Invalid API-Football response list")
        if path == "/leagues":
            data = [row for row in data if row.get("league", {}).get("id") in self.ids]
        observed = datetime.now(UTC)
        saved = {"data": data, "observed_at": observed.isoformat()}
        self.cache.set(key, saved, ttl)
        return data, observed

    def _fixture(self, item, observed):
        league = item["league"]
        slug = self.ids.get(league.get("id"))
        if not slug:
            return None
        native = item["fixture"]
        if type(native.get("id")) is not int or native["id"] <= 0:
            raise ValueError("Invalid provider fixture identity")
        if league.get("country") and normalize(league["country"]) != normalize(EUROPEAN_LEAGUES[slug]["country"]):
            raise ValueError("Fixture country differs from verified league")
        state = native.get("status", {}).get("short")
        if state not in STATUS:
            raise ValueError("Unresolved fixture status")
        kickoff = aware_time(native.get("date"))
        teams = item["teams"]
        if not all(isinstance(teams.get(s, {}).get("id"), int) and teams[s]["id"] > 0 for s in ("home", "away")):
            raise ValueError("Unresolved provider team identities")
        goals = (item.get("score") or {}).get("fulltime") or (item.get("goals") if state == "FT" else {}) or {}
        finished = STATUS[state] == "finished"
        provenance = {"adapter": self.name, "source": "api-sports-v3", "observed_at": observed.isoformat(),
            "provider_updated_at": None, "season": league.get("season"), "id_namespace": "api-football",
            "result_time_basis": "first_observed_final" if finished else None,
            "warnings": ["Historical imports do not establish point-in-time result availability."]}
        return FixtureDTO(external_id=str(native["id"]), competition=league.get("name") or EUROPEAN_LEAGUES[slug]["name"],
            league_slug=slug, country=EUROPEAN_LEAGUES[slug]["country"], id_namespace="api-football",
            competition_external_id=str(league["id"]), home_external_id=str(teams["home"]["id"]),
            away_external_id=str(teams["away"]["id"]), home=teams["home"]["name"], away=teams["away"]["name"],
            kickoff=kickoff, status=STATUS[state], home_goals=goals.get("home") if finished else None,
            away_goals=goals.get("away") if finished else None, result_known_at=observed if finished else None,
            simulated=False, enrichment={"source": "api-sports-v3", "as_of": observed.isoformat(), "provenance": provenance})

    def _odds(self, row, item, observed):
        # Pre-match full-time markets only. No live market IDs or synthesized odds.
        if str(item.get("fixture", {}).get("id")) != row.external_id:
            raise ValueError("Odds belong to a different fixture")
        stamp = aware_time(item.get("update"))
        if stamp > observed:
            raise ValueError("Future-dated odds")
        books = sorted(item.get("bookmakers", []), key=lambda b: b.get("id", 0))
        if self.settings.api_football_bookmaker_id:
            books = [b for b in books if b.get("id") == self.settings.api_football_bookmaker_id]
        mappings = {"match winner": {"Home": "home_win", "Draw": "draw", "Away": "away_win"},
            "double chance": {"Home/Draw": "home_or_draw", "Draw/Away": "away_or_draw", "Home/Away": "home_or_away"},
            "goals over under": {"Over 2.5": "over_2_5", "Under 2.5": "under_2_5"},
            "both teams score": {"Yes": "btts_yes", "No": "btts_no"},
            "both teams to score": {"Yes": "btts_yes", "No": "btts_no"}}
        for book in books:
            quotes = {}
            for bet in book.get("bets", []):
                market = mappings.get(normalize(bet.get("name", "")), {})
                for selection in bet.get("values", []):
                    label = market.get(selection.get("value"))
                    try:
                        price = float(selection.get("odd", ""))
                    except (ValueError, TypeError):
                        continue
                    if label and math.isfinite(price) and 1 < price < 1001:
                        quotes[label] = price
            if quotes:
                row.odds, row.odds_at = quotes, stamp
                row.enrichment["provenance"]["odds"] = {"bookmaker_id": book.get("id"),
                    "bookmaker": book.get("name"), "provider_updated_at": stamp.isoformat(), "observed_at": observed.isoformat()}
                return

    def fetch(self):
        self.warnings, self.calls = [], 0
        account, observed = self._read("/status", ttl=86400)
        if not isinstance(account, dict):
            raise ProviderFailure("Invalid API-Football account status")
        subscription = account.get("subscription") or {}
        if subscription.get("active") is False:
            raise ProviderFailure("API-Football subscription is inactive")
        self.cache.set("status_summary", {"plan": subscription.get("plan"), "active": subscription.get("active"),
            "requests": account.get("requests"), "observed_at": observed.isoformat()}, 86400)
        metadata, _ = self._read("/leagues", {"current": "true"}, 86400)
        seasons = {}
        for league in metadata:
            native = league.get("league", {})
            slug = self.ids.get(native.get("id"))
            if not slug or native.get("type") != "League" or normalize(league.get("country", {}).get("name", "")) != normalize(EUROPEAN_LEAGUES[slug]["country"]):
                continue
            current = [s for s in league.get("seasons", []) if s.get("current") is True and isinstance(s.get("year"), int)]
            if len(current) == 1:
                seasons[native["id"]] = current[0]["year"]
        if not seasons:
            raise ProviderFailure("API-Football returned no verified current seasons for the configured leagues")
        for native in self.ids:
            if native not in seasons:
                self.warnings.append({"reason": "league_coverage_unavailable", "league_slug": self.ids[native]})
        rows = {}
        successful = 0

        def consume(items, observed):
            for item in items:
                try:
                    if item.get("league", {}).get("id") not in seasons:
                        continue
                    if item["league"].get("season") != seasons[item["league"]["id"]]:
                        raise ValueError("Unexpected fixture season")
                    row = self._fixture(item, observed)
                    previous = rows.get(row.external_id) if row else None
                    if row and (not previous or observed >= aware_time(previous.enrichment["provenance"]["observed_at"])):
                        if previous and previous.status == row.status == "finished" and (previous.home_goals, previous.away_goals) == (row.home_goals, row.away_goals):
                            row.result_known_at = min(previous.result_known_at, row.result_known_at)
                        rows[row.external_id] = row
                except (ValueError, KeyError, TypeError, ValidationError):
                    self.warnings.append({"reason": "invalid_or_incomplete_fixture"})

        for offset in range(-1, self.settings.api_football_days_ahead + 1):
            day = (datetime.now(UTC) + timedelta(days=offset)).date().isoformat()
            try:
                items, observed = self._read("/fixtures", {"date": day, "timezone": "UTC"}, self.settings.api_football_fixture_cache_minutes * 60)
                consume(items, observed)
                successful += 1
            except ProviderFailure as exc:
                self.warnings.append({"reason": "schedule_unavailable", "detail": str(exc), "date": day})
        if not successful:
            self.cache.set("sync_status", {"status": "unavailable", "warnings": self.warnings}, 86400)
            raise ProviderFailure("API-Football fixture access is unavailable; check current-season access and request quota")
        # Warm one uncached league history per run; cached histories cost no API calls.
        for native, season in seasons.items():
            before = self.calls
            try:
                items, observed = self._read("/fixtures", {"league": native, "season": season, "timezone": "UTC"}, 86400)
                consume(items, observed)
            except ProviderFailure as exc:
                self.warnings.append({"reason": "history_unavailable", "league_slug": self.ids[native], "detail": str(exc)})
            if self.calls > before:
                break
        now = datetime.now(UTC)
        window_end = (now + timedelta(days=self.settings.api_football_days_ahead + 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        candidates = sorted((r for r in rows.values() if r.status == "scheduled" and now < r.kickoff < window_end), key=lambda r: (r.kickoff, r.external_id))
        for row in candidates:
            try:
                items, observed = self._read("/odds", {"fixture": int(row.external_id)}, self.settings.api_football_odds_cache_minutes * 60)
                for item in items:
                    self._odds(row, item, observed)
            except RequestBudgetExceeded:
                self.warnings.append({"reason": "request_budget_reached"})
                break
            except (ProviderFailure, ValueError, TypeError, KeyError) as exc:
                self.warnings.append({"reason": "odds_unavailable", "fixture": row.external_id,
                    "detail": str(exc) if isinstance(exc, ProviderFailure) else "Invalid odds response"})
        self.cache.set("sync_status", {"status": "partial" if self.warnings else "ok", "warnings": self.warnings,
            "fixtures": len(rows), "requests": self.calls}, 86400)
        return [FixtureDTO.model_validate(row.model_dump()) for row in rows.values()]
