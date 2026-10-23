import os
from datetime import timedelta

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["JWT_SECRET"] = "test-only-secret-" + "x" * 48
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["COOKIE_SECURE"] = "false"
os.environ["DEMO_MODE"] = "false"
os.environ["SENTRY_DSN"] = ""
os.environ["MLFLOW_TRACKING_URI"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import password_hasher
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import Competition, Fixture, ModelVersion, PlatformSettings, Prediction, Team, User, utcnow


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(PlatformSettings(id=1))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def selection(db):
    now = utcnow()
    home = Team(name="Test Home", identity="test:home", country="Test")
    away = Team(name="Test Away", identity="test:away", country="Test")
    comp = Competition(name="Test League", identity="test:league", country="Test")
    db.add_all([home, away, comp])
    db.flush()
    fixture = Fixture(provider="test", external_id="one", competition_id=comp.id, home_id=home.id, away_id=away.id,
        kickoff=now + timedelta(days=1), status="scheduled", simulated=False, odds={"home_or_draw": 1.2}, odds_at=now, synced_at=now)
    model = ModelVersion(version="test-v1", approved=True, simulated=False, artifact_path="unused",
                         metrics={}, trained_until=now - timedelta(days=2))
    db.add_all([fixture, model])
    db.flush()
    prediction = Prediction(fixture=fixture, model=model, market="home_or_draw", probability=.85, raw_probability=.87,
        quality=.85, odds=1.2, odds_at=now, eligible=True, reasons=[], features={}, explanation="Test evidence", created_at=now)
    db.add(prediction)
    db.commit()
    return prediction


@pytest.fixture
def admin(db, client):
    user = User(email="admin@example.test", password_hash=password_hasher.hash("A-long-test-password"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"email": user.email, "password": "A-long-test-password"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}
