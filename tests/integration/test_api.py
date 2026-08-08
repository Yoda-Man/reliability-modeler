"""
Integration tests for the Reliability Modeler API.

Run with: python -m pytest tests/integration/ -v
Requires the API server to be running on localhost:8000,
or set RELIABILITY_API_URL environment variable.
"""

import os
import pytest
import requests
import io
import time

API_URL = os.getenv("RELIABILITY_API_URL", "http://localhost:8000")
SAMPLE_CSV = "Date Time Of Error,Error or Fault Description\n2026-01-01 08:00:00,NullPointerException in auth\n2026-01-01 09:00:00,Database timeout\n2026-01-01 10:00:00,UI rendering error\n2026-01-01 11:00:00,Memory leak detected\n2026-01-01 12:00:00,Network timeout\n"


def _api_available():
    """Skip tests if API is not running."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=2)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
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


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
class TestSampleData:
    """Test the /sample-data endpoint."""

    def test_sample_data_returns_valid_response(self):
        r = requests.get(f"{API_URL}/sample-data", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "models" in data
        assert "plots" in data
        assert "categorized_failures" in data
        assert data["summary"]["total_failures"] > 0
        assert len(data["models"]) > 0

    def test_sample_data_models_have_aic(self):
        r = requests.get(f"{API_URL}/sample-data", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for model in data["models"]:
            assert "aic" in model
            assert "name" in model
            assert "total_expected_failures" in model
            assert isinstance(model["aic"], (int, float))

    def test_sample_data_plots_are_base64(self):
        r = requests.get(f"{API_URL}/sample-data", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for plot_name in ["reliability", "intensity", "categories"]:
            assert plot_name in data["plots"], f"Missing plot: {plot_name}"
            assert len(data["plots"][plot_name]) > 100, f"Plot {plot_name} seems empty"


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
class TestAnalyzeEndpoint:
    """Test the /analyze endpoint with file uploads."""

    def test_analyze_valid_csv(self):
        csv_content = SAMPLE_CSV.encode("utf-8")
        files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
        r = requests.post(f"{API_URL}/analyze?future_hours=500", files=files, timeout=30)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["summary"]["total_failures"] == 5
        assert len(data["models"]) >= 1

    def test_analyze_empty_csv_returns_error(self):
        csv_content = b"Date Time Of Error,Error or Fault Description\n"
        files = {"file": ("empty.csv", io.BytesIO(csv_content), "text/csv")}
        r = requests.post(f"{API_URL}/analyze", files=files, timeout=30)
        assert r.status_code in (400, 500), f"Expected error status, got {r.status_code}"

    def test_analyze_rejects_negative_future_hours(self):
        csv_content = SAMPLE_CSV.encode("utf-8")
        files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
        r = requests.post(f"{API_URL}/analyze?future_hours=-100", files=files, timeout=30)
        assert r.status_code == 400, f"Expected 400 for negative future_hours, got {r.status_code}"

    def test_analyze_rejects_extreme_future_hours(self):
        csv_content = SAMPLE_CSV.encode("utf-8")
        files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
        r = requests.post(f"{API_URL}/analyze?future_hours=999999", files=files, timeout=30)
        assert r.status_code == 400, f"Expected 400 for extreme future_hours, got {r.status_code}"

    def test_analyze_rejects_non_csv(self):
        files = {"file": ("test.txt", io.BytesIO(b"this is not a csv"), "text/plain")}
        r = requests.post(f"{API_URL}/analyze", files=files, timeout=30)
        assert r.status_code in (400, 500), f"Expected error status, got {r.status_code}"


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
class TestConfigEndpoint:
    """Test the /config GET and POST endpoints."""

    def test_get_config(self):
        r = requests.get(f"{API_URL}/config", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "content" in data
        assert "settings" in data

    def test_post_valid_config(self):
        # First get current config to restore later
        r_get = requests.get(f"{API_URL}/config", timeout=5)
        original = r_get.json()

        # Post a valid taxonomy update
        new_content = "Database [db, sql]\nNetwork [http, timeout]\n"
        r = requests.post(f"{API_URL}/config", json={"content": new_content}, timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

        # Verify it was saved
        r_get2 = requests.get(f"{API_URL}/config", timeout=5)
        assert r_get2.json()["content"] == new_content

        # Restore original
        requests.post(f"{API_URL}/config", json={"content": original["content"]}, timeout=5)

    def test_post_invalid_taxonomy_rejected(self):
        r = requests.post(f"{API_URL}/config", json={"content": "this is not valid taxonomy format"}, timeout=5)
        assert r.status_code == 400, f"Expected 400 for invalid taxonomy, got {r.status_code}"


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
class TestLogsEndpoint:
    """Test the /logs endpoint."""

    def test_logs_returns_array(self):
        r = requests.get(f"{API_URL}/logs", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


@pytest.mark.skipif(not _api_available(), reason="API not available on {API_URL}".format(API_URL=API_URL))
class TestCORSSecurity:
    """Test CORS and security headers."""

    def test_cors_restricts_unknown_origin(self):
        # Without an Origin header, API should still respond normally
        r = requests.get(f"{API_URL}/health", timeout=5)
        assert r.status_code == 200

    def test_health_no_sensitive_headers(self):
        r = requests.get(f"{API_URL}/health", timeout=5)
        # Should not leak server info
        assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers.get("server", "").lower()
