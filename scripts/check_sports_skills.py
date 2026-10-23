"""Inspect the optional integration. --live performs one read-only season lookup."""
import argparse
from importlib.metadata import version
import json

from app.core.config import Settings
from app.providers.sports_skills import SportsSkillsFixtureProvider, UPSTREAM_COMMIT

parser = argparse.ArgumentParser()
parser.add_argument("--live", action="store_true")
args = parser.parse_args()
result = {"sdk_version": version("sports-skills"), "reviewed_commit": UPSTREAM_COMMIT, "operations": "read-only"}
if args.live:
    settings = Settings(demo_mode=False, sports_skills_personal_use=True, environment="development")
    provider = SportsSkillsFixtureProvider(settings)
    response = provider._read("get_current_season", competition_id="premier-league")
    result["season_discovery"] = response.get("season", {}).get("id")
    result["estimated"] = response.get("estimated", False)
print(json.dumps(result))
