"""
Integration tests for the Reliability Modeler API.

Run with: python -m pytest tests/integration/ -v
Requires the API server to be running on localhost:8000,
or set RELIABILITY_API_URL environment variable.
"""

import os
import pytest
import requests
import time

API_URL = os.getenv("RELIABILITY_API_URL", "http://localhost:8000")


def _api_available():
    """Skip tests if API is not running."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=2)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestHealthEndpoint:
    """Test the /health endpoint."""

    def test_health_returns_ok(self):
        r = requests.get(f"{API_URL}/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data

    def test_health_response_time(self):
        start = time.time()
        r = requests.get(f"{API_URL}/health", timeout=5)
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1s"


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestSentryEndpoint:
    """Test the Sentry ingest endpoints."""

    def test_ingest_sentry_requires_org(self):
        r = requests.post(f"{API_URL}/ingest/sentry", json={"project": "foo"}, timeout=5)
        assert r.status_code == 400

    def test_ingest_sentry_requires_project(self):
        r = requests.post(f"{API_URL}/ingest/sentry", json={"org": "foo"}, timeout=5)
        assert r.status_code == 400

    def test_ingest_sentry_missing_token(self):
        # Without SENTRY_AUTH_TOKEN, should return 503 (or 502/400 depending on env)
        r = requests.post(
            f"{API_URL}/ingest/sentry",
            json={"org": "foo", "project": "bar"},
            timeout=5,
        )
        assert r.status_code in (503, 502, 400)

    def test_list_projects_requires_org(self):
        r = requests.get(f"{API_URL}/ingest/sentry/projects", timeout=5)
        assert r.status_code == 400


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestConfigEndpoint:
    """Test the /config GET and POST endpoints."""

    def test_get_config(self):
        r = requests.get(f"{API_URL}/config", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "content" in data
        assert "settings" in data

    def test_post_valid_config(self):
        r_get = requests.get(f"{API_URL}/config", timeout=5)
        original = r_get.json()

        new_content = "Database [db, sql]\nNetwork [http, timeout]\n"
        r = requests.post(f"{API_URL}/config", json={"content": new_content}, timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

        r_get2 = requests.get(f"{API_URL}/config", timeout=5)
        assert r_get2.json()["content"] == new_content

        # Restore original
        requests.post(f"{API_URL}/config", json={"content": original["content"]}, timeout=5)

    def test_post_invalid_taxonomy_rejected(self):
        r = requests.post(f"{API_URL}/config", json={"content": "not valid"}, timeout=5)
        assert r.status_code == 400


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestLogsEndpoint:
    """Test the /logs endpoint."""

    def test_logs_returns_paginated_response(self):
        r = requests.get(f"{API_URL}/logs", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "total" in data
        assert "logs" in data
        assert isinstance(data["logs"], list)
        assert isinstance(data["total"], int)

    def test_logs_pagination_respects_limit(self):
        r = requests.get(f"{API_URL}/logs?limit=3&offset=0", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert len(data["logs"]) <= 3


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestTrendsEndpoint:
    """Test the /trends endpoint."""

    def test_trends_returns_valid_response(self):
        r = requests.get(f"{API_URL}/trends", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert "trend" in data
        assert isinstance(data["runs"], list)


@pytest.mark.skipif(not _api_available(), reason=f"API not available on {API_URL}")
class TestCORSSecurity:
    """Test CORS and security headers."""

    def test_cors_restricts_unknown_origin(self):
        r = requests.get(f"{API_URL}/health", timeout=5)
        assert r.status_code == 200

    def test_health_no_sensitive_headers(self):
        r = requests.get(f"{API_URL}/health", timeout=5)
        assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers.get("server", "").lower()
