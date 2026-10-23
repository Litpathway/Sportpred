import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
import numpy as np
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.leagues import EUROPEAN_LEAGUES
from app.schemas.contracts import FixtureDTO, MARKETS


class ProviderFailure(RuntimeError):
    pass


class FixtureProvider(Protocol):
    name: str

    def fetch(self) -> list[FixtureDTO]: ...


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


class AuthorizedFixtureProvider:
    """Customer-supplied, authorized normalized JSON feed. Not a bookmaker scraper."""
    name = "authorized"

    def __init__(self, settings: Settings):
        if not settings.fixture_api_url or not settings.fixture_api_token:
            raise ProviderFailure("Authorized fixture URL and token are required")
        if not settings.fixture_api_url.startswith("https://"):
            raise ProviderFailure("Fixture provider requires HTTPS")
        self.url = settings.fixture_api_url
        self.token = settings.fixture_api_token
        self.leagues = set(settings.league_slugs)
        self.warnings: list[dict] = []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8),
           retry=retry_if_exception_type((httpx.TransportError, ProviderFailure)), reraise=True)
    def fetch(self) -> list[FixtureDTO]:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(self.url, headers={"Authorization": f"Bearer {self.token}"})
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderFailure("Provider temporarily unavailable or rate limited")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("fixtures"), list):
            raise ProviderFailure("Expected normalized {fixtures: [...]} response")
        if len(payload["fixtures"]) > 10000:
            raise ProviderFailure("Provider batch exceeds configured ingestion limit")
        rows = [FixtureDTO.model_validate(row) for row in payload["fixtures"]]
        self.warnings = []
        selected = []
        for row in rows:
            if not row.league_slug:
                raise ProviderFailure("Authorized fixtures require a canonical league_slug; map native IDs in your gateway")
            if row.simulated:
                raise ProviderFailure("Authorized feeds must supply real fixtures, not simulated records")
            country = EUROPEAN_LEAGUES[row.league_slug]["country"]
            if normalize(row.country) != normalize(country):
                raise ProviderFailure("Fixture country differs from its canonical league")
            if row.league_slug in self.leagues:
                selected.append(row)
            else:
                self.warnings.append({"reason": "league_disabled", "league_slug": row.league_slug})
        return selected


class DemoFixtureProvider:
    name = "demo"
    # Fictional identities avoid representing simulated scores as real club results.
    competitions = {
        "England": ["Northbridge FC", "Kingsport United", "Ashford City", "Westhaven", "Eastfield Rovers", "Riverton Athletic", "Oakwell FC", "Briarwood"],
        "Spain": ["Real Costa", "Atletico Sol", "Deportivo Mar", "Valle Verde", "Union Sierra", "Sporting Luna", "CD Estrella", "Puerto Azul"],
        "Germany": ["FC Neustadt", "SV Bergheim", "Union Wald", "Rot Weiss Tal", "Blau Stadt", "VfB Hohen", "TSV West", "SC Linden"],
    }

    def fetch(self) -> list[FixtureDTO]:
        rng = np.random.default_rng(42)
        now = datetime.now(UTC)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows: list[FixtureDTO] = []
        # Randomness creates reproducible synthetic score data only. All probabilities
        # are subsequently learned/calculated from those results, never invented.
        for country, teams in self.competitions.items():
            for round_no in range(84):
                order = rng.permutation(8)
                for match_no in range(4):
                    h, a = map(int, order[2 * match_no:2 * match_no + 2])
                    kickoff = today - timedelta(days=(85 - round_no) * 3, hours=-15 - match_no)
                    attack_h, attack_a = 2.8 - h * .30, 2.8 - a * .30
                    hg = int(rng.poisson(max(.15, attack_h * (0.7 + a * .08) * 1.15)))
                    ag = int(rng.poisson(max(.15, attack_a * (0.7 + h * .08) * .85)))
                    rows.append(FixtureDTO(
                        external_id=f"history-{country}-{round_no}-{match_no}", competition=f"{country} Demo League",
                        country=country, home=teams[h], away=teams[a], kickoff=kickoff, status="finished",
                        home_goals=hg, away_goals=ag, result_known_at=kickoff + timedelta(hours=2), simulated=True,
                    ))
            for match_no, (h, a) in enumerate([(0, 7), (1, 6), (2, 5), (3, 4)]):
                kickoff = today + timedelta(days=1, hours=15 + match_no)
                rows.append(FixtureDTO(
                    external_id=f"upcoming-{country}-{today.date()}-{match_no}", competition=f"{country} Demo League",
                    country=country, home=teams[h], away=teams[a], kickoff=kickoff, status="scheduled", simulated=True,
                    # Demonstration quotes, deliberately independent of model probabilities.
                    odds=dict(zip(MARKETS, [1.48, 4.2, 6.1, 1.14, 2.5, 1.22, 1.8, 2.02, 1.9, 1.9], strict=True)),
                    odds_at=now, enrichment={"source": "simulated", "as_of": now.isoformat()},
                ))
        return rows


def fixture_provider(settings: Settings) -> FixtureProvider:
    if settings.fixture_provider == "api_football":
        from app.providers.api_football import ApiFootballProvider
        return ApiFootballProvider(settings)
    if settings.fixture_provider == "sports_skills":
        from app.providers.sports_skills import SportsSkillsFixtureProvider
        return SportsSkillsFixtureProvider(settings)
    if settings.fixture_provider == "demo" and settings.demo_mode:
        return DemoFixtureProvider()
    if settings.fixture_provider == "authorized":
        return AuthorizedFixtureProvider(settings)
    raise ProviderFailure("Provider disabled or not configured; demo requires DEMO_MODE=true")
