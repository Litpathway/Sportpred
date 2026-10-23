import hashlib
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import poisson
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.ml.features import FEATURE_NAMES, features_for
from app.models.entities import Fixture
from app.schemas.contracts import MARKETS


class InsufficientData(ValueError):
    pass


def outcomes(home: int, away: int) -> dict[str, int]:
    return dict(zip(MARKETS, map(int, [home > away, home == away, home < away, home >= away,
                home <= away, home != away, home + away > 2, home + away < 3,
                home > 0 and away > 0, home == 0 or away == 0]), strict=True))


def poisson_markets(home_rate: float, away_rate: float) -> dict[str, float]:
    h, a = np.arange(25)[:, None], np.arange(25)[None, :]
    joint = poisson.pmf(h, np.clip(home_rate, .05, 8)) * poisson.pmf(a, np.clip(away_rate, .05, 8))
    joint /= joint.sum()
    masks = [h > a, h == a, h < a, h >= a, h <= a, h != a, h + a > 2, h + a < 3,
             (h > 0) & (a > 0), (h == 0) | (a == 0)]
    return {market: float(joint[mask].sum()) for market, mask in zip(MARKETS, masks, strict=True)}


def chronological_split(fixtures: list[Fixture]) -> tuple[list, list, list]:
    times = sorted({f.kickoff for f in fixtures})
    if len(times) < 30:
        raise InsufficientData("At least 30 distinct historical kickoff times are required")
    a, b = times[int(len(times) * .6)], times[int(len(times) * .8)]
    train = [f for f in fixtures if f.kickoff < a and f.result_known_at < a]
    val = [f for f in fixtures if a <= f.kickoff < b and f.result_known_at < b]
    test = [f for f in fixtures if f.kickoff >= b]
    return train, val, test


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def evaluate(y: np.ndarray, probabilities: np.ndarray) -> dict:
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    observed, predicted = calibration_curve(y, p, n_bins=10, strategy="uniform")
    return {"n": len(y), "brier": float(brier_score_loss(y, p)),
            "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "accuracy": float(accuracy_score(y, p >= .5)),
            "calibration": [{"predicted": float(x), "observed": float(z)} for x, z in zip(predicted, observed, strict=True)]}


def raw_probabilities(artifact: dict, x: np.ndarray) -> dict[str, np.ndarray]:
    hr, ar = artifact["home"].predict(x), artifact["away"].predict(x)
    baseline = [poisson_markets(h, a) for h, a in zip(hr, ar, strict=True)]
    return {m: .5 * np.array([b[m] for b in baseline]) + .5 * artifact["classifiers"][m].predict_proba(x)[:, 1]
            for m in MARKETS}


def train_model(history: list[Fixture], simulated: bool) -> tuple[dict, dict]:
    history = sorted([f for f in history if f.status == "finished" and f.result_known_at
                      and f.simulated == simulated], key=lambda f: (f.kickoff, f.id))
    feature_map = {f.id: features_for(f, history) for f in history}
    usable = [f for f in history if feature_map[f.id] is not None]
    if len(usable) < 180:
        raise InsufficientData(f"Need 180 historical fixtures with pre-match features; found {len(usable)}")
    train, val, test = chronological_split(usable)
    if min(map(len, (train, val, test))) < 30:
        raise InsufficientData("Chronological splits need at least 30 examples each")
    xs = [np.array([feature_map[f.id].values for f in block]) for block in (train, val, test)]
    ys = [{m: np.array([outcomes(f.home_goals, f.away_goals)[m] for f in block]) for m in MARKETS}
          for block in (train, val, test)]
    artifact = {"feature_names": FEATURE_NAMES, "classifiers": {}, "calibrators": {}, "simulated": simulated}
    for side in ("home", "away"):
        model = make_pipeline(StandardScaler(), PoissonRegressor(alpha=.1, max_iter=500))
        model.fit(xs[0], np.array([getattr(f, f"{side}_goals") for f in train]))
        artifact[side] = model
    for market in MARKETS:
        if any(len(np.unique(y[market])) < 2 for y in ys):
            raise InsufficientData(f"Both outcomes required in each split for {market}")
        model = XGBClassifier(n_estimators=70, max_depth=2, learning_rate=.05, subsample=1,
                              colsample_bytree=1, random_state=42, n_jobs=1, eval_metric="logloss")
        model.fit(xs[0], ys[0][market])
        artifact["classifiers"][market] = model
    val_raw, test_raw = raw_probabilities(artifact, xs[1]), raw_probabilities(artifact, xs[2])
    metrics = {"markets": {}, "splits": {}, "seed": 42, "training_rows": len(train), "validation_rows": len(val),
               "test_rows": len(test), "feature_names": FEATURE_NAMES, "algorithm": "Poisson + XGBoost, sigmoid calibration",
               "simulation": simulated, "limitations": "Binary markets calibrated separately; not a coherent joint distribution."}
    for name, block in zip(("train", "validation", "test"), (train, val, test), strict=True):
        metrics["splits"][name] = {"start": block[0].kickoff.isoformat(), "end": block[-1].kickoff.isoformat(),
                                  "result_cutoff": max(f.result_known_at for f in block).isoformat()}
    for market in MARKETS:
        calibrator = LogisticRegression(C=1., random_state=42)
        calibrator.fit(_logit(val_raw[market]), ys[1][market])
        artifact["calibrators"][market] = calibrator
        calibrated = calibrator.predict_proba(_logit(test_raw[market]))[:, 1]
        metrics["markets"][market] = evaluate(ys[2][market], calibrated)
        metrics["markets"][market]["uncalibrated"] = evaluate(ys[2][market], test_raw[market])
    metrics["brier"] = float(np.mean([m["brier"] for m in metrics["markets"].values()]))
    metrics["log_loss"] = float(np.mean([m["log_loss"] for m in metrics["markets"].values()]))
    artifact["trained_until"] = max(f.result_known_at for f in train + val)
    artifact["evaluated_until"] = max(f.result_known_at for f in test)
    return artifact, metrics


def predict(artifact: dict, values: list[float]) -> dict[str, tuple[float, float]]:
    raw = raw_probabilities(artifact, np.array([values]))
    return {m: (float(artifact["calibrators"][m].predict_proba(_logit(raw[m]))[0, 1]), float(raw[m][0])) for m in MARKETS}


def save_artifact(artifact: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_artifact(artifact))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_artifact(path: Path, sha256: str) -> dict:
    return deserialize_artifact(path.read_bytes(), sha256)


def serialize_artifact(artifact: dict) -> bytes:
    buffer = BytesIO()
    joblib.dump(artifact, buffer)
    return buffer.getvalue()


def deserialize_artifact(data: bytes, sha256: str) -> dict:
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("Model artifact integrity check failed")
    # Only server-created artifacts from our database or legacy local storage.
    # No model upload endpoint exists. Verify the bytes before deserializing.
    return joblib.load(BytesIO(data))
