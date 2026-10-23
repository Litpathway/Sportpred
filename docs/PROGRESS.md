# Build progress

The supplied build brief is the acceptance specification. Checkboxes mean relevant checks have run; source alone does not establish completion.

- [x] 1. Repository, Docker configuration, SQLite migration lifecycle and authentication
- [x] 2. Provider adapters, ingestion, normalization and duplicate prevention
- [x] 3. Historical features, Poisson/XGBoost training, calibration and evaluation
- [x] 4. Predictions, eligibility decisions, immutable snapshots and conservative slip construction
- [x] 5. Responsive Next.js public website and analysis routes; desktop/mobile browser and viewport checks pass
- [x] 6. Booking adapters, verification and idempotent publication
- [x] 7. Admin, Celery schedules, settlement and analytics; task execution/retry contracts tested
- [x] 8. Security checks, automated tests, CI definition and deployment documentation

## Verification record — 23 October 2026

- Final completed backend suite: **74 passed**, including immutable generation windows, original-quote preservation and the latest-only API feed.
- Both Alembic revisions upgrade/downgrade in isolated SQLite tests; schema drift check passes on the migrated local database.
- Reproducible training and artifact roundtrip/tampering, chronological splits, future-result exclusion, calibration, eligibility and settlement exercised.
- Demo seed persisted **1,020 fixtures**, trained the ensemble, generated **120 predictions**, and published **12 prediction-only records**. A later pipeline updated fixtures and created a new 120-prediction snapshot without rewriting original quotes.
- Celery task success, idempotency, lock contention, retries and dead letters exercised with a controlled broker/lock boundary. A real Redis-backed worker/beat process remains unverified here.
- Final production frontend build and TypeScript checks **pass**, including the table positioning fix for mobile accessibility labels.
- **16 browser tests pass** across desktop and mobile, including actual backend predictions, login, a reversible settings change, mocked error states, responsive navigation and document-width assertions. Screenshots are saved under `docs/screenshots/`.
- `npm audit --omit=dev --audit-level=high`: **0 vulnerabilities**. `pip check`: no broken requirements.
- Compose configuration validation passes. Docker Desktop did not provide a working engine; container builds/startup and PostgreSQL runtime checks are **not verified**.
- The optional sports-skills SDK **0.37.2** was installed from reviewed commit `bdb972c0625fa337e15f18ca58abd28f57f25e37`. A real read-only season discovery returned `premier-league-2026`, `estimated=false`.
- Production rights rejection, research opt-in, season/identity mapping, lineup joins, result availability, source outage, throttling and read-only command restrictions have contract coverage.

## Remaining external verification

- [ ] Start the complete Compose stack on a working Docker engine and exercise PostgreSQL and Redis-backed workers.
- [ ] Run the supplied Linux GitHub Actions workflow in the user's connected repository.
- [ ] Configure and validate a licensed sports feed and an authorized genuine booking-code gateway before production use.
- [ ] Verify optional MLflow, Sentry and alert receivers when configured; their external services were not supplied.

## Implementation plan

1. Build a migrated SQLAlchemy schema and cookie-authenticated, role-protected FastAPI service. PostgreSQL is the deployment database; SQLite supports isolated local tests.
2. Ingest validated provider DTOs and explicitly simulated historical fixtures. Derive features using only results known before each kickoff.
3. Train reproducible Poisson and XGBoost models with chronological validation calibration and an untouched test set. Persist model artifacts, metrics and approval state.
4. Store every prediction and eligibility reason. Build single-selection slips; decline unsupported joint estimates. Publish predictions even when code providers fail.
5. Connect a dark, responsive Next.js interface to the API, including authenticated administration.
6. Add Celery automation, retries and dead letters, settlement, performance metrics, acceptance tests and operating instructions.

## Environment observations

- Empty starting workspace.
- Node.js 20.20.2 and npm are available.
- The system Python alias does not execute. An isolated Python 3.12.10 runtime was installed under ignored `.tools/` for local verification.
- Docker CLI is installed, but the Docker daemon is not running. Compose runtime verification requires a working daemon.
- No live sports-data or booking-provider credentials were supplied. Demo fixtures remain visibly simulated; genuine booking codes remain disabled by default.

## GitHub / Vercel handoff

- Target repository: `Litpathway/Sportpred`; the user confirmed the ten domestic leagues in `docs/VERCEL.md`.
- Added Vercel services for Next.js and the API container, with separate production worker and scheduler daemons.
- New model artifacts persist as integrity-checked database bytes; legacy local models remain compatible. Cloud startup serializes migrations and admin bootstrap with a PostgreSQL advisory lock.
- Added canonical league mapping and ten-league coverage reporting, including explicit missing-feed states.
- Local checks: 86 backend tests, production frontend build and TypeScript passed. All 18 browser scenarios passed across a full run and the focused desktop rerun described in README.
- The user has no sports-data provider or key yet. No live feed, production Vercel deployment, external PostgreSQL/Redis connection or genuine booking service has been verified.
