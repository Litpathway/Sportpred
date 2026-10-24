# SportPredict AI

Approved interface, design research, and the current frontend QA audit: [docs/DESIGN.md](docs/DESIGN.md).

**GitHub → Vercel deployment:** see [docs/VERCEL.md](docs/VERCEL.md). The root configuration deploys the site, API and production workers together. The ten selected European top flights are configured; live data requires an authorized feed.

**Native API-Football:** [connection and quota guide](docs/API_FOOTBALL.md). The direct adapter imports real fixtures and odds, records truthful observation times, and shares its cache and request budget across workers. An optional [SportyBet odds overlay](docs/SPORTYBET.md) adds read-only market quotes to exact match-page fixture matches. Neither feed replaces the verified history required to train an approved prediction model.

A working Next.js/FastAPI football intelligence application with persisted fixtures, reproducible Poisson/XGBoost predictions, calibration, approval and quality controls, candidate slips, publication and settlement. It never places wagers or handles money.

The default workspace is an explicitly **simulated demo** with fictional clubs. No live sports or booking credentials are included. [Progress and verification](docs/PROGRESS.md) records what was checked in this environment.

Screenshots from the running full-stack demo: [desktop](docs/screenshots/desktop.png) · [mobile](docs/screenshots/mobile.png).

## Start with Docker

Requires Docker Compose and Python 3.12+ for the one-time local configuration generator. From this directory:

```sh
python scripts/configure.py
docker compose up --build -d
docker compose exec api python -m app.cli seed-demo --approve-demo
```

Open **http://localhost:3000**. API health: http://localhost:8000/api/health. OpenAPI: http://localhost:8000/docs. The `migrate` service runs Alembic before the API starts. PostgreSQL, Redis, API, Celery worker, Celery beat and the frontend are separate services.

Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` from your local `.env` to sign in at `/login`. The generator creates unique secrets and does not print or commit them. Re-running seed is idempotent and never overwrites an existing password. `--approve-demo` explicitly approves the simulated model for demo use only; ordinary training always creates unapproved versions.

If `.env` already exists, skip the generator. Review and update it locally. Never commit `.env`, database files, model artifacts, replay captures or test traces.

## Native development

Python 3.12+, Node.js 20.9+ (22 recommended), and Redis are required for the complete local experience. SQLite is supported for local development and isolated tests; production requires PostgreSQL.

```sh
python scripts/configure.py
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
cd apps/api
pip install -r requirements.lock
pip install --no-deps -e .
python -m alembic upgrade head
python -m app.cli seed-demo --approve-demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd apps/web
npm ci
npm run dev
```

For production frontend verification: `npm run build` then `npm start`. The start script serves the standalone build with its static assets. Native Next.js rewrites `/api/*` to `http://127.0.0.1:8000` by default. `API_INTERNAL_URL` must be set **at frontend build time** when the backend has another internal address.

Run Redis separately and start the worker and scheduler from `apps/api`:

```sh
python -m celery -A app.workers.celery_app.celery worker --loglevel=INFO
python -m celery -A app.workers.celery_app.celery beat --loglevel=INFO
```

Celery workers are intended for Linux/Docker. On native Windows use `--pool=solo` for development only. Without Redis and workers, public browsing, authentication, settings, training via CLI and synchronous `python -m app.cli pipeline` still work; queued admin actions correctly return a queue-unavailable error.

This Windows workspace also contains an ignored `.tools/python/python.exe` runtime used for verification because the system Python alias did not execute. You can substitute it for `python` in commands; it is not part of deployment source or a supported distributable runtime.

## Integrate sports-skills

The reviewed [Machina Sports sports-skills](https://github.com/machina-sports/sports-skills) football SDK is integrated through an optional, pinned, **read-only personal/research provider**. See [installation, configuration, data rights and limitations](docs/integrations/sports-skills.md). A production mode guard prevents treating its public feeds as a licensed production service.

The application does not load its trading extras or route arbitrary SDK commands. No predicted odds, bookmaker codes, kickoff times or historical availability timestamps are invented. Public-data mode remains separate from demo models and simulated records.

## API and application routes

Public UI: `/`, `/matches`, `/matches/[id]`, `/predictions`, `/predictions/high-confidence`, `/booking-codes`, `/booking-codes/[id]`, `/performance`, `/about`.

Administration: `/login`, `/admin`, `/admin/fixtures`, `/admin/predictions`, `/admin/codes`, `/admin/models`, `/admin/providers`, `/admin/settings`.

Public API: `/api/overview`, `/api/fixtures`, `/api/fixtures/{id}`, `/api/competitions`, `/api/predictions`, `/api/slips`, `/api/slips/{id}`, `/api/performance`. Listings support validated limits and pagination; prediction and fixture lists support search and filters.

Every `/api/admin/*` endpoint requires a session. `viewer` reads, `operator` reads and triggers jobs/builds slips, `admin` additionally approves models and changes settings. Session tokens use HS256 with expiration, issuer and audience validation, an HTTP-only SameSite Strict cookie, and a session-bound CSRF token on mutations. Login attempts are throttled in the database. Production requires secure cookies. Users can be disabled in persistence; there is no public registration.

## Model and publication rules

- Historical features: last twelve known results, goals for/against, points per game, venue goal rates and rest days; six results per team are the minimum. Head-to-head and optional timestamped feed enrichment are recorded as context.
- At least 180 usable historical examples and 30 distinct kickoff times are required. Splits are chronological 60/20/20 by kickoff, with availability cutoffs. Poisson goal regressors and binary XGBoost classifiers fit the training period; sigmoid calibration fits validation; log loss, Brier, accuracy and reliability plots use the held-out test period.
- Model versions, training fingerprint, seed, split dates, artifacts and artifact SHA-256 are persisted. Approval is separate from training. Optional MLflow tracking: install `.[tracking]` and configure `MLFLOW_TRACKING_URI`.
- Predictions store raw and calibrated probabilities, frozen features, data quality, odds, explanation, version and eligibility rejection reasons. There are no hardcoded or randomly generated prediction probabilities.
- Scheduled inference creates an immutable snapshot per 15-minute window, idempotently within that window. Latest snapshots drive match analysis and high-confidence filters; historical snapshots remain in the full record. Refreshing quotes never rewrites the odds used for a prior prediction's hypothetical return.
- Default eligibility: calibrated probability ≥0.80, quality ≥0.70, approved matching-domain model, upcoming fixture, recent fixture data, fresh timestamped odds, and recent prediction. Recheck before building and publishing.
- Default slips contain one selection. Administrators may permit up to three legs. Duplicate fixtures, conflicting markets, repeated teams and repeated competitions are rejected. Multi-match joint probability and EV remain unset because independence has not been established. Single-selection EV is hypothetical `p × decimal_odds − 1`.
- Genuine booking codes require an authorized gateway, successful validation and exact selection matching. Mock values can never be marked genuine. Missing integration or provider outage publishes predictions without codes. Provider code creation receives a stable idempotency key; PostgreSQL locks and unique keys protect retries.
- Cancelled/postponed predictions settle as void. Finished scores settle supported markets as won or lost. Every outcome remains visible. Performance and hypothetical ROI include losses and separate pending/void counts. Backtest metrics are explicitly separate from published prediction history.

## Automation

Celery runs the ingestion/enrichment/settlement/prediction/filter/slip/publication pipeline every 15 minutes, booking status monitoring every five minutes, and model drift checks daily at 03:00 UTC. A shared Redis lease serializes mutation pipelines; task rates, bounded retries, idempotency records and SQL uniqueness protect duplicate execution. Failed jobs record attempts and enter `dead_letter` after four total attempts. Optional alerts use Sentry or `ALERT_WEBHOOK_URL`.

Jobs: `sync`, `odds`, `enrich`, `train`, `predict`, `filter`, `slips`, `publish`, `settle`, `monitor`, `drift`, `pipeline`. The normalized fixture feed includes timestamped odds and statistics, so odds sync uses the same authorized feed. Training never auto-approves production models. Review failures in the admin job log and audit trail. To retry a dead-letter job, trigger a new job from administration; domain idempotency prevents duplicate publications.

## Configuration

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | development/test/production; production enforces PostgreSQL and secure cookies |
| `DEMO_MODE` | Isolates simulated fixtures/models and public metrics from real-data mode |
| `JWT_SECRET` | Unique secret of at least 32 characters, generated locally |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | One-time CLI admin bootstrap; password ≥12 characters |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Compose database credentials |
| `DATABASE_URL` | SQLAlchemy URL; Compose overrides it to the internal PostgreSQL service |
| `REDIS_URL` | Celery broker/result backend and pipeline locks |
| `ALLOWED_ORIGINS` | Comma-separated exact frontend origins, including scheme and port |
| `COOKIE_SECURE`, `TOKEN_MINUTES` | HTTPS-only cookie mode and session lifetime |
| `ARTIFACT_DIR` | Legacy local model storage; new models store their bytes in PostgreSQL |
| `FIXTURE_PROVIDER` | `demo`, `authorized`, or optional `sports_skills` |
| `FIXTURE_API_URL`, `FIXTURE_API_TOKEN` | Customer-authorized HTTPS normalized fixture feed |
| `BOOKING_PROVIDER` | `unavailable` default, `mock` in demo, or `authorized` |
| `BOOKING_API_URL`, `BOOKING_API_TOKEN` | Customer-authorized booking-code gateway; not a bookmaker endpoint guess |
| `API_INTERNAL_URL` | Backend target baked into the Next.js build |
| `MLFLOW_TRACKING_URI` | Optional experiment tracking; requires tracking extra |
| `SENTRY_DSN` | Optional exception monitoring, default PII disabled |
| `ALERT_WEBHOOK_URL` | Optional dead-letter alert receiver; configure on the server |
| `SPORTS_SKILLS_*`, `INSTALL_SPORTS_SKILLS` | Optional research connector; see dedicated integration guide |

## Tests

Verified locally: **86 backend tests** and **18 desktop/mobile browser scenarios**, plus the Next.js production build, TypeScript, Alembic schema drift and Compose configuration checks. The latest full browser run passed 17 scenarios; a focused rerun passed the remaining desktop scenario after a cold-start timeout. Production npm audit reported zero vulnerabilities and Python dependency consistency passed. Container startup, PostgreSQL runtime and external production services remain unverified locally as described below; the GitHub workflow also checks the Linux API image.

```sh
cd apps/api
python -m pytest -q
python -m alembic check
cd ../web
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests cover desktop and mobile with synthetic API contract responses. For full-stack browser tests, first start a seeded API on port 8000, add `http://127.0.0.1:3100` to its allowed origins, and set `E2E_LIVE=1`. Supply `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` via the environment or use the local root `.env`. The real admin test temporarily changes a setting and restores it. `PLAYWRIGHT_EXECUTABLE_PATH` may select an already installed Chrome/Edge binary. Test traces can contain credentials; they are ignored and must not be shared.

On this restricted Windows workspace, use `-p no:cacheprovider` and a unique project-local `--basetemp ../../.tools/<run-name>` when running pytest from `apps/api` to avoid cross-user cache permissions. Native BLAS threads are bounded to avoid multiplying memory allocation across API, workers and tests.

GitHub Actions defines Linux tests, PostgreSQL migrations/schema checks, Redis services, demo seed/pipeline, a frontend production build and browser tests. Check the repository's Actions tab for remote results; local checks do not prove a successful cloud deployment.

## Deployment

For GitHub-linked Vercel hosting, follow [the Vercel deployment guide](docs/VERCEL.md). Import the repository root so the API and background workers deploy alongside Next.js. This configuration uses Vercel's beta Services, Container Runtime and Daemons features and needs managed PostgreSQL, Redis and a licensed data feed.

Deploy the Compose stack to a Docker-capable Linux host. Before first production start, set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, exact HTTPS `ALLOWED_ORIGINS`, unique secrets, `DEMO_MODE=false`, and an authorized licensed provider. Bootstrap an admin with `docker compose exec api python -m app.cli create-admin`. Ingest history, train, review holdout metrics, approve through administration, then generate predictions.

Serve only the frontend through a TLS reverse proxy; [Caddy example](infrastructure/Caddyfile) is provided. Keep PostgreSQL, Redis, workers and the API on the private Docker network. Restrict or remove loopback development API mappings when deploying. New model artifacts are included in PostgreSQL backups; preserve legacy local files until their models are retrained into database storage. Preserve audit/history records. Rotate credentials through environment configuration, restart services, and confirm health, migration state, provider freshness and job execution after rollout. Run one beat scheduler per deployment.

## Known limits

- Docker's engine did not become available on this Windows host; Compose configuration was checked, but container startup and PostgreSQL runtime verification need a working Docker engine. The SQLite migration lifecycle and schema drift checks were exercised locally.
- No production sports feed or genuine booking gateway credentials were supplied. The authorized interfaces have contract tests; a real integration requires provider-specific authorization and matching gateway implementation.
- The public sports-skills adapter has prototype-only data rights, uneven coverage and no live-score SLA. Historical backfill does not prove point-in-time result availability. It never bypasses model or odds requirements.
- The first ensemble uses historical results; optional xG, injuries, suspensions, shots, defense and lineups are context and completeness inputs, not fitted ensemble features. No correlation-aware joint model is trained.
- Published performance begins empty until generated predictions settle. The demo is a reproducible software exercise, not evidence of real-world predictive accuracy. Its relative-date fixtures are not a permanent historical sports feed.
- Audit and provider views are intentionally capped; public slip pagination currently filters data domains in the service layer. Larger deployments should normalize slip legs into an association table, add retention and query profiling, and implement account lifecycle/MFA through a production identity service.

Provider contracts: [authorized integrations](docs/PROVIDERS.md). Sports-skills: [research integration](docs/integrations/sports-skills.md). Third-party attribution: [notices](docs/THIRD_PARTY_NOTICES.md).
