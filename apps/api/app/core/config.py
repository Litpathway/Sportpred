from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.leagues import DEFAULT_LEAGUES, EUROPEAN_LEAGUES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./sportpredict.db"
    redis_url: str = "redis://localhost:6379/0"
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
