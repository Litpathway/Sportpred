# Deploy SportPredict from GitHub to Vercel

Repository: https://github.com/Litpathway/Sportpred

The repository root contains `vercel.json`. Import this repository into Vercel with **Root Directory left at the repository root**. Do not select `apps/web`: that would omit the API and workers. The configuration builds Next.js in `apps/web`, the Python API container in `apps/api`, and two production daemons for Celery workers and scheduling. `/api/*` and the website share one HTTPS origin, including admin cookies.

This deployment uses Vercel **Services, Container Runtime and Daemons**, currently beta features. Check their availability in your Vercel project before deploying. The existing Docker Compose deployment remains available if your account cannot use these features.

Linux builds install XGBoost's smaller CPU package; this model does not need GPU libraries. GitHub Actions also builds the API image and checks its imports. See [XGBoost's installation guide](https://xgboost.readthedocs.io/en/stable/install.html#minimal-installation-cpu-only).

## Resources to connect

- A managed PostgreSQL database. Model bytes, SHA-256 hashes, metrics, approval state, users, fixtures and predictions are stored here. New models do not depend on a container filesystem or a separate object store.
- Managed Redis with the standard Redis TCP/TLS protocol and Celery support. An HTTP-only Redis REST endpoint is insufficient. Use a persistent Redis service configured to retain queued tasks rather than evicting broker keys.
- An API-Football account using the [native integration](API_FOOTBALL.md), or an authorized gateway implementing [PROVIDERS.md](PROVIDERS.md). Provider credentials belong in Vercel's encrypted environment settings.

Place PostgreSQL and Redis near the worker region (`iad1` in `vercel.json`), or update both daemon regions together. Keep the scheduler at one instance. The worker starts with concurrency one; measure training memory and duration against your data before increasing workload.

If you do not yet have a provider, [API-Football](https://www.api-football.com/pricing) offers a free account for initial API tests (100 requests/day, restricted seasons). Its published plans include all competitions and endpoints. That quota is not a production capacity promise for ten leagues with frequent fixture and odds refreshes. Confirm the actual season, odds and redistribution rights for the intended site before choosing a paid plan. The native adapter uses `API_FOOTBALL_KEY` directly; a separate gateway is needed only for `FIXTURE_PROVIDER=authorized`.

## Vercel environment variables

Set these for the Production environment before the first deployment. Use separate databases and Redis instances for Preview deployments; production daemons do not run on previews during Vercel's beta.

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` (unprivileged API container port) |
| `DEMO_MODE` | `false` |
| `COOKIE_SECURE` | `true` |
| `ALLOWED_ORIGINS` | Exact site origin, e.g. `https://sportpred.vercel.app`; use the actual assigned domain, with no trailing slash |
| `DATABASE_URL` | PostgreSQL URL from your database integration; the app selects the psycopg driver |
| `DATABASE_URL_UNPOOLED` | Direct PostgreSQL URL for migration session locks |
| `REDIS_URL` | Redis broker connection URL from your provider, with required TLS/certificate options |
| `JWT_SECRET` | A newly generated random secret of at least 32 characters |
| `ADMIN_EMAIL` | Your administrator email |
| `ADMIN_PASSWORD` | A unique password of at least 12 characters |
| `FIXTURE_PROVIDER` | `api_football` for the native API-Football adapter, or `authorized` for a custom gateway |
| `API_FOOTBALL_KEY` | API-Football credential, marked sensitive; native adapter only |
| `FIXTURE_API_URL` / `FIXTURE_API_TOKEN` | Only required for a custom authorized gateway |
| `PIPELINE_INTERVAL_MINUTES` | Initial API-Football deployment: `60`, with request caching and a 90-request daily guard |
| `BOOKING_PROVIDER` | `unavailable` initially; genuine codes require the separate authorized booking integration |

`ENABLED_LEAGUES` defaults to the ten league slugs below. Set `PORT=8000` in Vercel so its routing and the non-root API container use the same unprivileged port. Do not set `API_INTERNAL_URL` on Vercel: the root service router connects `/api/*` directly. Never prefix server secrets with `NEXT_PUBLIC_`.

At container startup, the cloud entrypoint acquires a shared PostgreSQL advisory lock, applies Alembic migrations and creates the first admin if absent. It preserves an existing admin's password. No fictional fixtures are seeded, and production models require explicit review and approval.

## First deployment

1. Import `Litpathway/Sportpred` using Vercel's GitHub integration, keep the repository root, and configure the variables above. Select Node.js 22 for the web build.
2. Deploy, then check `/api/health` and the API, `prediction-worker` and `prediction-scheduler` logs. GitHub pushes to the linked production branch deploy subsequent changes.
3. Sign in at `/login`. In administration, sync the authorized historical and upcoming data. Verify all ten leagues under **Matches → European league coverage**; “data received” counts imported fixtures and does not assert complete or fresh provider coverage.
4. Train a model when sufficient verified historical availability exists, inspect chronological evaluation/calibration and source timestamps, and explicitly approve it. Run the prediction pipeline once. The scheduler uses `PIPELINE_INTERVAL_MINUTES`, checks genuine booking codes every five minutes when that integration is configured, and performs daily drift checks. Imported historical scores alone do not establish a valid point-in-time training set; current team form remains visible without invented probabilities.
5. Confirm that new prediction snapshots and settlement records persist across redeployments. Missing history, model approval or fresh odds must remain visible as insufficient data or ineligibility.

Current local verification does not prove a cloud deployment: the first Vercel build, PostgreSQL/Redis connectivity, licensed feed coverage and live worker execution must be confirmed in the connected account.

## Ten configured domestic leagues

This is the user-selected group of major European top flights, not a live UEFA coefficient ranking.

| Country | League | Gateway `league_slug` |
|---|---|---|
| England | Premier League | `premier-league` |
| Spain | La Liga | `la-liga` |
| Germany | Bundesliga | `bundesliga` |
| Italy | Serie A | `serie-a` |
| France | Ligue 1 | `ligue-1` |
| Netherlands | Eredivisie | `eredivisie` |
| Portugal | Primeira Liga | `primeira-liga` |
| Belgium | Belgian Pro League | `belgian-pro-league` |
| Turkey | Süper Lig | `super-lig` |
| Scotland | Scottish Premiership | `scottish-premiership` |

Map your provider's native competition IDs explicitly to these IDs in the gateway. Authorized ingestion requires `league_slug`, rejects simulated fixtures and country mismatches, and skips disabled leagues. The app does not guess competition identities from similar names. The optional Machina research adapter now accepts up to ten competitions, but its public data remains disabled in production; its code licence does not supply commercial data rights.

## Existing local models

The migration leaves existing local artifacts usable locally. Run training again before migrating an old database to the cloud: an existing version without database bytes is retrained into shared storage and requires fresh approval. New artifacts are saved transactionally with their model version and integrity hash. Include model bytes in PostgreSQL backups and monitor database growth as model versions accumulate.

## Official platform references

- [Services](https://vercel.com/docs/services)
- [Container Runtime](https://vercel.com/docs/functions/runtimes/container)
- [Daemons](https://vercel.com/docs/daemons)
- [Daemon configuration](https://vercel.com/docs/daemons/config-reference)
- [GitHub deployments](https://vercel.com/docs/git/vercel-for-github)
