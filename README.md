# Software Reliability Growth Modeler

A **Sentry-powered** web application that turns your existing error-monitoring data into reliability intelligence. It fits the **Goel-Okumoto (GO)** and **Musa-Okumoto (MO)** Non-Homogeneous Poisson Process (NHPP) models to Sentry failure events to estimate MTBF, residual faults and release readiness.

Current version: **2.9.0** (see [`CHANGELOG.md`](CHANGELOG.md)).

> **Internal network only.** The application is designed to run behind your organisation's network boundary or VPN. It has authentication (API key + UI login) but is not hardened as an internet-facing service.

> **Data source: Sentry only.** There is no CSV upload, file import or CLI.

## What it tells you

- **MTBF evolution**: current and projected reliability
- **Predicted residuals**: how many latent faults likely remain
- **Release readiness**: when the software reaches a stability threshold
- **Keystone failures**: fault categories that drive the most downstream impact (graph centrality)
- **Failure cascades**: errors that predictably trigger others
- **Cross-project breakdown**: which Sentry project contributes the most failures

## Quick start (Docker)

Requirements: Docker Engine 24+ with the Compose plugin.

```bash
cp .env.example .env
chmod 600 .env

# Edit .env and set at least:
#   RELIABILITY_API_KEY=<output of: openssl rand -hex 32>
#   UI_PASSWORD=<a strong password>
#   SENTRY_AUTH_TOKEN=<Sentry token with event:read + project:read>   (optional, needed to ingest)

docker compose up -d
docker compose ps        # both services should become "healthy"
```

Open **http://localhost:3000** and log in with `UI_USERNAME` (default `admin`) and `UI_PASSWORD`.

`docker compose` refuses to start if `RELIABILITY_API_KEY` or `UI_PASSWORD` is missing.

To run a specific release, set `IMAGE_TAG` (e.g. `IMAGE_TAG=2.9.0`) in `.env`. Operations procedures (upgrade, rollback, backup, secret rotation) are in [`RUNBOOK.md`](RUNBOOK.md).

## Architecture

```
                 host :3000 (only published port)
Browser ──HTTP Basic auth──▶ ┌────────────────────────────┐
                             │ UI  (Next.js, port 3000)   │
                             │  • login middleware        │
                             │  • /healthz                │
                             │  • /api/* server-side proxy│──┐ adds X-API-Key,
                             └────────────────────────────┘  │ X-Request-ID,
                                                             │ X-Forwarded-For
                        internal compose network only        ▼
                             ┌────────────────────────────┐      ┌──────────────┐
                             │ API (FastAPI, port 8000)   │ ───▶ │ Sentry API   │
                             │  • auth on every route     │ pull │ (HTTPS)      │
                             │    except /health*         │      └──────────────┘
                             │  • modeler/ NHPP engine    │
                             └─────────────┬──────────────┘
                                           │
                      volume config_data ──┤── /app/config  (fault_categories.conf, settings.json)
                      volume output_data ──┘── /app/output  (archives, analyses, plots)
```

| Layer | Location | Purpose |
|-------|----------|---------|
| UI | `web/ui` | Next.js frontend, login, server-side proxy to the API |
| API | `web/api` | FastAPI: Sentry ingestion, analysis, GraphQL, health, metrics |
| Engine | `modeler/` | GO/MO NHPP models, graph analytics, Sentry connector |

The browser never talks to the API directly and never sees the API key: the UI proxy injects it server-side. Port 8000 is not published to the host.

## Authentication

- **API**: every route requires the `X-API-Key: <RELIABILITY_API_KEY>` header **except** `GET /health` and `GET /health/live`. This includes `/docs`, `/redoc`, `/openapi.json` and `/metrics`. The API refuses to start without a key (unless `ALLOW_INSECURE_NO_AUTH=true`, for local development only).
- **UI**: HTTP Basic auth on every route except `/healthz`, using `UI_USERNAME` / `UI_PASSWORD`. If `UI_PASSWORD` is empty the UI returns `503 UI_PASSWORD not configured` (unless `UI_AUTH_DISABLED=true`, for local development only).
- The API key is a shared secret on a trusted network, not a per-user identity. Rotate it as described in the runbook.

## Configuration

### API

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `RELIABILITY_API_KEY` | **yes** | none | Shared secret; also given to the UI service |
| `SENTRY_AUTH_TOKEN` | for ingestion | empty | Sentry token with `event:read` + `project:read`. Without it `/health` is `degraded` |
| `SENTRY_BASE_URL` | no | `https://sentry.io/api/0/` | Self-hosted Sentry |
| `ALLOWED_ORIGINS` | no | `http://localhost:3000` | CORS origins (only for direct browser access to the API) |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `RETENTION_DAYS` | no | `90` | Prune archives/analyses/plots older than N days at startup and daily; `0` disables |
| `ANALYSIS_TIMEOUT_SECONDS` | no | `120` | Max time per analysis |
| `MAX_BODY_BYTES` | no | `1048576` | Request body limit for POST routes |
| `RATE_LIMIT_PER_MINUTE` | no | `30` | Per client IP |
| `CONFIG_DIR` | no | repo root locally, `/app/config` in Docker | Holds `fault_categories.conf` and `settings.json`; seeded from the default on first start |
| `DEFAULT_CONFIG_PATH` | no | `<repo>/fault_categories.conf`, `/app/defaults/fault_categories.conf` in Docker | Bundled default taxonomy |
| `OUTPUT_DIR` | no | `<repo>/output`, `/app/output` in Docker | Archives, analyses, plots |
| `ALLOW_INSECURE_NO_AUTH` | no | `false` | Local development only |

### UI

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `UI_PASSWORD` | **yes** | none | Login password |
| `UI_USERNAME` | no | `admin` | Login username |
| `API_URL` | no | `http://api:8000` in compose | Where the proxy forwards `/api/*` (server-side only) |
| `RELIABILITY_API_KEY` | **yes** | none | Injected by the proxy; must match the API |
| `PROXY_TIMEOUT_MS` | no | `130000` | Proxy timeout; keep above `ANALYSIS_TIMEOUT_SECONDS` |
| `UI_AUTH_DISABLED` | no | `false` | Local development only |

### Compose / release

| Variable | Default | Purpose |
|----------|---------|---------|
| `IMAGE_TAG` | `latest` | Image tag to run; pin in production, change to roll back |
| `DOCKERHUB_NAMESPACE` | `trustaldo` | Image namespace |
| `UI_PORT` | `3000` | Host port for the UI |
| `DOCKERHUB_USERNAME` | `trustaldo` | Used by `make push` |

[`.env.example`](.env.example) documents every variable.

## API reference

All routes except `/health` and `/health/live` need `X-API-Key`. Errors are JSON `{"detail": "..."}`; every response carries `X-Request-ID`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/live` | Liveness: always `{"status":"ok"}` |
| GET | `/health` | Readiness with checks and version; 503 if output/config unusable |
| GET | `/metrics` | Prometheus metrics |
| POST | `/ingest/sentry` | Pull events from Sentry and run analysis (`project: "all"` aggregates every project) |
| GET | `/ingest/sentry/projects` | List projects in an org |
| GET | `/config` | Fault taxonomy and settings |
| POST | `/config` | Update fault taxonomy and settings |
| GET | `/logs` | Paginated analysis archive |
| POST | `/logs/prune` | Delete archives older than N days |
| GET | `/trends` | Cross-run MTBF/failure-rate comparison |
| GET | `/report/{id}/html` | Self-contained HTML executive report |
| POST | `/graphql` | Failure-graph queries over persisted analyses |

Analysis IDs look like `AN-20261010-142233-a1b2c3` (UTC timestamp + random suffix). IDs from releases before 2.9.0 (`AN-YYYYMMDD-HHMMSS`) remain valid.

### GraphQL examples

```graphql
{ availableAnalyses }

{ keystoneCategories(analysisId: "AN-20261010-142233-a1b2c3") { node pagerank isBridge } }

{ cascadeChains(analysisId: "AN-20261010-142233-a1b2c3") { chain confidence } }

{ failureGraph(analysisId: "AN-20261010-142233-a1b2c3") {
    graphMetrics { numCategories numCascadeEdges }
    centralityScores { node pagerank isKeystone }
  }
}

# Which category is consistently keystone across analyses?
{ keystoneCategoriesAcross(limit: 10) { node keystoneCount avgPagerank totalAnalyses } }
```

## Local development

Python 3.13 and Node 22 (the versions the images use).

```bash
# Python
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r web/api/requirements.txt -r requirements.txt -r requirements-dev.txt

# API (runs from web/api; CONFIG_DIR/OUTPUT_DIR default to the repo root / ./output)
cd web/api
RELIABILITY_API_KEY=dev-key uvicorn main:app --reload --port 8000

# UI (second terminal)
cd web/ui
npm ci
API_URL=http://127.0.0.1:8000 RELIABILITY_API_KEY=dev-key UI_PASSWORD=dev npm run dev
# open http://localhost:3000 (user admin / password dev)
```

### Tests and tooling

```bash
make help        # list targets
make test        # Python unit tests with coverage + UI tests
make build       # build both images locally (current architecture), tagged :<VERSION>
make smoke       # start the built images in a throwaway compose project and verify health/auth/proxy
```

CI (`.github/workflows/test.yml`) runs unit tests with a 75% coverage floor, API integration tests, UI lint/typecheck/test/build, `npm audit`, `pip-audit`, and a Docker build + smoke test. Releases are built for `linux/amd64` and `linux/arm64` by `make push` or `.github/workflows/release.yml`.

## Documentation

- [`USER_MANUAL.md`](USER_MANUAL.md): end-user guide
- [`SUPPORT.md`](SUPPORT.md): architecture, monitoring, troubleshooting, capacity
- [`RUNBOOK.md`](RUNBOOK.md): deploy, upgrade, rollback, rotation, backup/restore, incidents

## Ownership

| Role | Contact |
|------|---------|
| Service owner | Marwa Trust Mutemasango |
| Team channel | trustaldo@gmail.com |
| Escalation | trustaldo@gmail.com |
| Repository | https://github.com/Yoda-Man/reliability-modeler |

## License

MIT, see [`LICENSE`](LICENSE).
