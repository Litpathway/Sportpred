import math
from collections import Counter, defaultdict

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.engine import evaluate, outcomes
from app.core.config import get_settings
from app.models.entities import AuditLog, Fixture, ModelVersion, Prediction


def settle_results(db: Session) -> dict:
    settled = 0
    for p in db.scalars(select(Prediction).where(Prediction.outcome == "pending")):
        f = p.fixture
        if f.status in {"cancelled", "postponed"}:
            p.outcome = "void"
        elif f.status == "finished" and f.home_goals is not None and f.away_goals is not None:
            p.outcome = "won" if outcomes(f.home_goals, f.away_goals)[p.market] else "lost"
        else:
            continue
        p.eligible = False
        db.add(AuditLog(action="prediction.settled", entity=str(p.id), detail={"outcome": p.outcome, "home": f.home_goals, "away": f.away_goals}))
        settled += 1
    db.commit()
    return {"settled": settled}


def performance(db: Session, simulated: bool | None = None) -> dict:
    domain = get_settings().demo_mode if simulated is None else simulated
    latest_ids = select(func.max(Prediction.id)).group_by(Prediction.fixture_id, Prediction.market)
    rows = list(db.scalars(select(Prediction).where(Prediction.id.in_(latest_ids), Prediction.fixture.has(Fixture.simulated == domain)).order_by(Prediction.created_at)))
    counts = Counter(p.outcome for p in rows)
    done = [p for p in rows if p.outcome in {"won", "lost"}]
    market_rows, bands, versions = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in done:
        market_rows[p.market].append(p)
        bands[f"{min(90, int(p.probability * 10) * 10)}–{min(100, int(p.probability * 10) * 10 + 10)}%"].append(p)
        versions[p.model.version].append(p)

    def group(items):
        return [{"name": name, "count": len(group), "accuracy": sum(p.outcome == "won" for p in group) / len(group)} for name, group in items.items()]

    metrics = evaluate(np.array([int(p.outcome == "won") for p in done]), np.array([p.probability for p in done])) if done else None
    quoted = [p for p in done if p.odds is not None]
    roi = sum((p.odds - 1) if p.outcome == "won" else -1 for p in quoted) / len(quoted) if quoted else None
    cumulative, history = 0, []
    for p in done:
        cumulative += 1 if p.outcome == "won" else 0
        history.append({"date": p.created_at.date().isoformat(), "accuracy": cumulative / (len(history) + 1), "count": len(history) + 1})
    return {"total": len(rows), "won": counts["won"], "lost": counts["lost"], "void": counts["void"], "pending": counts["pending"],
            "accuracy": counts["won"] / len(done) if done else None, "metrics": metrics, "roi": roi,
            "roi_assumptions": "Hypothetical flat one-unit stake on every settled prediction with recorded odds; no fees, limits or slippage. Overlapping markets are not independent. No money is staked.",
            "by_market": group(market_rows), "by_probability_band": group(bands), "by_model": group(versions),
            "history": history, "simulated": any(p.fixture.simulated for p in rows)}


def drift_report(db: Session) -> dict:
    rows = list(db.scalars(select(Prediction).where(Prediction.outcome.in_(["won", "lost"]))
                           .order_by(Prediction.created_at.desc()).limit(200)))
    if len(rows) < 50:
        report = {"status": "insufficient_data", "settled": len(rows), "minimum": 50}
    else:
        brier = sum((p.probability - int(p.outcome == "won")) ** 2 for p in rows) / len(rows)
        baseline = sum(p.model.metrics.get("markets", {}).get(p.market, {}).get("brier", .25) for p in rows) / len(rows)
        report = {"status": "alert" if brier > baseline + .05 else "ok", "brier": brier, "baseline": baseline, "settled": len(rows)}
    db.add(AuditLog(action="model.drift", entity="latest", detail=report))
    db.commit()
    return report
