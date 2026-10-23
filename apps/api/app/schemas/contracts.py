from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.leagues import EUROPEAN_LEAGUES

MARKETS = ("home_win", "draw", "away_win", "home_or_draw", "away_or_draw", "home_or_away",
           "over_2_5", "under_2_5", "btts_yes", "btts_no")
MARKET_LABELS = {
    "home_win": "Home win", "draw": "Draw", "away_win": "Away win",
    "home_or_draw": "Home or draw", "away_or_draw": "Away or draw", "home_or_away": "Either team wins",
    "over_2_5": "Over 2.5 goals", "under_2_5": "Under 2.5 goals",
    "btts_yes": "Both teams to score", "btts_no": "Both teams to score — No",
}


class EnrichmentDTO(BaseModel):
    source: str | None = Field(default=None, max_length=100)
    as_of: datetime | None = None
    xg: dict[Literal["home", "away"], float] | None = None
    shots: dict[Literal["home", "away"], int] | None = None
    defensive_stats: dict[Literal["home", "away"], dict[str, float]] | None = None
    injuries: dict[Literal["home", "away"], list[str]] | None = None
    suspensions: dict[Literal["home", "away"], list[str]] | None = None
    lineups: dict[Literal["home", "away"], list[str]] | None = None
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def timestamps_and_ranges(self):
        supplied = any(getattr(self, key) is not None for key in ("xg", "shots", "defensive_stats", "injuries", "suspensions", "lineups"))
        if supplied and (not self.as_of or self.as_of.tzinfo is None):
            raise ValueError("Enrichment requires a timezone-aware as_of timestamp")
        for key in ("xg", "shots"):
            values = getattr(self, key)
            if values and any(v < 0 or v > 1000 for v in values.values()):
                raise ValueError("Invalid enrichment statistic")
        return self


class FixtureDTO(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    competition: str = Field(min_length=1, max_length=150)
    league_slug: str | None = Field(default=None, max_length=60)
    country: str = Field(min_length=1, max_length=60)
    home: str = Field(min_length=1, max_length=150)
    away: str = Field(min_length=1, max_length=150)
    id_namespace: str | None = Field(default=None, pattern=r"^[a-z0-9._-]{1,40}$")
    home_external_id: str | None = Field(default=None, min_length=1, max_length=120)
    away_external_id: str | None = Field(default=None, min_length=1, max_length=120)
    competition_external_id: str | None = Field(default=None, min_length=1, max_length=120)
    kickoff: datetime
    status: Literal["scheduled", "live", "finished", "cancelled", "postponed"]
    home_goals: int | None = Field(default=None, ge=0, le=50)
    away_goals: int | None = Field(default=None, ge=0, le=50)
    result_known_at: datetime | None = None
    simulated: bool = False
    odds: dict[str, float] = Field(default_factory=dict)
    odds_at: datetime | None = None
    enrichment: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check(self):
        if self.league_slug and self.league_slug not in EUROPEAN_LEAGUES:
            raise ValueError("Unknown canonical league_slug")
        self.enrichment = EnrichmentDTO.model_validate(self.enrichment).model_dump(mode="json", exclude_none=True)
        if (self.home_external_id or self.away_external_id) and not (self.id_namespace and self.home_external_id and self.away_external_id):
            raise ValueError("Provider team identities require both IDs and their namespace")
        if self.home.strip().casefold() == self.away.strip().casefold():
            raise ValueError("A team cannot play itself")
        if self.status == "finished" and (self.home_goals is None or self.away_goals is None or self.result_known_at is None):
            raise ValueError("Finished fixtures require scores and result availability timestamp")
        if self.kickoff.tzinfo is None:
            raise ValueError("Provider timestamps must include timezone")
        for stamp in (self.odds_at, self.result_known_at):
            if stamp is not None and stamp.tzinfo is None:
                raise ValueError("Provider timestamps must include timezone")
        if self.result_known_at and self.result_known_at < self.kickoff:
            raise ValueError("Result cannot be known before kickoff")
        if any(k not in MARKETS or not 1 < v < 1001 for k, v in self.odds.items()):
            raise ValueError("Invalid decimal odds or unsupported market")
        if self.odds and not self.odds_at:
            raise ValueError("Odds require a timestamp")
        return self


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SettingsInput(BaseModel):
    threshold: float = Field(ge=0.5, le=0.99)
    min_quality: float = Field(ge=0.5, le=1)
    publication_paused: bool
    max_legs: int = Field(ge=1, le=3)
    provider_enabled: bool


class SlipInput(BaseModel):
    prediction_ids: list[int] = Field(min_length=1, max_length=3)


class ClearDataInput(BaseModel):
    confirmation: Literal["CLEAR ALL DATA"]


class ApprovalInput(BaseModel):
    approved: bool
