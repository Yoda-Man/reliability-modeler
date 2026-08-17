# Reliability Modeler — Operations & Support Runbook

## 1. Service Overview

The Reliability Modeler is a two-tier containerized application that ingests failure data **exclusively from Sentry**:

```
┌──────────────┐     HTTP :8000     ┌──────────────┐     ┌─────────────┐
│   Next.js UI │ ─────────────────▶ │  FastAPI API │ ──▶ │    Sentry    │
│   Port 3000  │                    │   Port 8000  │     │  API (pull)  │
└──────────────┘                    └──────┬───────┘     └─────────────┘
                                          │
                                          ▼
                                    ┌──────────┐
                                    │ modeler/ │  Python NHPP engine
                                    │ output/  │  Logs & archives
                                    └──────────┘
```

- **API**: Python 3.13+ FastAPI server. CPU-bound (scipy optimization, matplotlib rendering).
- **UI**: Next.js 16 client-rendered SPA. Talks to API exclusively.
- **Data source**: Sentry (pulled on demand). No CSV upload, no CLI.
- **No database**: State is file-based (JSON log archives, settings.json, fault_categories.conf).

### ⚠️ Critical: Config Persistence

`fault_categories.conf` and `settings.json` are written to the API container's local filesystem. **If the container restarts without a persistent volume, ALL configuration changes are lost.**

| Deployment | What you need |
|------------|---------------|
| **Docker Compose** | Mount a volume (see `docker-compose.yml`) |
| **Kubernetes** | Create a `PersistentVolumeClaim` and mount it at `/app` in the API pod |
| **Bare metal** | Point config paths at persistent storage |

The startup log warns if write targets are on ephemeral storage. Check `docker logs` after deploy.

## 2. Common Failure Modes & Remedies

### 2.1 "No failure events found" from Sentry ingest

**Likely causes:**
1. **Bad or missing token** — `SENTRY_AUTH_TOKEN` not set, expired, or lacks `event:read` scope.
   - *Fix*: Verify the token, check scopes in Sentry's "Auth Tokens" page.
2. **Wrong org/project slug** — slugs are case-sensitive.
   - *Fix*: Use `GET /ingest/sentry/projects?org=X` to list exact slugs.
3. **No events in the look-back window** — the project had no errors in the selected period.
   - *Fix*: Increase the day range or check Sentry directly.

### 2.2 "502 Bad Gateway" on `/ingest/sentry`

Sentry returned an error (401 auth, 404 not found, 429 rate-limited, or network failure). The API logs the specific reason. Check `docker logs` and grep for `Sentry ingest failed`.

### 2.3 "429 Too Many Requests" (Sentry rate limit)

Pulling "all projects" across a large org can hit Sentry's API rate limits. Narrow the look-back window, or analyze a single project at a time. The connector caps 5000 events per project and skips failures gracefully.

### 2.4 Model fails to converge (NaN/empty results)

Data is too sparse (< 3 events) or all timestamps are identical. Narrow the scope to a busier project or widen the time window.

### 2.5 Config changes not persisting after container restart

Use a Docker volume mount for `fault_categories.conf` and `settings.json` (see section 1).

### 2.6 UI shows "Failed to pull data from Sentry"

- Check `SENTRY_AUTH_TOKEN` is set on the API container (not the UI).
- Verify `NEXT_PUBLIC_API_URL` points at the API.
- Check browser console for CORS errors — ensure `ALLOWED_ORIGINS` includes the UI origin.

## 3. Logging & Monitoring

### API Logs
- Format: JSON-structured to stdout
- Fields: `time`, `level`, `logger`, `message`
- Each request gets an `X-Request-ID` header for correlation.
- Log level: `INFO` by default.

```bash
docker logs reliability-modeler-api-1
docker logs -f reliability-modeler-api-1 2>&1 | grep '"level": "ERROR"'
```

### Health Checks
- **Endpoint**: `GET /health` → `{"status": "ok", "version": "2.7.0", "timestamp": "..."}`
- Use for load balancer probes. Expected: HTTP 200, response < 100ms.

## 4. Deployment & Rollback

### Deploy
```bash
# Build and push images
make build push IMAGE_TAG=v2.7.0

# On target host
docker-compose pull
docker-compose up -d
```

### Rollback
```bash
IMAGE_TAG=v2.6.0 docker-compose up -d
```

### Verify deployment
```bash
curl http://localhost:8000/health
curl http://localhost:3000  # Should return HTML
```

## 5. Environment Variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `SENTRY_AUTH_TOKEN` | API | (required) | Sentry org token with `event:read` + `project:read` scope |
| `SENTRY_BASE_URL` | API | `https://sentry.io/api/0/` | Override for self-hosted Sentry |
| `ALLOWED_ORIGINS` | API | `http://localhost:3000` | Comma-separated CORS origins |
| `RELIABILITY_API_KEY` | API + UI | (empty = disabled) | Shared secret. API validates it; UI proxy injects it server-side |
| `API_URL` | UI | `http://localhost:8000` | Backend URL the Next.js proxy forwards to (server-side) |
| `RATE_LIMIT_MAX` | API | `30` | Max requests per window |
| `RATE_LIMIT_WINDOW` | API | `60` | Rate limit window (seconds) |
| `ANALYSIS_TIMEOUT_SECONDS` | API | `120` | Max seconds per analysis request |
| `DOCKERHUB_USERNAME` | Build | (required) | Docker Hub username for push |
| `IMAGE_TAG` | Build | git hash | Docker image tag |

> **Note on authentication:** `RELIABILITY_API_KEY` is a *shared secret* for a trusted internal network, not a cryptographic security boundary. The key is held server-side by the Next.js proxy (never shipped to the browser bundle) and required on all non-`/health` routes. When unset, auth is disabled and the API logs a warning at startup.

## 6. Escalation

| Issue Type | First Response | Escalate To |
|------------|---------------|-------------|
| Sentry ingest errors | Check token/scopes, API logs | Development team |
| Container won't start | Check Docker logs, port conflicts | Infrastructure team |
| Model produces NaN/Inf | Check data volume, optimizer | Data science team |
| Security incident | Take API offline, rotate credentials | Security team |
| UI rendering issues | Check browser console, API connectivity | Frontend team |

## 7. Backup & Recovery

- **Log archives**: Stored in `output/logs/`. Back up this directory.
- **Configuration**: Back up `fault_categories.conf` and `web/api/settings.json`.
- **Recovery**: Restore files to the same paths and restart containers.

## 8. Capacity Planning

- The API is CPU-bound (scipy MLE fits + matplotlib rendering).
- Estimated: 2-5 seconds per analysis on ~1000 events.
- Sentry pulls are the bottleneck for large orgs — respect Sentry's rate limits.
- Recommend 1 vCPU per 5 concurrent analysis requests.
- Memory: ~256MB baseline, peaks at ~512MB during rendering.
