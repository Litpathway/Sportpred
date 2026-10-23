import argparse
import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import password_hasher
from app.db.session import SessionLocal
from app.models.entities import AuditLog, User
from app.providers.booking import booking_provider
from app.providers.fixtures import fixture_provider
from app.services.ingestion import sync_fixtures
from app.services.predictions import generate_predictions, refilter, train_and_register
from app.services.publication import publish_candidates


def main():
    parser = argparse.ArgumentParser(description="SportPredict operator commands")
    parser.add_argument("command", choices=["create-admin", "seed-demo", "sync", "train", "pipeline"])
    parser.add_argument("--approve-demo", action="store_true", help="Explicitly approve simulated model for demo use only")
    args = parser.parse_args()
    settings = get_settings()
    with SessionLocal() as db:
        if args.command in {"create-admin", "seed-demo"}:
            if not settings.admin_password or len(settings.admin_password) < 12:
                parser.error("Set ADMIN_PASSWORD to a unique password of at least 12 characters")
            email = settings.admin_email.strip().casefold()
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, password_hash=password_hasher.hash(settings.admin_password), role="admin"))
                db.commit()
            print("Admin account exists; existing passwords are not overwritten.")
        if args.command == "seed-demo":
            if not settings.demo_mode or settings.fixture_provider != "demo":
                parser.error("seed-demo requires DEMO_MODE=true and FIXTURE_PROVIDER=demo")
            print(sync_fixtures(db, fixture_provider(settings)))
            model = train_and_register(db)
            if args.approve_demo:
                model.approved = True
                db.add(AuditLog(action="model.approval", actor="demo-cli", entity=str(model.id), detail={"simulated": True}))
                db.commit()
            print(generate_predictions(db))
            print(publish_candidates(db, booking_provider(settings)))
        if args.command == "train":
            model = train_and_register(db)
            print({"model_id": model.id, "version": model.version, "approved": model.approved})
        if args.command == "sync":
            print(sync_fixtures(db, fixture_provider(settings)))
        if args.command == "pipeline":
            from app.workers.tasks import execute_job
            print(execute_job("pipeline", db))


if __name__ == "__main__":
    main()
