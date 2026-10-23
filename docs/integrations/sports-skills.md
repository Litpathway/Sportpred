# sports-skills football integration

Reviewed repository: [machina-sports/sports-skills](https://github.com/machina-sports/sports-skills/tree/bdb972c0625fa337e15f18ca58abd28f57f25e37), SDK 0.37.2. The optional dependency is pinned to this exact source archive, not a floating Git branch. Instructions used: [football-data/SKILL.md](https://github.com/machina-sports/sports-skills/blob/bdb972c0625fa337e15f18ca58abd28f57f25e37/skills/football-data/SKILL.md) and its API reference.

## Scope and rights

The upstream wrapper code is MIT licensed. Public-source data is separately restricted; upstream describes the integrations as personal/non-commercial and marks canonical data `prototype_only=true`, `commercial_use=false`. This application enforces that boundary **before importing the SDK or making requests**. `ENVIRONMENT=production` always refuses this provider. For a commercial deployment use `FIXTURE_PROVIDER=authorized` with a licensed, normalized data feed.

Only these football SDK methods are reachable: `get_current_season`, `get_season_schedule`, `get_daily_schedule`, and `get_event_lineups`. No premium setup, CLI execution, wallet/trading modules, market orders, or bookmaker automation is exposed. The base SDK is installed without trading extras. This integration produces no booking codes or wagering functionality.

## Enable personal/research data

From `apps/api`, with your virtual environment active:

```sh
pip install '.[sports]'
```

Use a separate database for research, or retain the existing database knowing that public APIs and analytics filter simulated and real records into separate environments. Update the root `.env` locally:

```dotenv
ENVIRONMENT=development
DEMO_MODE=false
FIXTURE_PROVIDER=sports_skills
SPORTS_SKILLS_PERSONAL_USE=true
SPORTS_SKILLS_COMPETITIONS=premier-league
SPORTS_SKILLS_DAYS_AHEAD=3
SPORTS_SKILLS_HISTORY=false
SPORTS_SKILLS_ENRICH_LIMIT=4
BOOKING_PROVIDER=unavailable
```

Then restart the API and workers and run:

```sh
python -m app.cli sync
python ../../scripts/check_sports_skills.py
# Optional single real upstream read:
python ../../scripts/check_sports_skills.py --live
```

For Docker, set `INSTALL_SPORTS_SKILLS=true` in `.env` before `docker compose build`. The image includes the optional pinned SDK only when this build argument is enabled.

## Configuration

| Variable | Default | Behavior |
|---|---|---|
| `SPORTS_SKILLS_PERSONAL_USE` | false | Explicit public-data research opt-in; production remains forbidden |
| `SPORTS_SKILLS_COMPETITIONS` | premier-league | One to ten unique supported league slugs; see the [European catalog](../VERCEL.md#ten-configured-domestic-leagues) |
| `SPORTS_SKILLS_DAYS_AHEAD` | 3 | UTC daily-schedule windows, 1–7 |
| `SPORTS_SKILLS_HISTORY` | false | Optional full current-season backfill; can issue many upstream requests |
| `SPORTS_SKILLS_ENRICH_LIMIT` | 4 | Maximum upcoming fixtures for confirmed lineup lookup per sync, 0–12 |
| `SPORTS_SKILLS_REPLAY` | off | Upstream SDK replay mode; use `replay` to forbid network for recorded tests |
| `SPORTS_SKILLS_REPLAY_DIR` | empty | Local private capture directory; not an artifact to publish |

Supported configured leagues: premier-league, championship, la-liga, bundesliga, serie-a, ligue-1, mls, eredivisie, primeira-liga, champions-league, serie-a-brazil. This list is a connector scope, not a claim of complete or continuously available coverage.

## Mapping and safeguards

- Resolve the active season with `get_current_season` before accepting events. Reject estimated season IDs and events from a different season.
- Keep native ESPN team IDs under the `espn` namespace. Never resolve an ambiguous club by fuzzy matching or hash a name into a provider ID.
- Accept ESPN event statuses and final scores. Date-only, timezone-free, unknown-status and incomplete records are skipped and audited. This adapter deliberately declines openfootball fallback batches rather than mixing identifier systems or inventing kickoff times.
- Source observations record the reviewed commit, source, observed-at timestamp, rights and coverage caveats in fixture enrichment; they are visible in the API.
- `synced_at` is our retrieval time, **not** an upstream “last updated” claim. No provider update timestamp is fabricated.
- Preserve the first observed final timestamp for unchanged scores. A score correction gets a new availability timestamp. Ingestion retries do not duplicate fixtures.
- Read confirmed lineups only for a bounded number of upcoming events and join them by native team IDs. Require eleven named starters for each side. Missing or unsupported enrichment stays absent and lowers quality.
- No odds are inferred from forecasts or prediction-market prices. Without fresh authorized quotes, eligibility rejects publication candidates with `stale_or_missing_odds`.
- SDK failures and throttles receive bounded retries. Optional lineup failures do not discard valid fixtures. Ingestion failures preserve existing records and enter the worker retry/dead-letter path.

## Historical availability and model training

The SDK supplies historical results but does not establish when each final result originally became available. Backdating `result_known_at` to kickoff plus a guessed duration would misrepresent point-in-time evidence. The adapter therefore records the actual first observation.

A newly backfilled season can support current team context, but cannot immediately support a leakage-free historical training set under the strict timestamp policy. Training returns `insufficient_data` until enough point-in-time history is recorded or an authorized historical dataset supplies verifiable availability timestamps. Demo models remain isolated from real fixtures. This limitation is intentional and must not be bypassed by approving a simulated model for public-data predictions.

Understat xG, FPL injuries and ClubElo forecasts are not automatically collected by this integration. Coverage and player identity resolution differ across these sources. The normalized authorized-feed contract can supply timestamped xG, shots, defense, injuries, suspensions and lineups. Their presence is recorded as context; the first ensemble uses the documented historical feature vector.

## Verification

`tests/test_sports_skills.py` exercises season discovery, research opt-in, production rejection, namespace mapping, date/season rejection, lineup joining, observed result timestamps, duplicate prevention, outages, rate-limit retries and the read-only command allowlist. Network-free fixtures are deliberately synthetic contract examples. A passing contract suite does not prove that public sources are available or licensed for a particular deployment.
