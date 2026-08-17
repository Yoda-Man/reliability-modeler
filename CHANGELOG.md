# Changelog

All notable changes to the **Reliability Modeler** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.0] - 2025-08-08

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

## [2.6.0] - 2025-08-08

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

## [2.5.0] - 2025-08-08

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

## [2.4.0] - 2025-08-08

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

## [2.3.2] - 2025-08-08

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

## [2.3.0] - 2025-08-08

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

## [2.2.0] - 2025-08-08

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

## [2.1.0] - 2025-08-08

### Added
- **NetworkX graph analytics engine** (`modeler/graphs.py`): co-occurrence graph,
  temporal-proximity fallback, cascade graph, PageRank/betweenness centrality,
  Louvain community detection, cascade chain DFS extraction.
- **Graphene GraphQL endpoint** (`POST /graphql`): typed schema for querying
  failure graph data — `failureGraph`, `keystoneCategories`, `cascadeChains`.
- **Graph insights in export** — human_summary.txt now includes keystone
  categories, cascade chains, communities, and graph health metrics.
- 9 new unit tests for graph module (15/15 pass total).

## [2.0.2] - 2025-08-08

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

## [2.0.1] - 2025-08-08

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
