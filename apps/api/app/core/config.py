from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.leagues import DEFAULT_LEAGUES, EUROPEAN_LEAGUES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore", hide_input_in_errors=True, populate_by_name=True)
    environment: str = "development"
    database_url: str = Field(default="sqlite:///./sportpredict.db", validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"))
    database_url_unpooled: str | None = Field(default=None, validation_alias=AliasChoices("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING"))
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias=AliasChoices("REDIS_URL", "KV_URL", "UPSTASH_REDIS_URL"))
    jwt_secret: str = Field(min_length=32)
    token_minutes: int = Field(default=60, ge=5, le=480)
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cookie_secure: bool = False
    demo_mode: bool = True
    admin_email: str = "admin@example.test"
    admin_password: str | None = None
    artifact_dir: Path = Path("artifacts")
    fixture_provider: str = "demo"
    fixture_api_url: str | None = None
    fixture_api_token: str | None = None
    api_football_key: SecretStr | None = None
    api_football_days_ahead: int = Field(default=1, ge=1, le=7)
    api_football_max_requests: int = Field(default=20, ge=1, le=100)
    api_football_daily_budget: int = Field(default=90, ge=1, le=150000)
    api_football_bookmaker_id: int | None = Field(default=None, ge=1)
    api_football_fixture_cache_minutes: int = Field(default=60, ge=5, le=360)
    api_football_odds_cache_minutes: int = Field(default=180, ge=5, le=360)
    sportybet_odds_enabled: bool = False
    sportybet_region: str = Field(default="ng", pattern=r"^[a-z]{2}$")
    sportybet_cache_seconds: int = Field(default=300, ge=90, le=3600)
    pipeline_interval_minutes: int = Field(default=15, ge=5, le=360)
    enabled_leagues: str = DEFAULT_LEAGUES
    sports_skills_personal_use: bool = False
    sports_skills_competitions: str = "premier-league"
    sports_skills_days_ahead: int = Field(default=3, ge=1, le=7)
    sports_skills_history: bool = False
    sports_skills_enrich_limit: int = Field(default=4, ge=0, le=12)
    booking_provider: str = "unavailable"
    booking_api_url: str | None = None
    booking_api_token: str | None = None
    mlflow_tracking_uri: str | None = None
    sentry_dsn: str | None = None
    alert_webhook_url: str | None = None

    @field_validator("database_url", "database_url_unpooled", mode="before")
    @classmethod
    def postgres_driver(cls, value):
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @model_validator(mode="after")
    def production_checks(self):
        leagues = self.league_slugs
        if not leagues or len(leagues) != len(set(leagues)) or any(s not in EUROPEAN_LEAGUES for s in leagues):
            raise ValueError("ENABLED_LEAGUES must contain unique supported European league slugs")
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL")
        return self

    @property
    def league_slugs(self) -> list[str]:
        return [s.strip() for s in self.enabled_leagues.split(",") if s.strip()]

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
