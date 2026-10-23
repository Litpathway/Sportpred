from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from app.models.entities import Fixture

FEATURE_NAMES = ["home_scored", "home_conceded", "home_points", "home_venue_scored",
                 "away_scored", "away_conceded", "away_points", "away_venue_scored", "home_rest", "away_rest"]


@dataclass
class FeatureResult:
    values: list[float]
    quality: float
    detail: dict


def features_for(fixture: Fixture, history: list[Fixture], cutoff: datetime | None = None) -> FeatureResult | None:
    as_of = min(cutoff, fixture.kickoff) if cutoff else fixture.kickoff
    past = [f for f in history if f.status == "finished" and f.kickoff < as_of
            and f.result_known_at and f.result_known_at < as_of and f.simulated == fixture.simulated
            and f.home_goals is not None and f.away_goals is not None]
    values: list[float] = []
    detail: dict = {"as_of": as_of.isoformat(), "missing": [], "history_ids": []}
    counts = []
    for side, team_id in (("home", fixture.home_id), ("away", fixture.away_id)):
        recent = sorted([f for f in past if team_id in (f.home_id, f.away_id)], key=lambda f: f.kickoff)[-12:]
        if len(recent) < 6:
            return None
        counts.append(len(recent))
        detail["history_ids"].extend(f.id for f in recent)
        scored, conceded, points, venue = [], [], [], []
        for f in recent:
            is_home = f.home_id == team_id
            gf, ga = (f.home_goals, f.away_goals) if is_home else (f.away_goals, f.home_goals)
            scored.append(gf)
            conceded.append(ga)
            points.append(3 if gf > ga else 1 if gf == ga else 0)
            if is_home == (side == "home"):
                venue.append(gf)
        rest = min(21., (as_of - recent[-1].kickoff).total_seconds() / 86400)
        values.extend([float(np.mean(scored)), float(np.mean(conceded)), float(np.mean(points)),
                       float(np.mean(venue or scored))])
        detail[f"{side}_rest"] = rest
        detail[f"{side}_form"] = ["W" if p == 3 else "D" if p == 1 else "L" for p in points[-5:]]
        detail[f"{side}_matches"] = len(recent)
    values.extend([detail["home_rest"], detail["away_rest"]])
    # Optional feed statistics are exposed only when timestamped before prediction.
    extras = fixture.enrichment or {}
    extra_time = datetime.fromisoformat(extras["as_of"]).astimezone(UTC).replace(tzinfo=None) if extras.get("as_of") else None
    available = {}
    for key in ("xg", "shots", "defensive_stats", "injuries", "suspensions", "lineups"):
        value = extras.get(key)
        if extra_time and extra_time <= as_of and isinstance(value, dict) and {"home", "away"}.issubset(value):
            available[key] = value
        else:
            detail["missing"].append(key)
    detail["available_enrichment"] = available
    h2h = [f for f in past if {f.home_id, f.away_id} == {fixture.home_id, fixture.away_id}]
    detail["head_to_head_count"] = len(h2h)
    detail["head_to_head"] = [{"fixture_id": f.id, "home_goals": f.home_goals, "away_goals": f.away_goals,
                               "kickoff": f.kickoff.isoformat()} for f in sorted(h2h, key=lambda f: f.kickoff)[-5:]]
    detail["source_as_of"] = extras.get("as_of")
    detail["strength_rating"] = "Rolling points per game, not an external ranking"
    detail["values"] = dict(zip(FEATURE_NAMES, values, strict=True))
    # Historical coverage dominates; optional feed completeness supplies the rest.
    quality = .85 * min(counts) / 12 + .15 * len(available) / 6
    return FeatureResult(values, quality, detail)
