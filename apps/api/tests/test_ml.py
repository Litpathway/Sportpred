from datetime import timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.ml.engine import InsufficientData, chronological_split, load_artifact, outcomes, poisson_markets, predict, save_artifact, train_model
from app.ml.features import features_for
from app.models.entities import Fixture
from app.providers.fixtures import DemoFixtureProvider
from app.services.ingestion import sync_fixtures


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.session import Base
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        sync_fixtures(db,DemoFixtureProvider())
        history = list(db.scalars(select(Fixture).where(Fixture.status=="finished").order_by(Fixture.kickoff)))
        artifact, metrics = train_model(history,simulated=True)
        yield artifact, metrics, history
    engine.dispose()


def test_poisson_probabilities_are_normalized_and_complements():
    p = poisson_markets(1.8,.8)
    assert p["home_win"]+p["draw"]+p["away_win"] == pytest.approx(1)
    assert p["over_2_5"]+p["under_2_5"] == pytest.approx(1)
    assert p["btts_yes"]+p["btts_no"] == pytest.approx(1)
    assert p["home_or_draw"] == pytest.approx(p["home_win"]+p["draw"])


def test_insufficient_history_is_explicit():
    with pytest.raises(InsufficientData): train_model([],simulated=True)


def test_backtest_splits_are_strictly_chronological(trained):
    artifact,metrics,history=trained
    splits=metrics["splits"]
    assert splits["train"]["end"] < splits["validation"]["start"]
    assert splits["validation"]["end"] < splits["test"]["start"]
    assert artifact["trained_until"] < artifact["evaluated_until"]
    train,val,test=chronological_split(history)
    assert max(f.result_known_at for f in train) < min(f.kickoff for f in val)
    assert max(f.result_known_at for f in val) < min(f.kickoff for f in test)


def test_feature_snapshot_excludes_future_information(trained):
    _,_,history=trained
    fixture=history[len(history)//2]
    before=features_for(fixture,history)
    future=history[-1]
    original=future.home_goals
    future.home_goals=49
    after=features_for(fixture,history)
    future.home_goals=original
    assert before.values == after.values
    assert future.id not in before.detail["history_ids"]
    assert fixture.id not in before.detail["history_ids"]


def test_delayed_results_are_excluded(trained):
    _,_,history=trained
    fixture=history[-1]
    before=features_for(fixture,history)
    selected=next(f for f in history if f.id in before.detail["history_ids"])
    original=selected.result_known_at
    selected.result_known_at=fixture.kickoff+timedelta(days=1)
    after=features_for(fixture,history)
    selected.result_known_at=original
    assert selected.id not in after.detail["history_ids"]


def test_calibrated_predictions_and_metrics_are_computed(trained):
    artifact,metrics,history=trained
    features=features_for(history[-1],history)
    result=predict(artifact,features.values)
    assert len(result)==10 and all(0<p<1 for p,raw in result.values())
    assert 0<metrics["brier"]<1 and metrics["test_rows"]>=30
    for market,metric in metrics["markets"].items():
        assert len(metric["calibration"])>1 and metric["log_loss"]>0
    assert artifact["calibrators"]["home_win"].coef_.shape==(1,1)


def test_artifact_roundtrip_and_tampering(trained,tmp_path):
    artifact,_,history=trained
    path=tmp_path/"model.joblib"
    digest=save_artifact(artifact,path)
    loaded=load_artifact(path,digest)
    values=features_for(history[-1],history).values
    assert predict(loaded,values)==predict(artifact,values)
    path.write_bytes(path.read_bytes()+b"tampering")
    with pytest.raises(ValueError,match="integrity"):load_artifact(path,digest)


def test_reproducible_training(trained):
    first,metrics,history=trained
    second,again=train_model(history,simulated=True)
    values=features_for(history[-1],history).values
    assert predict(first,values)==predict(second,values)
    assert metrics["brier"]==again["brier"]


def test_registered_artifact_is_shared_and_verified_without_local_files(trained, db, monkeypatch):
    from sqlalchemy.orm import Session
    from app.core.config import get_settings
    from app.models.entities import ModelVersion
    from app.services.predictions import generate_predictions, train_and_register
    import app.services.predictions as service
    artifact, metrics, _ = trained
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(service, "train_model", lambda *args, **kwargs: (artifact, dict(metrics)))
    sync_fixtures(db, DemoFixtureProvider())
    model = train_and_register(db)
    assert model.artifact_path.startswith("database://") and model.artifact_data
    model.approved = True
    db.commit()
    with Session(db.get_bind()) as another_process:
        assert generate_predictions(another_process)["created"] == 120
        stored = another_process.get(ModelVersion, model.id)
        stored.artifact_data += b"tampered"
        another_process.commit()
        with pytest.raises(ValueError, match="integrity"):
            generate_predictions(another_process)


def test_scheduled_inference_preserves_quotes_and_is_idempotent_per_window(trained, db, tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.models.entities import ModelVersion, Prediction, utcnow
    from app.services.predictions import generate_predictions, refilter
    import app.services.predictions as service
    artifact, metrics, _ = trained
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    sync_fixtures(db, DemoFixtureProvider())
    path=tmp_path/"scheduled.joblib"
    digest=save_artifact(artifact,path)
    version=ModelVersion(version="scheduled-test",approved=True,simulated=True,artifact_path=str(path),
                         trained_until=artifact["trained_until"],metrics={**metrics,"sha256":digest})
    db.add(version);db.commit()
    now=utcnow()
    monkeypatch.setattr(service,"utcnow",lambda:now)
    assert generate_predictions(db)["created"]==120
    assert generate_predictions(db)["created"]==0
    original=db.scalar(select(Prediction).where(Prediction.market=="home_win"))
    original_odds=original.odds
    later=now+timedelta(minutes=16)
    monkeypatch.setattr(service,"utcnow",lambda:later)
    for fixture in db.scalars(select(Fixture).where(Fixture.status=="scheduled")):
        fixture.odds={**fixture.odds,"home_win":1.9}
        fixture.odds_at=later
    db.commit()
    assert generate_predictions(db)["created"]==120
    refilter(db)
    assert original.odds==original_odds and original.odds_at<later
    latest=db.scalar(select(Prediction).where(Prediction.fixture_id==original.fixture_id,Prediction.market=="home_win").order_by(Prediction.id.desc()))
    assert latest.odds==1.9 and latest.generation!=original.generation
