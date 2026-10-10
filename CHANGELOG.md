# Changelog

All notable changes to the **Reliability Modeler** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.9.0] - 2026-10-10

Production-readiness release. **Contains breaking changes**; read "Upgrade notes" and RUNBOOK.md section 2 before upgrading.

### Breaking
- **`RELIABILITY_API_KEY` is mandatory.** The API refuses to start without it (dev-only escape hatch: `ALLOW_INSECURE_NO_AUTH=true`). Every route except `/health` and `/health/live` requires the key, including `/docs`, `/redoc`, `/openapi.json` and `/metrics`.
- **`UI_PASSWORD` is mandatory.** The UI enforces HTTP Basic auth on every route except `/healthz`; without a password it answers 503 "UI_PASSWORD not configured". `docker compose` refuses to start if either variable is missing.
- **API port 8000 is no longer published** to the host. All access goes through the UI proxy on port 3000 (or from inside the compose network).
- **Analysis ID format** is now `AN-YYYYMMDD-HHMMSS-<6 hex>` (UTC, unique). Old IDs are still accepted.

### Added
- UI login (Basic auth, constant-time compare, `UI_USERNAME` default `admin`) and `/healthz` liveness route.
- Persistent `config_data` volume at `/app/config` for `fault_categories.conf` and `settings.json`, seeded from the bundled default (`/app/defaults/fault_categories.conf`) on first start. New `CONFIG_DIR`, `OUTPUT_DIR`, `DEFAULT_CONFIG_PATH` settings.
- Deep health check: `/health` reports `checks` (output writable, config readable, Sentry token configured) with `ok` / `degraded` / `error` (503); `/health/live` for container health checks.
- Prometheus `/metrics`: `rm_http_requests_total`, `rm_analyses_total`, `rm_analysis_duration_seconds_sum/_count`, `rm_ingest_failures_total`.
- Real JSON logging (`ts`, `level`, `logger`, `msg`, `request_id`).
- Configurable retention: `RETENTION_DAYS` (default 90; startup + daily prune; 0 disables).
- Request body limit `MAX_BODY_BYTES` (default 1 MiB) on all POST routes; stricter input validation.
- UI: live System Status badge, visible error states with HTTP status and retry, React error boundaries.
- UI proxy: forwards/generates `X-Request-ID`, sets `X-Forwarded-For`, GET/POST allowlist, 1 MiB body limit, `PROXY_TIMEOUT_MS`, binary-safe bodies, JSON error logging.
- Tests: API tests with FastAPI `TestClient`, UI tests with vitest; coverage floor of 75% in CI.
- `RUNBOOK.md` (deploy, upgrade, rollback, secret rotation, backup/restore, failure table, release procedure); `scripts/backup.sh`, `scripts/restore.sh`, `scripts/smoke-test.sh`.
- `release.yml` workflow: multi-arch (`linux/amd64`, `linux/arm64`) build and push to Docker Hub on `v*` tags or manual dispatch.

### Changed
- Single version source: `modeler/__init__.py` (`2.9.0`), used by the API, Makefile and release workflow.
- Analysis and GraphQL execution run off the event loop, so timeouts are enforced and `/health` stays responsive; plotting uses the matplotlib object API (no global pyplot state).
- All error responses use `{"detail": "..."}`; UI parses `detail` (then `error`).
- Sentry connector retries transient failures (429/5xx) with backoff.
- API image: `python:3.13-slim` pinned by digest, multi-stage build (no compiler in the runtime image), non-root, health check on `/health/live`, all API modules copied.
- Compose hardening: `IMAGE_TAG` / `DOCKERHUB_NAMESPACE`, `restart: unless-stopped`, health-based `depends_on`, CPU/memory limits, json-file log rotation (10 MB x 5), `no-new-privileges`, dropped capabilities, configurable `ALLOWED_ORIGINS`.
- Root `.dockerignore` keeps `.env`, `.git`, output and tool directories out of the build context.
- Makefile rewritten: `build`, `test`, `smoke`, multi-arch `push` (`:VERSION` + `:latest`), `up`/`down`/`logs`, `backup`/`restore`.
- CI overhaul: Python 3.13 (matches the image), coverage gate, integration tests against an authenticated API, UI lint/typecheck/test/build, `npm audit` and `pip-audit`, Docker build + smoke test, current action versions.
- Documentation rewritten: README, SUPPORT, USER_MANUAL, `.env.example`.

### Fixed
- Rate limiter: `X-Forwarded-For` is honoured only for requests authenticated with the API key (the UI proxy), so clients can no longer spoof their IP to evade limits.
- Cascade-chain extraction bug in the graph engine.
- Analysis ID collisions when two analyses started in the same second.

### Removed
- `Reference_Release/` (old Windows CLI build and sample CSV input). It remains available in git history.

### Upgrade notes
- Add `RELIABILITY_API_KEY` and `UI_PASSWORD` to `.env` (see `.env.example`), replace `docker-compose.yml`, then `docker compose up -d`.
- A customised taxonomy from 2.8.x lived inside the container; export it before upgrading and copy it into the new config volume (RUNBOOK.md section 2).
- Anything that called `http://<host>:8000` directly must use the UI proxy or the internal network.

## [2.8.1] - 2026-10-10

### Fixed
- **Sentry ingestion** — `_fetch_project_events` referenced an undefined `base` variable (NameError on every ingest since 2.8.0).
- **API image** — Dockerfile now copies `graphql_schema.py`; images since 2.7.1 crashed on startup.
- **UI build** — regenerated `package-lock.json` (was out of sync with package.json, `npm ci` failed); fixed two TypeScript errors from the recharts upgrade.
- **UI healthcheck** — probes `127.0.0.1` instead of `localhost` (resolved to IPv6, container reported unhealthy).

### Security
- Next.js 16.3.0 → 16.3.8 (critical advisory: RCE/SSRF in image optimization); `npm audit` now clean.

## [2.8.0] - 2026-08-17

### Security fixes (from full audit)
- **Authentication fixed** — removed the client-side `NEXT_PUBLIC_API_KEY` (was
  shipped in the JS bundle) and the GET bypass. Added a server-side Next.js proxy
  (`/api/[...path]/route.ts`) that injects `RELIABILITY_API_KEY` server-side.
  Auth now applies to all non-`/health` routes.
- **GraphQL path traversal fixed** — analysis IDs validated against
  `^AN-\d{8}-\d{6}$` before any disk access.
- **Sentry slug injection fixed** — org/project slugs validated + URL-encoded
  with `quote(safe='')`.
- **Error disclosure** — Sentry error bodies and URLs no longer echoed to clients.
- **Log-forging** — `X-Request-ID` sanitized to `[A-Za-z0-9-]`.
- **Introspection** — precise regex (`__schema\b|__type\b`) that no longer
  falsely blocks `__typename`.
- **Non-root** — API container now runs as a non-root `appuser`.

### Robustness fixes
- **Fail-open warning** — startup logs a prominent warning when auth is disabled.
- **`/logs/prune`** — `retention_days` validated (≥7), prunes logs + analyses + plots.
- **Unbounded `project=all`** — capped at 50 projects and the entire fetch is
  wrapped in `ANALYSIS_TIMEOUT_SECONDS`.
- **HTML report chart** — reliability plot is now persisted to `output/plots/`
  so executive reports actually embed the chart (was always empty).
- **Corrupt settings.json** — `load_persistent_settings` now falls back to defaults.
- **Dead code** — removed unused `_sentry_request`.
- **ROOT_DIR** — Docker flat-layout detection so write paths resolve to `/app`
  (fixes the compose volume mismatch).
- **GraphQL cross-analysis DoS** — capped to the 50 most recent analyses.

### Tests
- 4 new security tests (slug validation, path traversal rejection, introspection regex).
- 39/39 unit tests pass.
- *Correction (2026-10-10):* the 39 passing tests did not cover `_fetch_project_events` or the Docker image. 2.8.0 shipped with a `NameError` on every Sentry ingest and an API image that crashed on startup; both were fixed in 2.8.1.

## [2.7.2] - 2026-08-17

### Added — Cross-analysis GraphQL query
- `keystoneCategoriesAcross(limit)` — aggregates keystone categories across
  ALL analyses, ranking which fault category is *consistently* central over time.
  Returns `{node, keystoneCount, avgPagerank, totalAnalyses}`.
- 1 new unit test covering the cross-analysis aggregation.
- README: example query.

## [2.7.1] - 2026-08-17

### Added — GraphQL persistence
- Graph data is now persisted to `output/analyses/{id}.json`, so GraphQL can query
  **historical analyses** across restarts (previously in-memory only).
- New `availableAnalyses` GraphQL query lists all queryable analysis IDs.
- Added `list_available_analyses()` + disk fallback in `_get_categorized_data()`.
- 5 new unit tests covering persistence, disk fallback, and schema queries.

### Fixed
- **Numpy bool serialization** — `is_keystone`/`is_bridge` were `np.bool_` (not
  Python `bool`), which broke GraphQL Boolean serialization. Cast to `bool()`.

## [2.7.0] - 2026-08-17

### Major — Sentry-Only Simplification
- **Removed CSV upload** — deleted `/analyze` (file upload) and `/sample-data` endpoints.
- **Removed the CLI** — deleted `reliability_modeler.py` and its `export.py` module.
- **Removed CSV parsing** — `modeler/data.py` now keeps only `categorize_description()`
  and `load_fault_categories()` (used by the Sentry connector). `load_failure_data()` removed.
- **Sentry is the sole ingestion source** — `/ingest/sentry` and `/ingest/sentry/projects`.
- **UI**: removed `FileUpload` component; the **Sentry** tab is now the default entry point.
- **Dependencies**: removed `python-multipart` and `python-dateutil` (no longer needed).

### Fixed
- **GraphQL introspection crash** — `graphene.Schema(introspection=False)` was never a valid
  argument and would crash the API on startup. Replaced with query-level introspection
  rejection in the `/graphql` endpoint.

### Documentation
- Rewrote `README.md`, `SUPPORT.md`, and `USER_MANUAL.md` for the Sentry-only workflow.
- Removed stale `documentation/` HTML files referencing the CSV/CLI flow.

### Removed files
- `reliability_modeler.py`, `modeler/export.py`, `run_analysis.bat`, `build_release.bat`,
  `web/api/sample_data.csv`, `input/error_log.csv`, ad-hoc test scripts, and stale logs.

## [2.6.0] - 2026-08-17

### Added — Multi-Project Sentry
- **`list_sentry_projects()`** — lists all projects in a Sentry org
  (paginated via Link header).
- **`load_sentry_failures_all()`** — aggregates failure events across every
  project in an org into one system-wide reliability timeline, returning a
  per-project breakdown. Each event description is tagged with `[project: X]`.
- **`GET /ingest/sentry/projects?org=X`** — list projects for the UI.
- **`POST /ingest/sentry`** now accepts `project: "all"` to aggregate every
  project, and returns a `projects` breakdown (sorted by failure count).
- **"Analyze all projects" toggle** in the Sentry tab.
- **Project Breakdown panel** in the Dashboard (horizontal bars, color-coded).
- **2 new unit tests** for `_normalize_raw_events`.

### Changed
- `load_sentry_failures` refactored to share `_fetch_project_events()` and
  `_normalize_raw_events()` helpers — single-project and multi-project paths
  are now consistent.
- Version bumped to 2.6.0.

## [2.5.0] - 2026-08-17

### Added — Sentry Integration
- **`modeler/sentry.py`** — connector that pulls failure events from the Sentry
  API and normalizes them into the exact same shape `load_failure_data()` produces,
  so the entire downstream pipeline (models, graphs, dashboard) works unchanged.
- **`POST /ingest/sentry`** endpoint — accepts `{org, project, days, future_hours}`,
  pulls events via cursor-paginated requests, and returns a full analysis.
- **Sentry tab in the UI** — org/project/days form + "Pull & Analyze" button,
  reuses the existing Dashboard. Setup requirements shown inline.
- **9 unit tests** for the connector (cursor parsing, timestamp parsing,
  description building with release/environment/exception context).

### Changed
- `run_analysis_pipeline` refactored into a core `_analyze_from_data()` that accepts
  pre-normalized data — enables non-CSV ingestion sources.
- Env vars documented: `SENTRY_AUTH_TOKEN`, `SENTRY_BASE_URL`,
  `NEXT_PUBLIC_API_KEY`, `ANALYSIS_TIMEOUT_SECONDS`.
- Version bumped to 2.5.0.

### Design notes
- Sentry events are counted as individual occurrences (not unique issues) for
  accurate MTBF math.
- Pagination capped at 50 pages (5000 events) with cursor-based Link-header parsing.
- Uses only stdlib (`urllib`) — no new runtime dependency.

## [2.4.0] - 2026-08-09

### Error Resilience
- **Request timeout** on `/analyze` — `asyncio.wait_for` with configurable
  `ANALYSIS_TIMEOUT_SECONDS` (default 120s). Prevents hung workers.
- **Atomic file writes** — log archives, config, and settings now use tmp-file +
  `os.fsync` + atomic rename to prevent corruption on concurrent writes.
- **Startup log pruning** — automatically removes log archives older than
  90 days on every container start. No more unbounded disk growth.

### Authentication UX
- **API key wired into UI** — all fetch calls in page.tsx, ConfigView, LogsView,
  and TrendsView now use a shared `apiFetch()` helper that injects `X-API-Key`
  when `NEXT_PUBLIC_API_KEY` is configured. UI no longer breaks when the API
  has auth enabled.
- **Shared API helper** (`web/ui/src/app/api.ts`) — single source for API URL,
  auth header, and 30s fetch timeout.

### Performance
- **Cached `/sample-data`** — first request computes and caches the result
  in memory. Subsequent requests return instantly.

### Testing
- **2 end-to-end smoke tests** — full pipeline (load → fit → export → verify)
  and CLI --help/--version verification.
- **20/20 tests pass** (18 unit + 2 e2e). Junk test artifacts cleaned.

### Changed
- Version bumped to 2.4.0 across CLI, API, and health endpoint.
- SUPPORT.md: documented `ANALYSIS_TIMEOUT_SECONDS` and `NEXT_PUBLIC_API_KEY`
  env vars, log pruning schedule.

## [2.3.4] - 2026-08-08

### Security
- CORS `allow_headers` includes `X-API-Key` and `allow_methods` includes `OPTIONS` (browser auth was blocked).
- `analysis_id` HTML-escaped in the `/report/{id}/html` template.
- API key comparison uses `secrets.compare_digest()` (constant time).
- Rate-limit store prunes only expired entries instead of clearing everything.
- `/graphql` enforces a 256 KB body limit.
- Next.js security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.

### Added
- Docker `HEALTHCHECK` for the API (`/health`) and UI images.

### Changed
- Version strings in the API and health endpoint corrected.

## [2.3.3] - 2026-08-08

### Changed
- UI dependencies bumped: next 16.1.6 -> 16.3.0, react/react-dom 19.2.3 -> 19.2.8, recharts ^3.10.1, tailwind-merge ^3.6.0, eslint-config-next 16.3.0, tailwindcss ^4.3.3 and matching `@types`.
- Python dependencies verified at latest; held back lucide-react 1.x, eslint 10 and TypeScript 7 (breaking changes).

## [2.3.2] - 2026-08-08

> Note: this release mainly moved the UI image to Node 22 and wrote up the changelog. Most security and fix items below were delivered in 2.3.1 and are listed here as originally documented.

### Security
- **API key authentication** — `X-API-Key` header checked against `RELIABILITY_API_KEY`
  env var. GET + /health exempt. Disabled when env var unset.
- **Path traversal fix** — `/report/{id}/html` rejects `..`, `/`, `\` and verifies
  resolved path stays inside log directory.
- **Stored XSS fix** — HTML report escapes filename and date before template interpolation.
- **GraphQL introspection disabled** — `introspection=False` on schema.
- **Rate-limit store pruning** — auto-clears when exceeding 1000 entries (memory DoS).
- **CORS whitespace fix** — origins from env var now stripped properly.

### Changed
- **Node 22 LTS** — Docker UI image upgraded from `node:20-alpine` to `node:22-alpine`
  (EOL 2027 vs 2026). `@types/node` bumped to `^22`.
- **Python 3.13** — Docker API image corrected from `python:3.14-slim` (no stable release)
  to `python:3.13-slim`.
- **GraphQL import** — now try/except for both package-mode and flat Docker layout.
- **AIC formula** in export.py now uses explicit `2*2 - 2*ll` (consistent with CLI/API).
- **Plot error handling** — exceptions now log full tracebacks (`exc_info=True`).
- CLI argparse description corrected to v2.3.0.

### Fixed
- `/logs` pagination: limit clamped to 1-200, offset to 0-10000.
- `settings.json` added to `.gitignore` (prevents accidental commits).
- Dead `ContextVar` import removed from `run_analysis_pipeline`.
- README version reference corrected to Next.js 16.1.

### Added
- Three new `fit_model` unit tests (GO convergence, MO convergence, n<3 edge case).
- `RELIABILITY_API_KEY` documented in SUPPORT.md env vars table.

### Tests
- 18/18 pass (3 new `fit_model` tests).

## [2.3.1] - 2026-08-08

### Security (audit fixes)
- `/report/{id}/html` path-traversal fix and HTML escaping of filename/date (stored XSS).
- API key middleware (`X-API-Key` vs `RELIABILITY_API_KEY`; GET and `/health` exempt at the time).
- Rate-limit store pruning above 1000 entries; CORS origin whitespace stripping.
- GraphQL introspection disabled.

### Fixed
- API image base corrected from `python:3.14-slim` to `python:3.13-slim`.
- GraphQL import works in both package and flat Docker layouts.
- `/logs` limit/offset clamped; `settings.json` added to `.gitignore`; consistent AIC formula; plot errors log tracebacks.

### Tests
- 3 new `fit_model` tests (18 total).

## [2.3.0] - 2026-08-08

### Added
- **Trend Comparison** (`GET /trends` + TrendsView): cross-run MTBF and failure rate
  trend charts comparing all archived analyses. Shows improving/degrading/stable
  direction with percentage change. Run-by-run data table included.
- **Failure Heatmap**: day-of-week × hour-of-day grid in the Dashboard. Color
  intensity shows failure density — spot temporal patterns at a glance.
- **HTML Executive Report** (`GET /report/{id}/html`): self-contained,
  print-ready HTML report with KPIs, summary, and embedded chart. Can be
  saved and emailed by any external scheduler (cron, CI, etc.).
- **Trends nav item** in the sidebar — new "Trends" tab between Dashboard and Logs.

### Changed
- Dashboard now includes the Failure Heatmap panel below the Risk Bubble chart.

## [2.2.0] - 2026-08-08

### Added
- **Interactive Recharts dashboard** — category bar chart, MTBF trend area chart,
  risk bubble chart (failure count × centrality), all with hover/tooltip support.
- **Fault Network Intelligence panel** — keystone categories with PageRank scores,
  top cascade chain, community count, and graph density surfaced in the UI.
- **Risk Landscape bubble chart** — ScatterChart plotting categories by failure
  count (y-axis) × graph centrality (x-axis), bubble size = impact score.
- **MTBF Trend chart** — rolling-window MTBF over time using ComposedChart with
  area fill, showing whether reliability is improving or degrading.
- **5-KPI row** — added Failure Rate (failures/hour) as a fifth KPI card.

### Changed
- **Dashboard completely rewritten** — Recharts now renders interactive charts
  (BarChart, ScatterChart, ComposedChart, AreaChart) instead of only static PNGs.
- Model comparison panel now integrated alongside Graph Insight card.
- Recent failures list increased to 50 items with improved formatting.
- PNG plots retained as high-quality fallback for reliability growth and intensity.

## [2.1.0] - 2026-08-08

### Added
- **NetworkX graph analytics engine** (`modeler/graphs.py`): co-occurrence graph,
  temporal-proximity fallback, cascade graph, PageRank/betweenness centrality,
  Louvain community detection, cascade chain DFS extraction.
- **Graphene GraphQL endpoint** (`POST /graphql`): typed schema for querying
  failure graph data — `failureGraph`, `keystoneCategories`, `cascadeChains`.
- **Graph insights in export** — human_summary.txt now includes keystone
  categories, cascade chains, communities, and graph health metrics.
- 9 new unit tests for graph module (15/15 pass total).

## [2.0.3] - 2026-08-08

### Added
- `GET /logs` pagination (`{"total", "logs"}` with limit/offset) and `POST /logs/prune` (default 90 days); Logs view page controls.
- CI workflow (`.github/workflows/test.yml`): unit tests, API integration tests, Docker build of both images.
- SUPPORT.md section on config persistence (ephemeral storage risk, Kubernetes PVC example); startup warning when config is on temporary paths.

### Fixed
- Per-category "remaining failures" extrapolation now uses a practical forecast horizon instead of the unbounded asymptote (e.g. "117 more" instead of "76828 more").

### Documentation
- README notice that the application is for internal networks only.

## [2.0.2] - 2026-08-08

### Changed
- **Python 3.14 support** — upgraded all dependencies and Docker base image to Python 3.14.
  - numpy 1.26.4 → 2.5.1
  - scipy 1.13.1 → 1.18.0
  - matplotlib 3.9.2 → 3.11.1
  - pandas 2.2.3 → 3.0.5
  - fastapi 0.115.6 → 0.141.1
  - uvicorn 0.34.0 → 0.52.1
  - pytest 8.3.4 → 9.1.1
  - All unit tests (6/6) and full CLI pipeline pass on Python 3.14.

## [2.0.1] - 2026-08-08

### Security
- **Fixed path traversal** via uploaded filename — now uses UUID-based filenames.
- **Added config validation** on POST /config — taxonomy syntax and optimizer method are validated before writing.
- **Restricted CORS** — origins are now configurable via `ALLOWED_ORIGINS` env var, `allow_credentials` disabled.
- **Added rate limiting** — 30 requests per 60 seconds per client IP, configurable via env vars.
- **Sanitized error responses** — API no longer leaks internal tracebacks to clients.

### Added
- **`/health` endpoint** — returns `{"status": "ok", "version": "..."}` for load balancer probes.
- **Structured JSON logging** — API logs include timestamps, levels, and request IDs.
- **Request ID middleware** — every request gets an `X-Request-ID` header for correlation.
- **Integration test suite** — 13 tests covering `/health`, `/analyze`, `/config`, `/logs`, CORS, and error cases.
- **pytest.ini** — standard pytest configuration.
- **SUPPORT.md** — operational runbook with troubleshooting, deployment, and escalation procedures.
- **LICENSE** — MIT license added.
- **`--max-iter` CLI flag** — control optimizer iteration limit.
- **`--version` CLI flag** — prints version string.

### Changed
- **AIC formula unified** — both CLI and API now use `AIC = 2k - 2·ln(L)` via shared helper.
- **CLI exit codes** — `sys.exit(1)` on failure instead of `return` (exit code 0).
- **Dependency versions pinned** — all requirements now specify exact versions.
- **docker-compose.yml** — uses pre-built images with version tags, adds health-relevant env vars.
- **Hessian fallback** — uses pseudo-inverse when Hessian is singular (was crashing).
- **MO asymptote** — uses 1e6 hours instead of 1e9 for numerical stability.
- **Optimizer timeout** — added `maxiter` parameter (default 5000) to scipy minimize calls.
- **CSV parse errors** — now include row-level detail and percentage in log warnings.
- **Export module** — plots are generated after CSVs; failures are tracked and reported.

### Fixed
- **Cross-platform test runner** — tests now run via `python -m pytest` instead of PowerShell-only.
- **README version** — corrected Next.js version reference (14 → 16).
- **Removed dead `data_scrubbing` toggle** — was accepted but never implemented.

### Removed
- **`pyinstaller` from root requirements** — moved to dev-only concern.
- **`DOCKERHUB_USERNAME` from `.env`** — no real credentials in repo.

## [2.0.0] - 2026-02-21

### Added (Web Architecture)
-   **Containerized Web UI**: Full migration from CLI-only to a dual-tier Next.js and FastAPI architecture.
-   **Executive Dashboard**: Management-optimized UI with Recharts visualizations and real-time KPIs.
-   **Functional Log Archives**: Persistent analysis history with search and status tracking.
-   **Interactive Configurations**: Live-editor for fault taxonomy and analysis behavioral toggles.
-   **Advanced Engine Controls**: UI support for optimization algorithm selection and fitting tolerance.
-   **Methodology View**: Embedded documentation for GO and MO models directly in the app.
-   **Persistence Layer**: Introduced `settings.json` and automated log archiving in the Docker environment.
-   **CSV Format Guide**: Visual in-app guide for data ingestion.

## [1.0.0] - 2026-02-17

### Initial Release
-   **Reliability Modeler**: Core tool for fitting Goel-Okumoto and Musa-Okumoto models.
-   **Failure Intensity Visualization**: Stability charts showing failure rate over time.
-   **Release Build System**: Automated creation of standalone executables.
-   **Date-Based Output**: Automatic organization of results by date.
-   **Reporting**: Detailed CSVs, plots, and human-readable summaries.
