# Reliability Modeler — Operations & Support Runbook

## 1. Service Overview

The Reliability Modeler is a two-tier containerized application:

```
┌──────────────┐     HTTP :8000     ┌──────────────┐
│   Next.js UI │ ─────────────────▶ │  FastAPI API │
│   Port 3000  │                    │   Port 8000  │
└──────────────┘                    └──────┬───────┘
                                          │
                                          ▼
                                    ┌──────────┐
                                    │ modeler/ │  Python NHPP engine
                                    │ output/  │  Logs & archives
                                    └──────────┘
```

- **API**: Python 3.11+ FastAPI server. CPU-bound (scipy optimization, matplotlib rendering).
- **UI**: Next.js 16 static + client-rendered SPA. Talks to API exclusively.
- **No database**: State is file-based (JSON log archives, settings.json, fault_categories.conf).

## 2. Common Failure Modes & Remedies

### 2.1 "500 Internal Server Error" from /analyze

**Likely causes:**
1. **CSV format mismatch**: Timestamp column is unparseable or missing.
   - *Fix*: Verify CSV has at least a timestamp column. Check that dates are in ISO format or relative hours.
   - *Log grep*: Look for `"Skipped N rows"` in API logs.

2. **Model convergence failure**: Data is too sparse (< 3 failure events) or all timestamps are identical.
   - *Fix*: Try `Nelder-Mead` optimizer in Config → Advanced Engine Settings. Ensure at least 3 distinct timestamps.

3. **Memory exhaustion on large CSV**: >100MB file or >50,000 rows.
   - *Fix*: The API enforces a 10MB upload limit. If legitimate data exceeds this, increase `MAX_UPLOAD_BYTES` in `web/api/main.py`.

### 2.2 "429 Too Many Requests"

Rate limiting is active: 30 requests per 60 seconds per client IP. Adjust via env vars:
- `RATE_LIMIT_MAX`: max requests per window (default 30)
- `RATE_LIMIT_WINDOW`: window size in seconds (default 60)

### 2.3 Config changes not persisting after container restart

`fault_categories.conf` and `settings.json` are written to the container filesystem. If the container is rebuilt, changes are lost. Use a Docker volume mount:

```yaml
volumes:
  - ./fault_categories.conf:/app/fault_categories.conf
  - ./settings.json:/app/web/api/settings.json
```

### 2.4 UI shows "Failed to analyze the file"

- Check that `NEXT_PUBLIC_API_URL` is set correctly in the UI container.
- Verify the API container is reachable from the UI container on port 8000.
- Check browser console for CORS errors. Ensure `ALLOWED_ORIGINS` includes the UI origin.

### 2.5 AIC values differ between CLI and Web UI

Both now use the same formula: `AIC = 2k - 2·ln(L)`. If you still see discrepancies, verify the same settings (optimizer, tolerance) are used.

## 3. Logging & Monitoring

### API Logs
- Format: JSON-structured to stdout
- Fields: `time`, `level`, `logger`, `message`
- Each request gets an `X-Request-ID` header for correlation.
- Log level: `INFO` by default. Set `LOG_LEVEL=DEBUG` for verbose output.

```bash
# View API logs
docker logs reliability-modeler-api-1

# Stream with filtering
docker logs -f reliability-modeler-api-1 2>&1 | grep '"level": "ERROR"'
```

### Health Checks
- **Endpoint**: `GET /health` → `{"status": "ok", "version": "2.0.1", "timestamp": "..."}`
- Use this for load balancer health probes. Expected: HTTP 200, response within 100ms.

### CLI Logs
- Written to `output/YYYY/MM/DD/run_HHMMSS.log` (structured text format).
- Console output if `--silent` is not set.

## 4. Deployment & Rollback

### Deploy
```bash
# Build and push images
make build push IMAGE_TAG=v2.0.1

# On target host
docker-compose pull
docker-compose up -d
```

### Rollback
```bash
# Revert to previous tag
IMAGE_TAG=v2.0.0 docker-compose up -d
```

### Verify deployment
```bash
curl http://localhost:8000/health
curl http://localhost:3000  # Should return HTML
```

## 5. Environment Variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `ALLOWED_ORIGINS` | API | `http://localhost:3000` | Comma-separated CORS origins |
| `RATE_LIMIT_MAX` | API | `30` | Max requests per window |
| `RATE_LIMIT_WINDOW` | API | `60` | Rate limit window (seconds) |
| `NEXT_PUBLIC_API_URL` | UI | `http://localhost:8000` | API base URL |
| `DOCKERHUB_USERNAME` | Build | (required) | Docker Hub username for push |
| `IMAGE_TAG` | Build | git hash | Docker image tag |

## 6. Escalation

| Issue Type | First Response | Escalate To |
|------------|---------------|-------------|
| API 500 errors | Check CSV format, logs | Development team |
| Container won't start | Check Docker logs, port conflicts | Infrastructure team |
| Model produces NaN/Inf | Check data quality, try different optimizer | Data science team |
| Security incident | Take API offline, rotate credentials | Security team |
| UI rendering issues | Check browser console, API connectivity | Frontend team |

## 7. Backup & Recovery

- **Log archives**: Stored in `output/logs/`. Back up this directory.
- **Configuration**: Back up `fault_categories.conf` and `web/api/settings.json`.
- **Recovery**: Restore files to the same paths and restart containers.

## 8. Capacity Planning

- The API is CPU-bound (one worker per request, scipy MLE fits).
- Estimated: 2-5 seconds per analysis on a 1000-row CSV.
- Recommend 1 vCPU per 5 concurrent analysis requests.
- Memory: ~256MB baseline, peaks at ~512MB during matplotlib rendering.
