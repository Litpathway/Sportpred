# API-Football connection

Use `FIXTURE_PROVIDER=api_football`, `DEMO_MODE=false`, and a server-only `API_FOOTBALL_KEY`. The adapter calls `https://v3.football.api-sports.io` with the `x-apisports-key` header. It does not require a custom gateway, and never exposes the key to browsers. Store it as a sensitive Production variable in Vercel; a sensitive key cannot be exported for local inspection and is tested on the deployed server instead.

The adapter verifies active season metadata for the ten configured native league IDs, imports yesterday/today/tomorrow UTC by default, gradually warms each league's current-season fixture history, and fetches pre-match odds for scheduled games. Native team, competition and fixture identities remain separate from the application's league slugs. Unknown kickoff times, invalid records, country mismatches and unverified seasons are rejected.

Results settled after extra time or penalties use `score.fulltime` for regulation-time markets. Provider odds retain their actual update timestamp and bookmaker identity; unavailable quotes stay unavailable. No odds are synthesized and quotes from different bookmakers are not combined into a fictional line.

Redis caches successful responses with their original observation timestamps and atomically limits uncached requests across worker restarts and manual retries. Defaults are 90 external requests per UTC day and eight per minute. Production initially uses a 60-minute pipeline, 60-minute fixture cache and 180-minute odds cache. These limits favor a small initial API plan; check actual subscription and coverage before raising them. Reaching a quota preserves existing records, records a warning and stops additional requests. Error text from the provider is not logged verbatim because it can echo credentials.

API-Football sometimes returns HTTP 200 with an `errors` body. This is treated as a failure. Authentication, subscription, pagination, quota and transport errors remain distinct from an empty fixture list. A scheduled job cannot claim a complete successful sync when every schedule request failed. Account status and sanitized import warnings appear in the administrator's Providers screen.

## Historical availability and models

The API supplies kickoff times, scores and observed current status; those do not establish when historical final results became available. The adapter records `result_known_at` as the first actual observation of a final score and preserves it on unchanged later imports. It never fabricates availability as kickoff plus two hours. An initial historical download therefore does not automatically provide a valid point-in-time model-training dataset. The calibrated model can remain unavailable until sufficient verified observations or a trustworthy historical availability dataset exists. Training and approval are explicit; an API key alone does not establish calibrated prediction accuracy.

Published performance and eligibility continue to use only actual site model snapshots. The integration never calls betting, payments or wagering endpoints, and does not substitute API-Football's prediction endpoint for the site's trained model.

## Server configuration

| Variable | Default | Purpose |
|---|---|---|
| `API_FOOTBALL_KEY` | missing | Required server-side credential |
| `API_FOOTBALL_DAYS_AHEAD` | 1 | Upcoming UTC days, plus today and yesterday |
| `API_FOOTBALL_DAILY_BUDGET` | 90 | Hard daily guard for this site's API calls |
| `API_FOOTBALL_MAX_REQUESTS` | 20 | Additional bound per provider invocation |
| `API_FOOTBALL_FIXTURE_CACHE_MINUTES` | 60 | Schedule response cache |
| `API_FOOTBALL_ODDS_CACHE_MINUTES` | 180 | Odds response cache |
| `API_FOOTBALL_BOOKMAKER_ID` | unset | Optional single-bookmaker filter |
| `PIPELINE_INTERVAL_MINUTES` | 15 | Generic scheduler default; initial API-Football deployment uses 60 |

`DATABASE_URL`/`POSTGRES_URL` and `DATABASE_URL_UNPOOLED`/`POSTGRES_URL_NON_POOLING` support standard PostgreSQL URLs; the app selects the psycopg driver. Cloud migrations use the direct, unpooled connection so PostgreSQL session locks are not sent through a transaction pooler. `REDIS_URL`, `KV_URL` and `UPSTASH_REDIS_URL` are accepted for standard Redis TCP/TLS connections. Celery uses verified TLS for `rediss` URLs and a longer idle blocking poll to reduce background Redis operations.

Official references: [API-Football documentation](https://www.api-football.com/documentation-v3), [provider's getting-started guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide), [plans](https://www.api-football.com/pricing).
