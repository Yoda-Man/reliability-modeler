# Software Reliability Growth Modeler

A **Sentry-powered** web application that turns your existing error-monitoring data into actionable reliability intelligence. It fits the **Goel-Okumoto (GO)** and **Musa-Okumoto (MO)** Non-Homogeneous Poisson Process (NHPP) models to your Sentry failure events to predict MTBF, residual faults, and release readiness.

> **⚠️ Design Decision — Internal Network Only**
> This application is designed for **internal/VPN deployment only**. It intentionally omits internet-facing hardening. Deploy it behind your organization's network boundary or VPN.

> **Data Source — Sentry only**
> This tool ingests failure data **exclusively from Sentry**. There is no CSV upload, no file import, and no CLI — the source of truth is your Sentry error events.

## What it tells you

- **MTBF evolution** — current and projected system reliability
- **Predicted residuals** — how many latent faults likely remain
- **Release readiness** — when the software reaches a stability threshold
- **Keystone failures** — which fault categories (via graph centrality) drive the most downstream impact
- **Failure cascades** — which errors predictably trigger others
- **Cross-project breakdown** — which Sentry project contributes the most failures

## How it works

1. **Configure Sentry access** — set `SENTRY_AUTH_TOKEN` on the API server.
2. **Connect** — open the **Sentry** tab, enter your org (and optionally a project, or "all projects").
3. **Analyze** — the engine pulls events from Sentry, categorizes them via your fault taxonomy, fits the GO/MO models, and renders an interactive dashboard.

## Architecture

```
┌──────────────┐     HTTP :8000     ┌──────────────┐     ┌─────────────┐
│   Next.js UI │ ─────────────────▶ │  FastAPI API │ ──▶ │    Sentry    │
│   Port 3000  │                    │   Port 8000  │     │   API (pull) │
└──────────────┘                    └──────────────┘     └─────────────┘
```

| Layer | Location | Purpose |
|-------|----------|---------|
| UI | `web/ui` | Next.js 16 frontend (Tailwind, Recharts, Lucide) |
| API | `web/api` | FastAPI server — Sentry ingestion, analysis, GraphQL |
| Engine | `modeler/` | GO/MO NHPP models, graph analytics, Sentry connector |

## Deployment

```bash
docker-compose up
```

- **Web UI**: http://localhost:3000
- **API**: http://localhost:8000
- **API docs (Swagger)**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

## Configuration

Set these environment variables on the API container:

| Variable | Required | Purpose |
|----------|----------|---------|
| `SENTRY_AUTH_TOKEN` | ✅ | Org token with `event:read` + `project:read` scope |
| `SENTRY_BASE_URL` | ❌ | Override for self-hosted Sentry (default `https://sentry.io/api/0/`) |
| `RELIABILITY_API_KEY` | ❌ | Shared secret for POST/DELETE auth (leave empty to disable) |

See [`SUPPORT.md`](SUPPORT.md) for the full runbook, and [`USER_MANUAL.md`](USER_MANUAL.md) for the end-user guide.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/ingest/sentry` | Pull events from Sentry and run analysis (`project: "all"` aggregates every project) |
| GET | `/ingest/sentry/projects` | List projects in an org |
| GET | `/config` | Get fault taxonomy and settings |
| POST | `/config` | Update fault taxonomy and settings |
| GET | `/logs` | Paginated analysis archive |
| GET | `/trends` | Cross-run MTBF/failure-rate comparison |
| GET | `/report/{id}/html` | Self-contained HTML executive report |
| POST | `/graphql` | Failure graph queries |

## Development

```bash
# Install Python dependencies
pip install -r requirements.txt -r web/api/requirements.txt

# Run tests
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v

# Run the API locally
cd web/api && uvicorn main:app --reload
```

## Maintainers

- **Primary**: Reliability Engineering Team
- **Repository**: https://github.com/Yoda-Man/reliability-modeler
- **Contact**: File an issue on the GitHub repository.

## License

MIT — see [`LICENSE`](LICENSE).
