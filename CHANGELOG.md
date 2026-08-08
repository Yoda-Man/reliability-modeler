# Changelog

All notable changes to the **Reliability Modeler** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
