from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    # UTC-naive storage makes SQLite/PostgreSQL comparisons identical. API adds Z.
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    identity: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str] = mapped_column(String(60))


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    identity: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str] = mapped_column(String(60))
    league_slug: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint("provider", "external_id"),
        UniqueConstraint("competition_id", "home_id", "away_id", "kickoff"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(120))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    home_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_known_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    odds: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    odds_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enrichment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    home: Mapped[Team] = relationship(foreign_keys=[home_id])
    away: Mapped[Team] = relationship(foreign_keys=[away_id])
    competition: Mapped[Competition] = relationship()


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_path: Mapped[str] = mapped_column(Text)
    artifact_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    trained_until: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("fixture_id", "model_id", "market", "generation", name="uq_prediction_generation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    market: Mapped[str] = mapped_column(String(40))
    generation: Mapped[str] = mapped_column(String(40), default="initial", server_default="initial")
    probability: Mapped[float] = mapped_column(Float)
    raw_probability: Mapped[float] = mapped_column(Float)
    quality: Mapped[float] = mapped_column(Float)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fixture: Mapped[Fixture] = relationship()
    model: Mapped[ModelVersion] = relationship()


class Slip(Base):
    __tablename__ = "slips"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    prediction_ids: Mapped[list[int]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    joint_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    combined_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    assumption: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    code_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    threshold: Mapped[float] = mapped_column(Float, default=0.80)
    min_quality: Mapped[float] = mapped_column(Float, default=0.7)
    publication_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    max_legs: Mapped[int] = mapped_column(Integer, default=1)
    provider_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(254), default="system")
    entity: Mapped[str] = mapped_column(String(150))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(150), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    identity: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
