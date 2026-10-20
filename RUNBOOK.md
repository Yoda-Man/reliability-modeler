# Reliability Modeler: Runbook

Procedures for operating the Docker Compose deployment. Background (architecture, metrics, log format, capacity) is in [`SUPPORT.md`](SUPPORT.md).

All commands run from the repository (or deployment) directory containing `docker-compose.yml` and `.env`.

| | |
|---|---|
| Service owner | Marwa Trust Mutemasango |
| Team channel | trustaldo@gmail.com |
| Escalation | trustaldo@gmail.com |

---

## 1. First deploy

```bash
cp .env.example .env && chmod 600 .env
openssl rand -hex 32          # paste as RELIABILITY_API_KEY
openssl rand -base64 24       # paste as UI_PASSWORD (or choose one)
# optionally set SENTRY_AUTH_TOKEN (or connect a token later on the Sentry page) and pin IMAGE_TAG=2.15.0
docker compose pull
docker compose up -d
docker compose ps             # wait for api and ui to be "healthy" (about 30 s)
```

Verify:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/healthz            # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/                   # 401 (login required)
curl -s -u admin:"<UI_PASSWORD>" http://localhost:3000/api/health                 # {"status":"ok",...,"version":"2.15.0"}
```

`degraded` means no Sentry token is connected yet: paste one on the Sentry page, or set `SENTRY_AUTH_TOKEN`. Then open http://localhost:3000, log in, and run a Sentry analysis.

## 2. Upgrade

```bash
./scripts/backup.sh                              # always back up first
# edit .env: IMAGE_TAG=<new version>
docker compose pull
docker compose up -d                             # recreates changed services; volumes are kept
docker compose ps && docker compose logs --tail=50 api
```

Read the release's CHANGELOG entry first for breaking changes.

### Upgrading from 2.8.x to 2.9.0 (one-off)

2.9.0 is a breaking release:

1. **New required variables.** Add `RELIABILITY_API_KEY` (if it was empty) and `UI_PASSWORD` to `.env`. Compose will not start without them.
2. **Use the 2.9.0 `docker-compose.yml`.** Port 8000 is no longer published; a new `config_data` volume is added. `output_data` is reused unchanged.
3. **Carry over a customised taxonomy.** Before 2.9.0 the taxonomy and settings lived inside the container (not on a volume). Before upgrading, export them from the running 2.8.x container:
   ```bash
   docker compose exec -T api cat /app/fault_categories.conf > fault_categories.migrate.conf
   docker compose exec -T api cat /app/settings.json > settings.migrate.json 2>/dev/null || true
   ```
   After the 2.9.0 stack is up, write them into the config volume as the app user and restart:
   ```bash
   docker compose exec -T api sh -c 'cat > /app/config/fault_categories.conf' < fault_categories.migrate.conf
   [ -s settings.migrate.json ] && docker compose exec -T api sh -c 'cat > /app/config/settings.json' < settings.migrate.json
   docker compose restart api
   ```
4. **Scripts or bookmarks that called `http://host:8000` directly** must now go through the UI proxy (`http://host:3000/api/...` with the UI login) or run inside the compose network with `X-API-Key`.

## 3. Rollback

Within releases that share the same compose layout (2.9.0 and later):

```bash
IMAGE_TAG=2.9.0 docker compose up -d      # or set IMAGE_TAG in .env to the previous version
docker compose ps
```

Data volumes are untouched by a rollback. If the newer version changed the taxonomy format or settings, restore the config volume from the pre-upgrade backup (section 5).

**Rolling back from 2.9.0 to 2.8.1** does *not* work with the 2.9.0 compose file: 2.8.1 images lack `/health/live` and `/healthz` (health checks fail, the UI never starts) and ignore `CONFIG_DIR`. To go back:

```bash
docker compose down                                         # volumes are kept
git show 67a2dbd:docker-compose.yml > docker-compose.2.8.yml   # last pre-2.9.0 compose file
IMAGE_TAG=2.8.1 docker compose -f docker-compose.2.8.yml up -d
```

(Edit the image lines in that file to use `:2.8.1` if they are hard-coded to `:latest`.) Notes: 2.8.1 publishes port 8000 and does not read `config_data`, so taxonomy edits made under 2.9.0 are not visible; analyses created under 2.9.0 use the new ID format, which 2.8.1's GraphQL rejects.

## 4. Secret rotation

| Secret | Steps | Impact |
|--------|-------|--------|
| `RELIABILITY_API_KEY` | 1. `openssl rand -hex 32` 2. update `.env` 3. `docker compose up -d --force-recreate api ui` (both services must get the new value together) 4. update any external caller (e.g. metrics scraper) | Requests in flight during the ~30 s recreate fail; UI shows API errors until both are up |
| `UI_PASSWORD` / `UI_USERNAME` | 1. update `.env` 2. `docker compose up -d --force-recreate ui` 3. tell users | Users are prompted to log in again |
| Sentry token (connected in the UI) | Sentry page → paste the new token → **Replace** (it is checked before saving). Then revoke the old token in Sentry |
| `SENTRY_AUTH_TOKEN` | 1. create the new token in Sentry (`event:read`, `project:read`, `org:read`) 2. update `.env` 3. `docker compose up -d --force-recreate api` 4. check `/api/health` shows `sentry_token_configured: true` 5. revoke the old token in Sentry | Ingest unavailable during recreate |
| Docker Hub token (CI) | Create a new access token, update the `DOCKERHUB_TOKEN` repository secret, revoke the old one | None |

After a suspected leak: rotate all three, review `docker compose logs api` for unexpected `401`/`429` patterns and unknown source IPs.

## 5. Backup and restore

What is backed up: the `output_data` (archives, analyses, plots) and `config_data` (taxonomy, settings) volumes. `.env` is **not** included; store it in your secret manager.

```bash
./scripts/backup.sh                    # -> ./backups/reliability-modeler-<project>-<UTC stamp>.tar.gz
make backup BACKUP_DIR=/srv/backups    # same, custom directory
```

Backups are safe while running (atomic writes); stop the API first (`docker compose stop api`) for a fully quiescent copy. Archives are created `0600` and owned by the user running the script. Suggested schedule: daily via cron, keep 14 days, copy off-host.

Restore (replaces current volume contents):

```bash
docker compose stop
./scripts/restore.sh backups/reliability-modeler-<project>-<stamp>.tar.gz     # asks for confirmation; -y to skip
docker compose up -d
```

Before asking for confirmation, `restore.sh` checks the whole archive (gzip integrity, full tar listing, both `output/` and `config/` present) and aborts without touching the volumes if it is truncated or incomplete. It then extracts into a staging directory and only replaces the volume contents once extraction succeeded.

If you run the stack under a non-default compose project name, set `COMPOSE_PROJECT_NAME` for both scripts. Test a restore at least once per quarter (restore into a throwaway project: `COMPOSE_PROJECT_NAME=rm-restore-test ./scripts/restore.sh <archive> -y`).

## 6. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `docker compose up` errors "required variable RELIABILITY_API_KEY/UI_PASSWORD is missing" | `.env` incomplete | Set the variable in `.env` (see section 1) |
| Browser keeps asking for a password / 401 on every page | Wrong UI credentials | Check `UI_USERNAME`/`UI_PASSWORD` in `.env`; recreate `ui` after changing them |
| UI loads but every API call fails with 401 "Invalid or missing API key" | UI and API have different `RELIABILITY_API_KEY` (one service not recreated after rotation) | `docker compose up -d --force-recreate api ui` |
| Every UI request returns 503 "UI_PASSWORD not configured" | `UI_PASSWORD` empty in the UI container | Set it in `.env`, recreate `ui` |
| API container exits immediately, log says API key required | `RELIABILITY_API_KEY` empty | Set it; never use `ALLOW_INSECURE_NO_AUTH` outside local dev |
| `/health` 200 `degraded`, `sentry_token_configured: false` | No Sentry token | Connect one on the Sentry page, or set `SENTRY_AUTH_TOKEN` and recreate `api` |
| Sentry 403 "denied access" | Organization token (`sntrys_`) or missing scopes | Use a personal or integration token with `event:read`, `project:read`, `org:read` |
| `/health` 503 `error`, `config_readable: false` | `config_data` volume missing/corrupt or wrong ownership | `docker compose exec api ls -l /app/config`; files must be readable by uid 10001. Restore config from backup, or remove the bad file to re-seed defaults |
| `/health` 503 `error`, `output_writable: false` | Output volume full or not owned by uid 10001 | Check disk space (`docker system df -v`); fix ownership: `docker run --rm -v <project>_output_data:/d busybox:1.37 chown -R 10001:10001 /d` |
| 413 "Request body too large" | Body above `MAX_BODY_BYTES` (API) or 1 MiB (proxy), usually a huge taxonomy | Shrink the payload; raise `MAX_BODY_BYTES` only if justified (the proxy limit is fixed at 1 MiB) |
| 429 "Too many requests" | More than `RATE_LIMIT_PER_MINUTE` per client IP (the proxy forwards the client's socket address) | Wait a minute; raise `RATE_LIMIT_PER_MINUTE` if legitimate. Behind a reverse proxy every user shares its IP: set `TRUST_PROXY=true` so its `X-Forwarded-For` is used. If it is Sentry's 429, see SUPPORT.md section 7 |
| Analysis fails with timeout (504 / "Analysis timed out") | Analysis exceeded `ANALYSIS_TIMEOUT_SECONDS` (large org, "all projects") | Narrow the window or project; raise `ANALYSIS_TIMEOUT_SECONDS` and keep `PROXY_TIMEOUT_MS` above it (in ms) |
| UI shows a proxy timeout / 504 while API logs success | `PROXY_TIMEOUT_MS` below analysis time | Raise `PROXY_TIMEOUT_MS` |
| Container `unhealthy` / UI stuck in "created" | API health check failing, so `ui` waits (depends_on healthy) | `docker compose ps`; `docker inspect --format '{{json .State.Health}}' <container>`; `docker compose logs api`. Common: OOM kill (raise `API_MEMORY`/`UI_MEMORY`), bad env value, volume permissions. "range of CPUs is from ...": `API_CPUS`/`UI_CPUS` exceed the host's CPUs |
| Container restarting repeatedly | Crash on startup or OOM | `docker compose logs --tail=200 <svc>`; `docker inspect -f '{{.State.OOMKilled}} {{.RestartCount}}' <container>` |
| Taxonomy edits lost after redeploy | `config_data` volume removed (`down -v`) or k8s PVC not mounted at `/app/config` | Restore from backup; never use `down -v` in production |

## 7. Logs and request correlation

```bash
docker compose logs -f api ui                      # live
docker compose logs --since 1h api | grep '"level": "ERROR"'
docker compose logs api ui | grep '<X-Request-ID>' # one request end-to-end
```

Container log files live under Docker's data directory (json-file driver, 10 MB x 5 per container; `docker inspect -f '{{.LogPath}}' <container>`).

To correlate a user report: ask for the `X-Request-ID` response header (browser dev tools, Network tab) or the time of the failure. The same ID appears in the UI proxy's error log and in the API's JSON `request_id` field.

## 8. Escalation

1. Check this runbook's failure table and `SUPPORT.md`.
2. Email trustaldo@gmail.com with: symptom, time (UTC), request ID, `docker compose ps`, last 100 lines of `docker compose logs api ui`.
3. If unresolved within 1 hour, or for any security incident: contact trustaldo@gmail.com. Owner: Marwa Trust Mutemasango.

## 9. Release procedure

1. Bump `__version__` in `modeler/__init__.py` and `"version"` in `web/ui/package.json`.
2. Add a dated entry at the top of `CHANGELOG.md` (newest first, mark breaking changes).
3. Make sure CI is green on `main` (tests, audits, Docker smoke test). Optionally locally: `make test build smoke`.
4. Commit, then tag: `git tag v<version> && git push origin v<version>`.
5. Publish images (multi-arch `linux/amd64` + `linux/arm64`, tags `:<version>` and `:latest`), either:
   - **CI**: the tag push triggers `.github/workflows/release.yml` (requires repository secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`; it fails if the tag does not match `__version__`, and runs the full test suite before pushing), or run it manually from the Actions tab (only from `main` or a `v*` tag; other branches are refused); or
   - **Locally**: `docker login && make push` (asks for confirmation; other namespace: `make push DOCKERHUB_USERNAME=<you>`).
6. Verify: `docker buildx imagetools inspect trustaldo/reliability-modeler-api:<version>` lists both platforms.
7. Deploy with the upgrade procedure (section 2).
