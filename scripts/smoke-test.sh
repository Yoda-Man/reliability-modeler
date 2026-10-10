#!/usr/bin/env bash
# Smoke-test the full stack in an isolated, throwaway compose project.
#
# Does NOT touch a running deployment: it uses its own project name, its own
# volumes, a generated env file and an alternate host port, and removes
# everything (including volumes) on exit.
#
# Usage:
#   IMAGE_TAG=2.9.0 ./scripts/smoke-test.sh
#
# Environment:
#   IMAGE_TAG            image tag to test            (default: latest)
#   DOCKERHUB_NAMESPACE  image namespace              (default: trustaldo)
#   SMOKE_PORT           host port for the UI         (default: 13000)
#   SMOKE_TIMEOUT        seconds to wait for healthy  (default: 180)
#   KEEP_STACK=1         leave the stack running for debugging

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
PROJECT="rm-smoke-$$"
SMOKE_PORT="${SMOKE_PORT:-13000}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-180}"
BASE="http://127.0.0.1:${SMOKE_PORT}"

ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/rm-smoke-env.XXXXXX")"
chmod 600 "${ENV_FILE}"

rand_hex() { od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; }
API_KEY="$(rand_hex 32)"
UI_USER="smoke"
UI_PASS="$(rand_hex 16)"

cat >"${ENV_FILE}" <<EOF
RELIABILITY_API_KEY=${API_KEY}
UI_USERNAME=${UI_USER}
UI_PASSWORD=${UI_PASS}
UI_PORT=${SMOKE_PORT}
IMAGE_TAG=${IMAGE_TAG:-latest}
DOCKERHUB_NAMESPACE=${DOCKERHUB_NAMESPACE:-trustaldo}
SENTRY_AUTH_TOKEN=
EOF

dc() { docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"; }

FAILED=0
cleanup() {
  local rc=$?
  if [ "${rc}" -ne 0 ] || [ "${FAILED}" -ne 0 ]; then
    echo "---- container status ----"; dc ps -a || true
    echo "---- last logs ----"; dc logs --no-color --tail=100 || true
  fi
  if [ "${KEEP_STACK:-0}" = "1" ]; then
    echo "KEEP_STACK=1: leaving project ${PROJECT} running (env file ${ENV_FILE})."
  else
    dc down -v --remove-orphans >/dev/null 2>&1 || true
    rm -f "${ENV_FILE}"
  fi
  exit "${rc}"
}
trap cleanup EXIT INT TERM

pass() { echo "  PASS  $*"; }
fail() { echo "  FAIL  $*" >&2; FAILED=1; }

# http_code <curl args...> -> prints status code
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@" || echo "000"; }

echo "==> Starting ${PROJECT} (images ${DOCKERHUB_NAMESPACE:-trustaldo}/reliability-modeler-*:${IMAGE_TAG:-latest}, UI port ${SMOKE_PORT})"
dc up -d --wait --wait-timeout "${SMOKE_TIMEOUT}"

echo "==> Checks"

# 1. API /health from inside the api container (port 8000 is not published).
API_HEALTH="$(dc exec -T api python -c "
import json, urllib.request, urllib.error
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5); code, body = r.status, r.read()
except urllib.error.HTTPError as e:
    code, body = e.code, e.read()
print(code, json.loads(body).get('status', ''), json.loads(body).get('version', ''))
" 2>&1 || true)"
case "${API_HEALTH}" in
  "200 ok "*|"200 degraded "*) pass "API /health -> ${API_HEALTH}" ;;
  *) fail "API /health -> ${API_HEALTH}" ;;
esac

# 2. API rejects unauthenticated access to protected routes.
API_NOAUTH="$(dc exec -T api python -c "
import urllib.request, urllib.error
try:
    print(urllib.request.urlopen('http://127.0.0.1:8000/config', timeout=5).status)
except urllib.error.HTTPError as e:
    print(e.code)
" 2>&1 || true)"
[ "${API_NOAUTH}" = "401" ] && pass "API /config without key -> 401" || fail "API /config without key -> ${API_NOAUTH} (want 401)"

# 3. API port is not published on the host.
API_PUBLISHED="$(dc port api 8000 2>/dev/null || true)"
if [[ "${API_PUBLISHED}" =~ :[1-9][0-9]*$ ]]; then fail "API port 8000 is published to the host (${API_PUBLISHED})"; else pass "API port 8000 not published"; fi

# 4. UI liveness (no auth).
code="$(http_code "${BASE}/healthz")"
[ "${code}" = "200" ] && pass "UI /healthz -> 200" || fail "UI /healthz -> ${code}"

# 5. UI requires login.
code="$(http_code "${BASE}/")"
[ "${code}" = "401" ] && pass "UI / without credentials -> 401" || fail "UI / without credentials -> ${code} (want 401)"

code="$(http_code -u "${UI_USER}:wrong-password" "${BASE}/")"
[ "${code}" = "401" ] && pass "UI / with wrong password -> 401" || fail "UI / with wrong password -> ${code} (want 401)"

code="$(http_code -u "${UI_USER}:${UI_PASS}" "${BASE}/")"
[ "${code}" = "200" ] && pass "UI / with credentials -> 200" || fail "UI / with credentials -> ${code}"

# 6. Proxy -> API with auth (key injected server-side), request id echoed.
HDRS="$(mktemp)"; BODY="$(mktemp)"
code="$(curl -s -D "${HDRS}" -o "${BODY}" -w '%{http_code}' --max-time 15 \
  -u "${UI_USER}:${UI_PASS}" -H 'X-Request-ID: smoke-test-1' "${BASE}/api/health" || echo 000)"
if [ "${code}" = "200" ] && grep -q '"version"' "${BODY}"; then
  pass "UI proxy /api/health -> 200 $(tr -d '\n' <"${BODY}" | head -c 160)"
else
  fail "UI proxy /api/health -> ${code} $(head -c 200 "${BODY}")"
fi
grep -qi '^x-request-id: smoke-test-1' "${HDRS}" && pass "X-Request-ID propagated" || fail "X-Request-ID not echoed by proxy"

code="$(http_code -u "${UI_USER}:${UI_PASS}" "${BASE}/api/config")"
[ "${code}" = "200" ] && pass "UI proxy /api/config (authed route) -> 200" || fail "UI proxy /api/config -> ${code}"
rm -f "${HDRS}" "${BODY}"

echo
if [ "${FAILED}" -ne 0 ]; then
  echo "SMOKE TEST FAILED"
  exit 1
fi
echo "SMOKE TEST PASSED"
