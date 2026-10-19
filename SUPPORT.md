# Reliability Modeler: Operations & Support

Reference for operators: architecture, persistence, monitoring, logging, troubleshooting and capacity. Step-by-step procedures (deploy, upgrade, rollback, secret rotation, backup/restore, incident table) are in [`RUNBOOK.md`](RUNBOOK.md).

Applies to version **2.14.0**.

## 1. Service overview

```
Browser ──Basic auth──▶ UI (Next.js) :3000 ──/api/* proxy──▶ API (FastAPI) :8000 ──▶ Sentry API
          (host port)    login, /healthz      X-API-Key        internal only          (pull, HTTPS)
                                              X-Request-ID          │
                                              X-Forwarded-For       ├── /app/config  (volume config_data)
                                                                    └── /app/output  (volume output_data)
```

- **UI**: Next.js server. Enforces HTTP Basic auth (`UI_USERNAME`/`UI_PASSWORD`) on every route except `/healthz`. Proxies `/api/*` to `API_URL` and injects `RELIABILITY_API_KEY` server-side. Only GET/POST are proxied, bodies are limited to 1 MiB, timeout `PROXY_TIMEOUT_MS` (default 250 s). The client address forwarded to the API (`X-Forwarded-For`, used for per-IP rate limiting) is the socket address; an incoming `X-Forwarded-For` is honoured only with `TRUST_PROXY=true` (set it only behind a reverse proxy that sets that header itself).
- **API**: Python 3.13 FastAPI. CPU-bound (scipy fits, matplotlib rendering); analysis runs in a worker thread so `/health` stays responsive. Requires `X-API-Key` on every route except `/health` and `/health/live`.
- **Data source**: Sentry, pulled on demand. No CSV upload, no CLI.
- **No database**: state is files on two volumes.

Because the browser only talks to the UI (same origin), there is no CORS involved in normal operation. `ALLOWED_ORIGINS` only matters if a browser calls the API directly, which the default deployment does not allow.

## 2. Persistence

| Path in API container | Compose volume | Contents | Loss impact |
|-----------------------|----------------|----------|-------------|
| `/app/config` | `config_data` | `fault_categories.conf`, `settings.json` | Taxonomy/settings edits revert to defaults |
| `/app/output` | `output_data` | Log archives, persisted analyses (GraphQL), plots | History, trends and reports lost |
| `/app/defaults/fault_categories.conf` | (in image) | Bundled default taxonomy | n/a, read-only |

On startup, if `CONFIG_DIR/fault_categories.conf` is missing, the API seeds it from `DEFAULT_CONFIG_PATH`. Later image upgrades **do not** overwrite an existing taxonomy in `config_data`.

The UI is stateless.

### Kubernetes

Mount two PersistentVolumeClaims on the API pod, **at `/app/output` and `/app/config` only**. Never mount a volume at `/app`: it would hide the application code and the bundled defaults.

```yaml
# API container (excerpt)
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  fsGroup: 10001          # set on the pod spec so the PVCs are writable
volumeMounts:
  - name: output
    mountPath: /app/output
  - name: config
    mountPath: /app/config
livenessProbe:
  httpGet: { path: /health/live, port: 8000 }
readinessProbe:
  httpGet: { path: /health, port: 8000 }
volumes:
  - name: output
    persistentVolumeClaim: { claimName: reliability-modeler-output }
  - name: config
    persistentVolumeClaim: { claimName: reliability-modeler-config }
```

UI pod: liveness/readiness `GET /healthz` on port 3000; `API_URL` pointing at the API Service.

## 3. Health checks

| Endpoint | Auth | Use | Response |
|----------|------|-----|----------|
| API `GET /health/live` | none | Container HEALTHCHECK / liveness | `200 {"status":"ok"}` always while the process serves |
| API `GET /health` | none | Readiness, monitoring | see below |
| UI `GET /healthz` | none | Container HEALTHCHECK / liveness | `200 ok` |
| UI `GET /api/health` | UI login | End-to-end check through the proxy; drives the UI status badge | API `/health` body |

`GET /health` example:

```json
{
  "status": "degraded",
  "version": "2.14.0",
  "timestamp": "2026-10-10T14:22:33.123456+00:00",
  "checks": {
    "output_writable": true,
    "config_readable": true,
    "sentry_token_configured": false
  }
}
```

| `status` | HTTP | Meaning |
|----------|------|---------|
| `ok` | 200 | All checks pass |
| `degraded` | 200 | Only `sentry_token_configured` is false: the app runs, ingestion will fail |
| `error` | 503 | Output volume not writable or config unreadable |

Since port 8000 is not published, check the API from inside the network:

```bash
docker compose exec api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
curl -u admin:"$UI_PASSWORD" http://localhost:3000/api/health
```

## 4. Metrics and alerting

`GET /metrics` (API, requires `X-API-Key`) returns Prometheus text format:

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `rm_http_requests_total` | counter | `method`, `status` | HTTP requests served |
| `rm_analyses_total` | counter | `result` | Analyses run, by outcome |
| `rm_analysis_duration_seconds_sum` / `_count` | summary-style counters | none | Total analysis time and count (average = sum / count) |
| `rm_ingest_failures_total` | counter | none | Failed Sentry ingests |

The endpoint requires the `X-API-Key` header, so the scraper must be able to send a custom header and must run inside the compose/cluster network (port 8000 is not published). Use your scraper's custom-header option if it has one, or a small header-injecting reverse proxy / sidecar in front of `api:8000/metrics`.

Suggested alerts (tune thresholds to your environment):

| Alert | Condition (example) | Severity |
|-------|---------------------|----------|
| API not healthy | `/health` non-200 for 5 min (blackbox probe) | page |
| API degraded | `/health` status `degraded` for 30 min | ticket |
| Ingest failures | `increase(rm_ingest_failures_total[15m]) > 3` | ticket |
| Slow analyses | average or p95 analysis duration > 60 s over 30 min (`rate(rm_analysis_duration_seconds_sum[30m]) / rate(rm_analysis_duration_seconds_count[30m])`; true p95 needs a histogram, so approximate with the average) | ticket |
| Server errors | `sum(rate(rm_http_requests_total{status=~"5.."}[5m])) > 0.1` | ticket |
| Container restarts | restart count increased in 15 min (`docker inspect -f '{{.RestartCount}}'`, cAdvisor or kube-state-metrics) | page if repeated |
| Disk usage | filesystem holding `output_data` > 80% | ticket |

## 5. Logging

Both services log to stdout. The API logs one JSON object per line:

```json
{"ts": "2026-10-10T14:22:33.123Z", "level": "INFO", "logger": "reliability_api", "msg": "Analysis complete", "request_id": "3f2c9a1e-..."}
```

| Field | Meaning |
|-------|---------|
| `ts` | UTC timestamp |
| `level` | `DEBUG`/`INFO`/`WARNING`/`ERROR` (set with `LOG_LEVEL`) |
| `logger` | Python logger name |
| `msg` | Message (never contains the API key or Sentry token) |
| `request_id` | Value of `X-Request-ID` for the request, or empty for background work |

The UI proxy logs its errors server-side as JSON as well. Compose keeps container logs with the json-file driver, rotated at 10 MB x 5 files per container.

```bash
docker compose logs -f api
docker compose logs api | grep '"level": "ERROR"'
docker compose logs api ui | grep '<request-id>'     # correlate one request across UI and API
```

`X-Request-ID` is generated by the UI proxy (or accepted from the client after sanitising), forwarded to the API and returned in the response header, so a user can report the ID shown in their browser's network tab.

## 6. Retention

`RETENTION_DAYS` (default **90**) controls automatic pruning of log archives, persisted analyses and plots in `/app/output`. Pruning runs at API startup and then once a day. `RETENTION_DAYS=0` disables automatic pruning. Manual pruning: `POST /logs/prune` (minimum 7 days).

Pruned analyses are no longer available to GraphQL, trends or reports. Take a backup first if you need long-term history (see the runbook).

## 7. Troubleshooting

The incident table (symptom, cause, fix) is in [`RUNBOOK.md`](RUNBOOK.md#common-failures). Sentry-specific issues:

### "No failure events found"
1. Token missing, expired, or lacking `event:read` (check `/health` → `sentry_token_configured`, then token scopes in Sentry).
2. Wrong org/project slug (case-sensitive). List slugs with the project picker or `GET /ingest/sentry/projects?org=<org>`.
3. No events in the look-back window: widen the window.

### 502 on `/ingest/sentry`
Sentry returned an error (401, 404, 429 or network failure). Transient errors (429, 5xx) are retried with backoff before failing. The specific reason is in the API log (`grep -i sentry`); it is not echoed to clients. `rm_ingest_failures_total` increments.

### Sentry rate limiting
"All projects" across a large org can hit Sentry's API limits. Narrow the window or analyse one project at a time. The connector caps 5000 events per project and 50 projects per aggregation.

### Model fails to converge
Fewer than 3 events, or identical timestamps. Use a busier project or a wider window.

### UI shows "Failed to pull data from Sentry"
- The Sentry token is either connected on the Sentry page (saved as `/app/config/sentry_token`, mode 0600) or set as `SENTRY_AUTH_TOKEN` on the **api** service; the environment variable wins. `GET /config/sentry` shows which is in use without revealing it.
- Organization tokens (`sntrys_`) get 403 from Sentry: use a personal (`sntryu_`) or internal-integration token with `event:read`, `project:read`, `org:read`.
- Backups of `config_data` contain the saved token; keep them private (`backup.sh` writes them 0600).
- The UI reaches the API through `API_URL` (compose sets `http://api:8000`). There is no `NEXT_PUBLIC_API_URL`.
- Check `docker compose logs ui` for proxy errors and `docker compose logs api` for the matching request ID.

## 8. Capacity planning

All figures are **estimates** from development hardware, not load-tested guarantees. Measure in your environment with `rm_analysis_duration_seconds_*`.

| Item | Estimate |
|------|----------|
| Analysis time, ~1,000 events | 2–5 s CPU |
| Analysis time, 5,000 events (single-project cap) | 10–30 s |
| API memory | ~250 MB idle, ~500–800 MB peak during fitting/rendering (compose limit `API_MEMORY`, default 1 GB) |
| UI memory | ~100–200 MB (compose limit `UI_MEMORY`, default 512 MB) |
| Concurrency | ~1 concurrent analysis per vCPU (compose limit `API_CPUS`, default 1 vCPU; raise on larger hosts, never above the host's CPU count) |
| Disk per analysis | ~0.1–1 MB (archive + persisted analysis + plot) |
| Disk at 90-day retention, 20 analyses/day | roughly 0.2–2 GB |

Sentry pull time is usually the dominant factor for "all projects" runs.

## 9. Environment variables

The authoritative list with defaults is in [`README.md`](README.md#configuration) and [`.env.example`](.env.example).

## 10. Escalation

| Issue | First response | Escalate to |
|-------|----------------|-------------|
| Sentry ingest errors | Token/scopes, API logs | trustaldo@gmail.com |
| Container unhealthy / won't start | `docker compose ps`, logs, runbook table | Marwa Trust Mutemasango |
| Model produces NaN/Inf | Data volume, model inputs | trustaldo@gmail.com |
| Security incident | Stop the stack, rotate API key / UI password / Sentry token | trustaldo@gmail.com |
