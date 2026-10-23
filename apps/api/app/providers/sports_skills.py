"""Read-only, personal/research integration with Machina's football-data skill.

Source reviewed at bdb972c0625fa337e15f18ca58abd28f57f25e37 (MIT).
Public-source data rights are separate from the wrapper's code licence.
"""
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.leagues import EUROPEAN_LEAGUES
from app.providers.fixtures import ProviderFailure
from app.schemas.contracts import FixtureDTO

UPSTREAM_COMMIT = "bdb972c0625fa337e15f18ca58abd28f57f25e37"
COUNTRIES = {**{slug: league["country"] for slug, league in EUROPEAN_LEAGUES.items()},
             "championship": "England", "mls": "United States", "champions-league": "Europe", "serie-a-brazil": "Brazil"}
STATUS = {"not_started": "scheduled", "live": "live", "halftime": "live", "closed": "finished",
          "postponed": "postponed", "cancelled": "cancelled", "canceled": "cancelled"}
RIGHTS = {"data_class": "open-public", "prototype_only": True, "commercial_use": False}


class SportsSkillsFixtureProvider:
    name = "sports_skills"

    def __init__(self, settings: Settings, sdk: Any = None):
        # Gate before imports, clients, or network activity. The public SDK does
        # not grant production data rights even if a user changes other flags.
        if settings.environment == "production" or not settings.sports_skills_personal_use:
            raise ProviderFailure("sports-skills public feeds require personal/research opt-in and cannot run in production; configure an authorized licensed feed")
        if settings.demo_mode:
            raise ProviderFailure("Set DEMO_MODE=false for public research data; simulated models cannot be used on real fixtures")
        if sdk is None:
            try:
                from sports_skills import football
            except ImportError:
                raise ProviderFailure("Install the optional API [sports] dependency to enable sports-skills") from None
            sdk = football
        self.sdk, self.settings = sdk, settings
        self.competitions = [c.strip() for c in settings.sports_skills_competitions.split(",") if c.strip()]
        if not 1 <= len(self.competitions) <= 10 or len(set(self.competitions)) != len(self.competitions) or any(c not in COUNTRIES for c in self.competitions):
            raise ProviderFailure("Select one to ten unique supported competition slugs; see integration documentation")
        self.warnings: list[dict] = []
        self.seasons: dict[str, str] = {}

    def _read(self, command: str, **kwargs) -> dict:
        # Fixed read-only method set: no CLI, arbitrary command routing, premium
        # setup, wallet, trading, betting, or other sports modules.
        allowed = {"get_current_season", "get_season_schedule", "get_daily_schedule", "get_event_lineups"}
        if command not in allowed:
            raise ProviderFailure("Unsupported read-only football command")
        for attempt in range(3):
            try:
                response = getattr(self.sdk, command)(**kwargs)
            except Exception as exc:
                if attempt == 2:
                    raise ProviderFailure(f"sports-skills request failed ({type(exc).__name__})") from None
                time.sleep(2 ** attempt)
                continue
            if isinstance(response, dict) and response.get("status") is True and isinstance(response.get("data"), dict):
                return response["data"]
            code = response.get("status_code") if isinstance(response, dict) else None
            if code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ProviderFailure("sports-skills returned unavailable, unsupported, or invalid data")
        raise ProviderFailure("sports-skills retry limit reached")

    def _event(self, event: dict, source: str, observed_at: datetime) -> FixtureDTO:
        competition_id = event.get("competition", {}).get("id")
        if competition_id not in self.seasons:
            raise ValueError("Unrequested competition")
        if event.get("season", {}).get("id") != self.seasons[competition_id]:
            raise ValueError("Fixture season differs from discovered active season")
        start = event.get("start_time")
        if not isinstance(start, str) or "T" not in start:
            # Date-only fallback schedules must never become invented midnight kickoffs.
            raise ValueError("Unresolved kickoff time")
        kickoff = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            raise ValueError("Unresolved kickoff timezone")
        status = STATUS.get(event.get("status"))
        if status is None:
            raise ValueError("Unsupported fixture status")
        participants = event.get("competitors", [])
        home = next((p for p in participants if p.get("qualifier") == "home"), None)
        away = next((p for p in participants if p.get("qualifier") == "away"), None)
        if not home or not away:
            raise ValueError("Unresolved participants")
        hteam, ateam = home.get("team", {}), away.get("team", {})
        native_ids = str(hteam.get("id", "")), str(ateam.get("id", ""))
        # Openfootball fallback IDs are provider-local slug strings, never ESPN IDs.
        namespace = "openfootball" if source == "openfootball" else "espn"
        if namespace == "espn" and (not all(i.isdigit() for i in native_ids) or not str(event.get("id", "")).isdigit()):
            raise ValueError("Invalid provider-native ESPN IDs")
        provenance = {"adapter": self.name, "upstream_commit": UPSTREAM_COMMIT, "source": source,
            "observed_at": observed_at.isoformat(), "provider_updated_at": None,
            "result_time_basis": "first_observed_final" if status == "finished" else None,
            "season_id": event.get("season", {}).get("id"), "id_namespace": namespace,
            "rights": RIGHTS, "coverage": "unverified; a successful response does not prove complete coverage",
            "warnings": ["Public research feed; post-match updates, no live-score SLA.",
                         "No provider odds in this integration; no publication eligibility without fresh authorized quotes."]}
        return FixtureDTO(external_id=f"{namespace}:{event['id']}", competition=event["competition"].get("name") or competition_id,
            country=COUNTRIES[competition_id], league_slug=competition_id if competition_id in EUROPEAN_LEAGUES else None,
            home=hteam.get("name", ""), away=ateam.get("name", ""),
            id_namespace=namespace, home_external_id=native_ids[0], away_external_id=native_ids[1],
            competition_external_id=competition_id, kickoff=kickoff, status=status, simulated=False,
            home_goals=home.get("score") if status == "finished" else None,
            away_goals=away.get("score") if status == "finished" else None,
            # Observed final timestamp, not a fabricated kickoff+2h availability.
            result_known_at=observed_at if status == "finished" else None, odds={}, odds_at=None,
            enrichment={"source": source, "as_of": observed_at.isoformat(), "provenance": provenance})

    def _lineups(self, row: FixtureDTO, event: dict, observed: datetime) -> None:
        if not row.external_id.startswith("espn:"):
            return
        data = self._read("get_event_lineups", event_id=str(event["id"]))
        teams = {row.home_external_id: "home", row.away_external_id: "away"}
        lineups = {}
        for team in data.get("lineups", []):
            side = teams.get(str(team.get("team", {}).get("id", "")))
            players = team.get("starting", [])
            names = [p.get("player", {}).get("name") or p.get("name") for p in players if isinstance(p, dict)]
            if side and len(names) == 11 and all(isinstance(n, str) and n for n in names):
                lineups[side] = names
        if set(lineups) == {"home", "away"}:
            row.enrichment = {**row.enrichment, "lineups": lineups}

    def fetch(self) -> list[FixtureDTO]:
        observed = datetime.now(UTC)
        self.warnings, self.seasons = [], {}
        batches: list[tuple[list, str]] = []
        failures = 0
        # Seasons are always discovered, never guessed from the wall clock.
        for competition in self.competitions:
            try:
                current = self._read("get_current_season", competition_id=competition)
                season_id = current.get("season", {}).get("id")
                if not season_id or current.get("estimated"):
                    raise ProviderFailure("Current season identity is unavailable or estimated")
                self.seasons[competition] = season_id
                if self.settings.sports_skills_history:
                    data = self._read("get_season_schedule", season_id=season_id)
                    batches.append((data.get("schedules", []), data.get("source", "espn")))
            except ProviderFailure:
                failures += 1
                self.warnings.append({"competition": competition, "reason": "season_or_history_unavailable"})
        for day in range(self.settings.sports_skills_days_ahead):
            try:
                data = self._read("get_daily_schedule", date=(observed + timedelta(days=day)).date().isoformat())
                batches.append((data.get("events", []), data.get("source", "espn")))
            except ProviderFailure:
                failures += 1
                self.warnings.append({"reason": "daily_schedule_unavailable", "day_offset": day})
        if not batches:
            raise ProviderFailure("sports-skills fixture sources are unavailable")
        rows: dict[str, FixtureDTO] = {}
        for events, source in batches:
            if source != "espn":
                self.warnings.append({"reason": "fallback_source_declined", "source": source})
                continue
            if not isinstance(events, list):
                raise ProviderFailure("Invalid schedule list")
            for event in events:
                if not isinstance(event, dict) or event.get("competition", {}).get("id") not in self.competitions:
                    continue
                try:
                    row = self._event(event, source, observed)
                except (ValueError, KeyError, TypeError, ValidationError):
                    self.warnings.append({"reason": "invalid_or_incomplete_event"})
                    continue
                # Final scores from ESPN are authoritative; do not overwrite a
                # final record with an upcoming copy from a daily fixture feed.
                previous = rows.get(row.external_id)
                if not previous or previous.status != "finished":
                    rows[row.external_id] = row
        candidates = sorted((r for r in rows.values() if r.status == "scheduled" and r.kickoff > observed), key=lambda r:r.kickoff)
        for row in candidates[:self.settings.sports_skills_enrich_limit]:
            try:
                self._lineups(row, {"id": row.external_id.split(":", 1)[1]}, observed)
            except ProviderFailure:
                self.warnings.append({"reason": "lineup_unavailable", "fixture": row.external_id})
        return [FixtureDTO.model_validate(row.model_dump()) for row in rows.values()]
