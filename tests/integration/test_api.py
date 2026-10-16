"""
Integration tests for a running Reliability Modeler API.

Run with: python -m pytest tests/integration/ -v

Environment:
    RELIABILITY_API_URL            base URL (default http://localhost:8000)
    RELIABILITY_API_KEY            sent as X-API-Key (required by the API since 2.9.0)
    RM_INTEGRATION_ALLOW_WRITE     set to "true" to run tests that modify live
                                   config (they restore the original afterwards)

All tests are skipped when the API is unreachable.
"""

import os
import time

import pytest
import requests

API_URL = os.getenv("RELIABILITY_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("RELIABILITY_API_KEY", "")
ALLOW_WRITE = os.getenv("RM_INTEGRATION_ALLOW_WRITE", "").lower() in {"1", "true", "yes"}
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

pytestmark = pytest.mark.integration


def _api_available():
    try:
        return requests.get(f"{API_URL}/health/live", timeout=2).status_code == 200
    except requests.RequestException:
        return False


requires_api = pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
requires_key = pytest.mark.skipif(not API_KEY, reason="RELIABILITY_API_KEY not set")


def get(path, **kw):
    return requests.get(f"{API_URL}{path}", headers=HEADERS, timeout=10, **kw)


def post(path, **kw):
    return requests.post(f"{API_URL}{path}", headers=HEADERS, timeout=10, **kw)


@requires_api
class TestHealthEndpoint:
    def test_liveness(self):
        assert requests.get(f"{API_URL}/health/live", timeout=5).json() == {"status": "ok"}

    def test_health_shape(self):
        r = requests.get(f"{API_URL}/health", timeout=5)
        assert r.status_code in (200, 503)
        data = r.json()
        assert data["status"] in ("ok", "degraded", "error")
        assert {"version", "timestamp", "checks"} <= set(data)
        assert set(data["checks"]) == {"output_writable", "config_readable", "sentry_token_configured"}

    def test_health_response_time(self):
        start = time.time()
        requests.get(f"{API_URL}/health", timeout=5)
        assert time.time() - start < 1.0

    def test_request_id_echoed(self):
        r = requests.get(f"{API_URL}/health/live", headers={"X-Request-ID": "itest-1"}, timeout=5)
        assert r.headers.get("X-Request-ID") == "itest-1"


@requires_api
class TestAuth:
    def test_protected_without_key(self):
        for path in ("/config", "/logs", "/docs", "/openapi.json", "/metrics"):
            r = requests.get(f"{API_URL}{path}", timeout=5)
            assert r.status_code == 401, path
            assert r.json() == {"detail": "Invalid or missing API key"}


@requires_api
@requires_key
class TestSentryEndpoint:
    def test_ingest_sentry_requires_org(self):
        r = post("/ingest/sentry", json={"project": "foo"})
        assert r.status_code == 422
        assert isinstance(r.json()["detail"], str)

    def test_ingest_sentry_requires_project(self):
        assert post("/ingest/sentry", json={"org": "foo"}).status_code == 422

    def test_ingest_sentry_days_bounds(self):
        assert post("/ingest/sentry", json={"org": "foo", "project": "bar", "days": 91}).status_code == 422

    def test_list_projects_requires_org(self):
        assert get("/ingest/sentry/projects").status_code == 422


@requires_api
@requires_key
class TestConfigEndpoint:
    def test_get_config(self):
        r = get("/config")
        assert r.status_code == 200
        data = r.json()
        assert "content" in data and "settings" in data

    def test_post_invalid_taxonomy_rejected(self):
        # Rejected by validation, so live config is never touched.
        r = post("/config", json={"content": "not valid"})
        assert r.status_code == 422

    @pytest.mark.skipif(not ALLOW_WRITE, reason="set RM_INTEGRATION_ALLOW_WRITE=true to modify live config")
    def test_post_valid_config_and_restore(self):
        original = get("/config").json()
        new_content = "Database [db, sql]\nNetwork [http, timeout]\n"
        try:
            r = post("/config", json={"content": new_content})
            assert r.status_code == 200, r.text
            assert get("/config").json()["content"] == new_content
        finally:
            restore = post("/config", json={"content": original["content"]})
            assert restore.status_code == 200, f"FAILED TO RESTORE CONFIG: {restore.text}"


@requires_api
@requires_key
class TestLogsEndpoint:
    def test_logs_returns_paginated_response(self):
        r = get("/logs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["total"], int) and isinstance(data["logs"], list)

    def test_logs_pagination_respects_limit(self):
        assert len(get("/logs", params={"limit": 3, "offset": 0}).json()["logs"]) <= 3


@requires_api
@requires_key
class TestTrendsEndpoint:
    def test_trends_returns_valid_response(self):
        data = get("/trends").json()
        assert isinstance(data["runs"], list) and isinstance(data["groups"], list) and "trend" in data


@requires_api
@requires_key
class TestMetrics:
    def test_metrics_text(self):
        r = get("/metrics")
        assert r.status_code == 200
        assert "rm_http_requests_total" in r.text
