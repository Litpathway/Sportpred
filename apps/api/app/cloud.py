"""Container entrypoints for Vercel services and production-only daemons."""
import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import password_hasher
from app.db.session import SessionLocal, engine, make_engine
from app.models.entities import User

SCHEMA_LOCK = 734200819


def bootstrap():
    settings = get_settings()
    if not settings.admin_password or len(settings.admin_password) < 12:
        raise ValueError("Set a unique ADMIN_PASSWORD of at least 12 characters")
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    # The session-level PostgreSQL lock also serializes first-admin creation.
    # Every API cold start and daemon rollout uses the same migration lock.
    migration_engine = make_engine(settings.database_url_unpooled) if settings.database_url_unpooled else engine
    with migration_engine.connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": SCHEMA_LOCK})
            connection.commit()
        try:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            with SessionLocal() as db:
                email = settings.admin_email.strip().casefold()
                if not db.scalar(select(User).where(User.email == email)):
                    db.add(User(email=email, password_hash=password_hasher.hash(settings.admin_password), role="admin"))
                    db.commit()
        finally:
            if postgres:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEMA_LOCK})
                connection.commit()


def process_command(role: str) -> list[str]:
    if role == "api":
        return ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
                "--port", os.environ.get("PORT", "80"), "--proxy-headers", "--no-access-log"]
    base = ["celery", "-A", "app.workers.celery_app:celery"]
    if role == "worker":
        return [*base, "worker", "--loglevel=info", "--concurrency=1"]
    if role == "scheduler":
        return [*base, "beat", "--loglevel=info", "--schedule=/tmp/sportpredict-beat"]
    raise ValueError("Unknown cloud role")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["api", "worker", "scheduler"])
    role = parser.parse_args().role
    settings = get_settings()
    if settings.environment != "production" or settings.demo_mode or settings.fixture_provider not in {"authorized", "api_football"}:
        raise ValueError("Cloud deployment requires production, real data and an authorized or api_football provider")
    if any(not origin.startswith("https://") for origin in settings.origins) or not settings.origins:
        raise ValueError("ALLOWED_ORIGINS must contain the exact HTTPS site origin")
    bootstrap()
    args = process_command(role)
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
