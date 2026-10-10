"""
API tests using FastAPI's TestClient — no network, no live server.

Sentry access is mocked by monkeypatching the loader functions the API
imports; CONFIG_DIR / OUTPUT_DIR point at per-test tmp dirs (see conftest).
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import API_KEY, REPO_ROOT

NEW_ID_RE = re.compile(r"^AN-\d{8}-\d{6}-[0-9a-f]{6}$")


def _synthetic_sentry(n=40, multi=False):
    """Return (t, categorized, t0, categories) like load_sentry_failures."""
    rng = np.random.default_rng(7)
    t = np.sort(rng.uniform(0, 200, n))
    t = np.round(t, 4)
    cats = ["Database", "Network", "Memory", "Authentication"]
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    categorized = []
    for i, th in enumerate(t):
        cat = cats[i % len(cats)]
        if multi and i % 3 == 0:
            cat = f"{cat}, Network" if cat != "Network" else "Network, Database"
        categorized.append((t0.isoformat(), float(th), cat, f"event {i}"))
    return t, categorized, t0, [("Database", {"db"})]


def _assert_detail(resp, status):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert isinstance(body.get("detail"), str) and body["detail"], body
    return body["detail"]


# ── Startup / auth ───────────────────────────────────────────────────────────

class TestAuth:
    def test_refuses_to_start_without_key(self, api_module, monkeypatch):
        monkeypatch.delenv("RELIABILITY_API_KEY", raising=False)
        monkeypatch.delenv("ALLOW_INSECURE_NO_AUTH", raising=False)
        with pytest.raises(RuntimeError, match="RELIABILITY_API_KEY"):
            api_module.load_api_key()

    def test_insecure_escape_hatch(self, api_module, monkeypatch, caplog):
        monkeypatch.delenv("RELIABILITY_API_KEY", raising=False)
        monkeypatch.setenv("ALLOW_INSECURE_NO_AUTH", "true")
        assert api_module.load_api_key() == ""
        assert "ALLOW_INSECURE_NO_AUTH" in caplog.text

    def test_key_loaded(self, api_module, monkeypatch):
        monkeypatch.setenv("RELIABILITY_API_KEY", " abc ")
        assert api_module.load_api_key() == "abc"

    @pytest.mark.parametrize("method,path", [
        ("GET", "/config"), ("POST", "/config"), ("GET", "/logs"), ("GET", "/trends"),
        ("POST", "/logs/prune"), ("POST", "/ingest/sentry"), ("GET", "/ingest/sentry/projects"),
        ("POST", "/graphql"), ("GET", "/report/AN-20260101-000000/html"),
        ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"), ("GET", "/metrics"),
    ])
    def test_401_without_key(self, anon_client, method, path):
        resp = anon_client.request(method, path)
        assert _assert_detail(resp, 401) == "Invalid or missing API key"
        assert resp.headers.get("X-Request-ID")

    def test_401_with_wrong_key(self, anon_client):
        _assert_detail(anon_client.get("/config", headers={"X-API-Key": "nope"}), 401)

    def test_health_endpoints_open(self, anon_client):
        assert anon_client.get("/health/live").json() == {"status": "ok"}
        assert anon_client.get("/health").status_code == 200

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_docs_available_with_key(self, client, path):
        assert client.get(path).status_code == 200

    def test_insecure_mode_allows_anonymous(self, api_module, anon_client, monkeypatch):
        monkeypatch.setattr(api_module, "API_KEY", "")
        assert anon_client.get("/config").status_code == 200

    def test_cors_preflight_not_blocked(self, anon_client):
        resp = anon_client.options("/config", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ── Request id / error shape ─────────────────────────────────────────────────

class TestRequestIdAndErrors:
    def test_request_id_echoed_and_sanitized(self, client):
        resp = client.get("/health/live", headers={"X-Request-ID": "abc-123_<script>"})
        assert resp.headers["X-Request-ID"] == "abc-123script"

    def test_request_id_generated(self, client):
        rid = client.get("/health/live").headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{16}", rid)

    def test_unknown_route_uniform_404(self, client):
        assert _assert_detail(client.get("/nope"), 404) == "Not Found"

    def test_method_not_allowed_uniform(self, client):
        _assert_detail(client.put("/config"), 405)

    def test_unhandled_exception_sanitized_500(self, api_module, client, monkeypatch):
        def boom():
            raise RuntimeError("secret internals /etc/passwd")
        monkeypatch.setattr(api_module.metrics, "render", boom)
        resp = client.get("/metrics", headers={"X-Request-ID": "req-42"})
        detail = _assert_detail(resp, 500)
        assert "req-42" in detail
        assert "secret" not in resp.text
        assert resp.headers["X-Request-ID"] == "req-42"

    def test_validation_errors_are_strings(self, client):
        detail = _assert_detail(client.post("/ingest/sentry", json={"project": "p"}), 422)
        assert "org" in detail


# ── Rate limiting ────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_limit_enforced(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "RATE_LIMIT_PER_MINUTE", 3)
        for _ in range(3):
            assert client.get("/logs").status_code == 200
        resp = client.get("/logs")
        assert _assert_detail(resp, 429) == "Too many requests"
        assert resp.headers["Retry-After"] == "60"

    def test_liveness_exempt(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "RATE_LIMIT_PER_MINUTE", 1)
        for _ in range(5):
            assert client.get("/health/live").status_code == 200

    def test_xff_honoured_only_when_authenticated(self, api_module, client, anon_client, monkeypatch):
        monkeypatch.setattr(api_module, "RATE_LIMIT_PER_MINUTE", 2)
        # Authenticated (UI proxy): each forwarded client gets its own bucket.
        for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
            for _ in range(2):
                assert client.get("/logs", headers={"X-Forwarded-For": ip}).status_code == 200
        # Unauthenticated: spoofed XFF does not create new buckets.
        api_module._rate_limit_store.clear()
        codes = [anon_client.get("/health", headers={"X-Forwarded-For": f"1.2.3.{i}"}).status_code
                 for i in range(4)]
        assert codes[:2] == [200, 200]
        assert codes[2:] == [429, 429]


# ── Body limit ───────────────────────────────────────────────────────────────

class TestBodyLimit:
    def test_content_length_over_limit(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "MAX_BODY_BYTES", 100)
        resp = client.post("/config", json={"content": "A [b]\n" * 50})
        assert "too large" in _assert_detail(resp, 413)

    def test_chunked_body_over_limit(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "MAX_BODY_BYTES", 100)

        def gen():
            for _ in range(10):
                yield b'{"content": "' + b"x" * 50 + b'"}'

        resp = client.post("/config", content=gen(), headers={"Content-Type": "application/json"})
        _assert_detail(resp, 413)

    def test_chunked_graphql_over_limit(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "MAX_BODY_BYTES", 50)
        resp = client.post("/graphql", content=iter([b"x" * 40, b"y" * 40]))
        _assert_detail(resp, 413)

    def test_invalid_content_length(self, client):
        resp = client.post("/config", content=b"{}", headers={"Content-Length": "abc",
                                                              "Content-Type": "application/json"})
        assert resp.status_code in (400, 422)


# ── Health / metrics ─────────────────────────────────────────────────────────

class TestHealth:
    def test_degraded_without_sentry_token(self, client):
        body = client.get("/health").json()
        assert body["status"] == "degraded"
        assert body["version"] == "2.9.0"
        assert body["checks"] == {"output_writable": True, "config_readable": True,
                                  "sentry_token_configured": False}
        assert body["timestamp"].endswith("+00:00")

    def test_ok_with_token(self, client, monkeypatch):
        monkeypatch.setenv("SENTRY_AUTH_TOKEN", "tok")
        resp = client.get("/health")
        assert resp.status_code == 200 and resp.json()["status"] == "ok"

    def test_503_when_taxonomy_missing(self, client, isolated_dirs):
        (isolated_dirs["config"] / "fault_categories.conf").unlink()
        resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "error"
        assert body["checks"]["config_readable"] is False

    def test_503_when_output_not_writable(self, client, tmp_path, monkeypatch):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        monkeypatch.setenv("OUTPUT_DIR", str(blocker))
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["checks"]["output_writable"] is False

    def test_version_single_source(self, api_module):
        import modeler
        assert api_module.app.version == modeler.__version__ == "2.9.0"


class TestMetrics:
    def test_prometheus_format(self, client):
        client.get("/health/live")
        client.get("/nope")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        text = resp.text
        assert re.search(r'rm_http_requests_total\{method="GET",status="200"\} \d+', text)
        assert re.search(r'rm_http_requests_total\{method="GET",status="404"\} \d+', text)
        for name in ("rm_analysis_duration_seconds_sum", "rm_analysis_duration_seconds_count",
                     "rm_ingest_failures_total", "# TYPE rm_analyses_total counter"):
            assert name in text


# ── Config ───────────────────────────────────────────────────────────────────

class TestConfig:
    def test_startup_seeds_taxonomy(self, client, isolated_dirs):
        seeded = isolated_dirs["config"] / "fault_categories.conf"
        assert seeded.read_text() == (REPO_ROOT / "fault_categories.conf").read_text()
        body = client.get("/config").json()
        assert "Database" in body["content"]
        assert body["settings"] == {"multi_label": False, "optimization_method": "L-BFGS-B",
                                    "tolerance": 1e-6}

    def test_seed_does_not_overwrite(self, api_module, isolated_dirs):
        cfg = isolated_dirs["config"]
        cfg.mkdir(parents=True)
        (cfg / "fault_categories.conf").write_text("Mine [x]\n")
        with TestClient(api_module.app, headers={"X-API-Key": API_KEY}) as c:
            assert c.get("/config").json()["content"] == "Mine [x]\n"

    def test_post_content_persists(self, client, isolated_dirs):
        content = "Database [db, sql]\nNetwork [http, timeout]\n"
        resp = client.post("/config", json={"content": content})
        assert resp.status_code == 200 and resp.json() == {"status": "success"}
        assert (isolated_dirs["config"] / "fault_categories.conf").read_text() == content
        assert client.get("/config").json()["content"] == content
        assert not [p for p in isolated_dirs["config"].iterdir() if p.name.endswith(".tmp")]

    def test_post_settings_persists(self, client, isolated_dirs):
        settings = {"multi_label": True, "optimization_method": "TNC", "tolerance": 1e-4}
        assert client.post("/config", json={"settings": settings}).status_code == 200
        saved = json.loads((isolated_dirs["config"] / "settings.json").read_text())
        assert saved == settings
        assert client.get("/config").json()["settings"] == settings

    @pytest.mark.parametrize("payload", [
        {"content": "not valid"},
        {"content": "# only comments\n"},
        {"content": 123},
        {"settings": {"optimization_method": "BFGS"}},
        {"settings": {"tolerance": -1}},
        {"settings": {"unknown": 1}},
        {"content": "A [b]", "extra": True},
        {},
    ])
    def test_post_invalid_rejected(self, client, payload):
        _assert_detail(client.post("/config", json=payload), 422)

    def test_content_max_size(self, client):
        big = "A [b]\n" * 50000  # 300 KB > 256 KiB limit, < 1 MiB body limit
        _assert_detail(client.post("/config", json={"content": big}), 422)

    def test_corrupt_settings_file_falls_back(self, client, isolated_dirs):
        (isolated_dirs["config"] / "settings.json").write_text("{nope")
        assert client.get("/config").json()["settings"]["optimization_method"] == "L-BFGS-B"

    def test_settings_file_with_legacy_keys(self, client, isolated_dirs):
        (isolated_dirs["config"] / "settings.json").write_text(
            json.dumps({"multi_label": True, "legacy": 1}))
        assert client.get("/config").json()["settings"]["multi_label"] is True

    def test_get_config_when_missing(self, client, isolated_dirs):
        (isolated_dirs["config"] / "fault_categories.conf").unlink()
        assert client.get("/config").json()["content"] == ""

    def test_save_failure_returns_500(self, api_module, client, monkeypatch):
        def fail(*_a, **_k):
            raise OSError("disk full")
        monkeypatch.setattr(api_module.rm_config, "atomic_write_text", fail)
        monkeypatch.setattr(api_module.rm_config, "atomic_write_json", fail)
        assert _assert_detail(client.post("/config", json={"content": "A [b]"}), 500) == \
            "Failed to save configuration"
        assert _assert_detail(client.post("/config", json={"settings": {}}), 500) == \
            "Failed to save settings"


# ── Sentry ingest ────────────────────────────────────────────────────────────

@pytest.fixture
def sentry_token(monkeypatch):
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "test-token")


class TestIngestValidation:
    @pytest.mark.parametrize("payload", [
        {"project": "p"},
        {"org": "o"},
        {"org": "o", "project": "p", "days": 0},
        {"org": "o", "project": "p", "days": 91},
        {"org": "o", "project": "p", "days": "abc"},
        {"org": "o", "project": "p", "days": 1.5},
        {"org": "o", "project": "p", "future_hours": 0},
        {"org": "o", "project": "p", "future_hours": 100001},
        {"org": "../etc", "project": "p"},
        {"org": "o", "project": "p/q"},
        {"org": "o", "project": "p", "surprise": 1},
    ])
    def test_rejects_bad_payload(self, client, sentry_token, payload):
        _assert_detail(client.post("/ingest/sentry", json=payload), 422)

    def test_requires_token(self, client):
        detail = _assert_detail(client.post("/ingest/sentry", json={"org": "o", "project": "p"}), 503)
        assert "SENTRY_AUTH_TOKEN" in detail

    def test_taxonomy_not_loaded(self, client, sentry_token, isolated_dirs):
        (isolated_dirs["config"] / "fault_categories.conf").write_text("# empty\n")
        resp = client.post("/ingest/sentry", json={"org": "o", "project": "p"})
        assert _assert_detail(resp, 500) == "taxonomy not loaded"


class TestIngestPipeline:
    def test_single_project_success(self, api_module, client, sentry_token, monkeypatch, isolated_dirs):
        calls = {}

        def fake(org, project, token, config_path, days, multi_label, cancel_event=None):
            calls.update(org=org, project=project, token=token, days=days, config_path=config_path)
            return _synthetic_sentry()

        monkeypatch.setattr(api_module, "load_sentry_failures", fake)
        resp = client.post("/ingest/sentry", json={"org": "acme", "project": "web", "days": 7,
                                                   "future_hours": 500})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert NEW_ID_RE.match(body["id"])
        assert calls["token"] == "test-token" and calls["days"] == 7
        assert Path(calls["config_path"]) == isolated_dirs["config"] / "fault_categories.conf"
        assert body["summary"]["total_failures"] == 40
        assert {m["id"] for m in body["models"]} <= {"go", "mo"} and body["models"]
        assert set(body["plots"]) == {"reliability", "intensity", "categories"}
        assert body["graph_report"] is not None
        out = isolated_dirs["output"]
        assert (out / "logs" / f"{body['id']}.json").is_file()
        assert (out / "analyses" / f"{body['id']}.json").is_file()
        assert (out / "plots" / f"{body['id']}_reliability.png").is_file()
        assert list((out / "temp_plots").iterdir()) == []
        metrics = client.get("/metrics").text
        assert 'rm_analyses_total{result="success"} ' in metrics

        # Archive is visible through /logs, /trends and /report
        logs = client.get("/logs").json()
        assert logs["total"] == 1 and logs["logs"][0]["id"] == body["id"]
        report = client.get(f"/report/{body['id']}/html").json()
        assert body["id"] in report["html"] and "data:image/png;base64," in report["html"]

        # GraphQL sees the new analysis
        q = '{ cascadeChains(analysisId: "%s", limit: 3) { chain occurrenceCount } }' % body["id"]
        gql = client.post("/graphql", json={"query": q}).json()
        assert "errors" not in gql and isinstance(gql["data"]["cascadeChains"], list)

    def test_ids_are_unique(self, api_module):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ids = {api_module.new_analysis_id(now) for _ in range(200)}
        assert len(ids) > 190
        assert all(NEW_ID_RE.match(i) for i in ids)

    def test_all_projects(self, api_module, client, sentry_token, monkeypatch):
        def fake_all(org, token, config_path, days, multi_label, cancel_event=None):
            t, cat, t0, cats = _synthetic_sentry(multi=True)
            return t, cat, t0, cats, {"api": 10, "web": 30}

        monkeypatch.setattr(api_module, "load_sentry_failures_all", fake_all)
        body = client.post("/ingest/sentry", json={"org": "acme", "project": "all"}).json()
        assert list(body["projects"].items()) == [("web", 30), ("api", 10)]

    def test_no_events(self, api_module, client, sentry_token, monkeypatch):
        monkeypatch.setattr(api_module, "load_sentry_failures",
                            lambda *a, **k: (np.array([]), [], datetime.now(timezone.utc), []))
        assert "No failure events" in _assert_detail(
            client.post("/ingest/sentry", json={"org": "o", "project": "p"}), 400)

    def test_sentry_error_502(self, api_module, client, sentry_token, monkeypatch):
        def fail(*a, **k):
            raise api_module.SentryError("Sentry authentication failed (401).")
        monkeypatch.setattr(api_module, "load_sentry_failures", fail)
        resp = client.post("/ingest/sentry", json={"org": "o", "project": "p"})
        assert "401" in _assert_detail(resp, 502)
        assert "rm_ingest_failures_total 1" in client.get("/metrics").text or \
            re.search(r"rm_ingest_failures_total [1-9]", client.get("/metrics").text)

    def test_sentry_cancelled_504(self, api_module, client, sentry_token, monkeypatch):
        def fail(*a, **k):
            raise api_module.SentryCancelled("cancelled")
        monkeypatch.setattr(api_module, "load_sentry_failures", fail)
        _assert_detail(client.post("/ingest/sentry", json={"org": "o", "project": "p"}), 504)

    def test_taxonomy_error_inside_loader(self, api_module, client, sentry_token, monkeypatch):
        def fail(*a, **k):
            raise api_module.TaxonomyError("gone")
        monkeypatch.setattr(api_module, "load_sentry_failures", fail)
        assert _assert_detail(client.post("/ingest/sentry", json={"org": "o", "project": "p"}),
                              500) == "taxonomy not loaded"

    def test_fetch_timeout_sets_cancel_flag(self, api_module, client, sentry_token, monkeypatch):
        seen = {}

        def slow(*a, cancel_event=None, **k):
            seen["event"] = cancel_event
            cancel_event.wait(5)
            raise api_module.SentryCancelled("stopped")

        monkeypatch.setattr(api_module, "ANALYSIS_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(api_module, "load_sentry_failures", slow)
        started = time.monotonic()
        resp = client.post("/ingest/sentry", json={"org": "o", "project": "p"})
        assert "timed out" in _assert_detail(resp, 504)
        assert time.monotonic() - started < 3
        assert seen["event"].wait(2)

    def test_analysis_timeout_fires_while_loop_responsive(self, api_module, client, sentry_token,
                                                          monkeypatch):
        release = threading.Event()

        def slow_analysis(*a, **k):
            release.wait(5)
            return {}

        monkeypatch.setattr(api_module, "load_sentry_failures", lambda *a, **k: _synthetic_sentry())
        monkeypatch.setattr(api_module, "_run_analysis", slow_analysis)
        monkeypatch.setattr(api_module, "ANALYSIS_TIMEOUT_SECONDS", 0.3)
        started = time.monotonic()
        resp = client.post("/ingest/sentry", json={"org": "o", "project": "p"})
        release.set()
        assert "timed out" in _assert_detail(resp, 504)
        assert time.monotonic() - started < 3
        assert 'rm_analyses_total{result="timeout"}' in client.get("/metrics").text

    def test_analysis_error_500_and_temp_cleanup(self, api_module, client, sentry_token,
                                                 monkeypatch, isolated_dirs):
        monkeypatch.setattr(api_module, "load_sentry_failures", lambda *a, **k: _synthetic_sentry())

        def explode(*a, **k):
            raise RuntimeError("plot exploded")
        monkeypatch.setattr(api_module, "plot_categories", explode)
        resp = client.post("/ingest/sentry", json={"org": "o", "project": "p"})
        assert "Analysis failed" in _assert_detail(resp, 500)
        assert "exploded" not in resp.text
        assert list((isolated_dirs["output"] / "temp_plots").iterdir()) == []
        assert 'rm_analyses_total{result="error"}' in client.get("/metrics").text

    def test_settings_applied(self, api_module, client, sentry_token, monkeypatch):
        client.post("/config", json={"settings": {"multi_label": True, "optimization_method": "TNC",
                                                  "tolerance": 1e-5}})
        seen = {}

        def fake(org, project, token, config_path, days, multi_label, cancel_event=None):
            seen["multi_label"] = multi_label
            return _synthetic_sentry()

        real_fit = api_module.fit_model

        def spy_fit(*a, **k):
            seen["method"] = k["method"]
            return real_fit(*a, **k)

        monkeypatch.setattr(api_module, "load_sentry_failures", fake)
        monkeypatch.setattr(api_module, "fit_model", spy_fit)
        assert client.post("/ingest/sentry", json={"org": "o", "project": "p"}).status_code == 200
        assert seen == {"multi_label": True, "method": "TNC"}

    def test_model_fit_failure_tolerated(self, api_module, client, sentry_token, monkeypatch):
        monkeypatch.setattr(api_module, "load_sentry_failures", lambda *a, **k: _synthetic_sentry())

        def flaky(t, T, model_name, **k):
            if model_name == "go":
                raise ValueError("bad fit")
            return None, None, None, None
        monkeypatch.setattr(api_module, "fit_model", flaky)
        body = client.post("/ingest/sentry", json={"org": "o", "project": "p"}).json()
        assert body["models"] == []


class TestSentryProjects:
    def test_requires_org(self, client):
        _assert_detail(client.get("/ingest/sentry/projects"), 422)

    def test_invalid_org(self, client):
        _assert_detail(client.get("/ingest/sentry/projects", params={"org": "a/b"}), 422)

    def test_requires_token(self, client):
        _assert_detail(client.get("/ingest/sentry/projects", params={"org": "acme"}), 503)

    def test_lists_projects(self, api_module, client, sentry_token, monkeypatch):
        monkeypatch.setattr(api_module, "list_sentry_projects",
                            lambda org, token, base, cancel: [{"slug": "web", "name": "Web"},
                                                              {"slug": "api"}, "junk"])
        body = client.get("/ingest/sentry/projects", params={"org": "acme"}).json()
        assert body == {"org": "acme", "count": 3, "projects": [
            {"slug": "web", "name": "Web"}, {"slug": "api", "name": "api"}]}

    def test_sentry_error(self, api_module, client, sentry_token, monkeypatch):
        def fail(*a):
            raise api_module.SentryError("Sentry organization not found (404).")
        monkeypatch.setattr(api_module, "list_sentry_projects", fail)
        _assert_detail(client.get("/ingest/sentry/projects", params={"org": "acme"}), 502)

    def test_timeout(self, api_module, client, sentry_token, monkeypatch):
        def slow(org, token, base, cancel):
            cancel.wait(5)
            return []
        monkeypatch.setattr(api_module, "ANALYSIS_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(api_module, "list_sentry_projects", slow)
        _assert_detail(client.get("/ingest/sentry/projects", params={"org": "acme"}), 504)


# ── Logs / prune / trends ────────────────────────────────────────────────────

def _write_log(output_dir: Path, log_id: str, tf: int, dh: float, date="2026-01-01 00:00", mtime=None):
    d = output_dir / "logs"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{log_id}.json"
    p.write_text(json.dumps({"id": log_id, "date": date, "file": "sentry://x", "status": "Completed",
                             "summary": {"total_failures": tf, "duration_hours": dh}}))
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


class TestLogsAndTrends:
    def test_logs_empty(self, client):
        assert client.get("/logs").json() == {"total": 0, "logs": []}

    def test_logs_pagination_and_corrupt_skipped(self, client, isolated_dirs, caplog):
        out = isolated_dirs["output"]
        for i in range(5):
            _write_log(out, f"AN-2026010{i + 1}-000000", 10, 5.0, date=f"2026-01-0{i + 1} 00:00")
        (out / "logs" / "AN-20260109-000000.json").write_text("{corrupt")
        (out / "logs" / "AN-20260110-000000.json").write_text("[1, 2]")
        body = client.get("/logs", params={"limit": 2, "offset": 1}).json()
        assert body["total"] == 5
        assert [e["id"] for e in body["logs"]] == ["AN-20260104-000000", "AN-20260103-000000"]
        assert "corrupt" in caplog.text

    def test_trends(self, client, isolated_dirs):
        out = isolated_dirs["output"]
        assert client.get("/trends").json() == {"runs": [], "trend": "insufficient_data"}
        _write_log(out, "AN-20260101-000000", 10, 10.0, mtime=1000)
        assert client.get("/trends").json()["trend"] == "single_run"
        _write_log(out, "AN-20260102-000000", 5, 10.0, mtime=2000)
        body = client.get("/trends").json()
        assert body["trend"] == "improving" and body["num_runs"] == 2
        _write_log(out, "AN-20260103-000000", 40, 10.0, mtime=3000)
        assert client.get("/trends").json()["trend"] == "degrading"
        _write_log(out, "AN-20260104-000000", 10, 10.0, mtime=4000)
        assert client.get("/trends").json()["trend"] == "stable"

    def test_prune(self, api_module, client, isolated_dirs):
        out = isolated_dirs["output"]
        old = time.time() - 100 * 86400
        _write_log(out, "AN-20250101-000000", 1, 1.0, mtime=old)
        _write_log(out, "AN-20260101-000000", 1, 1.0)
        for sub, name in [("analyses", "AN-20250101-000000.json"), ("plots", "AN-20250101-000000_reliability.png")]:
            (out / sub).mkdir(parents=True, exist_ok=True)
            p = out / sub / name
            p.write_text("x")
            os.utime(p, (old, old))
        (out / "temp_plots").mkdir(parents=True, exist_ok=True)
        stale = out / "temp_plots" / "plot_dead_reliability_plot.png"
        stale.write_text("x")
        os.utime(stale, (time.time() - 7200,) * 2)
        fresh = out / "temp_plots" / "plot_live_reliability_plot.png"
        fresh.write_text("x")

        body = client.post("/logs/prune", params={"retention_days": 90}).json()
        assert body["pruned"] == 4
        assert body["by_directory"] == {"logs": 1, "analyses": 1, "plots": 1, "temp_plots": 1}
        assert (out / "logs" / "AN-20260101-000000.json").exists()
        assert fresh.exists() and not stale.exists()

    def test_prune_default_and_validation(self, client):
        assert client.post("/logs/prune").json()["pruned"] == 0
        _assert_detail(client.post("/logs/prune", params={"retention_days": 3}), 422)
        _assert_detail(client.post("/logs/prune", params={"retention_days": "x"}), 422)

    def test_prune_forgets_cached_analyses(self, api_module, isolated_dirs):
        from web.api import graphql_schema as gql
        gql.store_analysis_data("AN-20250101-000000", [("x", 0.0, "A", "d")])
        path = isolated_dirs["output"] / "analyses" / "AN-20250101-000000.json"
        os.utime(path, (time.time() - 400 * 86400,) * 2)
        api_module.prune_output(90)
        assert gql.get_categorized_data("AN-20250101-000000") is None

    def test_prune_unlink_failure_logged(self, api_module, isolated_dirs, monkeypatch, caplog):
        out = isolated_dirs["output"]
        _write_log(out, "AN-20250101-000000", 1, 1.0, mtime=time.time() - 400 * 86400)

        def deny(self, *a, **k):
            raise PermissionError("read-only")
        monkeypatch.setattr(Path, "unlink", deny)
        result = api_module.prune_output(90)
        assert result["logs"] == []
        assert "Failed to prune" in caplog.text

    def test_retention_disabled_lifespan(self, api_module, monkeypatch, caplog):
        monkeypatch.setattr(api_module, "RETENTION_DAYS", 0)
        with TestClient(api_module.app, headers={"X-API-Key": API_KEY}) as c:
            assert c.get("/health/live").status_code == 200
        assert "retention pruning disabled" in caplog.text


# ── Reports ──────────────────────────────────────────────────────────────────

class TestReport:
    @pytest.mark.parametrize("bad", ["not-an-id", "AN-2026", "AN-20260101-000000-XYZ123", "...", "AN-20260101-000000.json"])
    def test_invalid_ids(self, client, bad):
        _assert_detail(client.get(f"/report/{bad}/html"), 400)

    @pytest.mark.parametrize("path", ["/report/../../etc/passwd/html", "/report/..%2F..%2Fetc/html",
                                      "/report/%2e%2e/html"])
    def test_traversal_segments_never_reach_files(self, client, path):
        assert client.get(path).status_code in (400, 404)

    def test_not_found(self, client):
        assert "not found" in _assert_detail(client.get("/report/AN-20260101-000000/html"), 404)

    def test_corrupt_record(self, client, isolated_dirs):
        d = isolated_dirs["output"] / "logs"
        d.mkdir(parents=True)
        (d / "AN-20260101-000000.json").write_text("{nope")
        assert "corrupt" in _assert_detail(client.get("/report/AN-20260101-000000/html"), 500)

    def test_legacy_and_new_ids_render(self, client, isolated_dirs):
        out = isolated_dirs["output"]
        for aid in ("AN-20260101-000000", "AN-20260101-000000-a1b2c3"):
            _write_log(out, aid, 12, 24.0)
            html = client.get(f"/report/{aid}/html").json()["html"]
            assert aid in html and "UTC" in html and "2.9.0" in html
            assert "data:image/png" not in html


# ── GraphQL ──────────────────────────────────────────────────────────────────

class TestGraphQLEndpoint:
    def _store(self):
        from web.api import graphql_schema as gql
        data = [(f"t{i}", i * 0.25, ["Database", "Network", "Memory"][i % 3], "d") for i in range(30)]
        gql.store_analysis_data("AN-20260101-000000-abcdef", data)
        return "AN-20260101-000000-abcdef"

    def test_query_ok(self, client):
        aid = self._store()
        resp = client.post("/graphql", json={"query": "query Q($id: String!) { keystoneCategories(analysisId: $id) { node } }",
                                             "variables": {"id": aid}, "operationName": "Q"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]["keystoneCategories"]) == 3

    @pytest.mark.parametrize("body,status", [
        (b"not json", 400),
        (b"[1]", 400),
        (b'{"query": ""}', 400),
        (b'{"query": "{ availableAnalyses }", "variables": [1]}', 400),
        (b'{"query": "{ availableAnalyses }", "operationName": 5}', 400),
        (b'{"query": "{ __schema { types { name } } }"}', 400),
        (b'{"query": "{ availableAnalyses "}', 400),
        (b'{"query": "{ nope }"}', 400),
    ])
    def test_bad_requests(self, client, body, status):
        resp = client.post("/graphql", content=body, headers={"Content-Type": "application/json"})
        _assert_detail(resp, status)

    def test_too_large(self, api_module, client, monkeypatch):
        monkeypatch.setattr(api_module, "MAX_GRAPHQL_BYTES", 10)
        _assert_detail(client.post("/graphql", json={"query": "{ availableAnalyses }"}), 413)

    def test_depth_limit(self, client):
        q = "{ failureGraph(analysisId: \"x\") { graphJson { nodes { id } } } }"
        assert client.post("/graphql", json={"query": q}).status_code == 200
        deep = "query { " + "a { " * 12 + "b" + " }" * 12 + " }"
        resp = client.post("/graphql", json={"query": deep})
        assert resp.status_code == 400

    def test_argument_bounds(self, client):
        aid = self._store()
        for q in [
            '{ failureGraph(analysisId: "%s", cascadeWindowHours: 0.5) { graphMetrics { numCategories } } }',
            '{ failureGraph(analysisId: "%s", cascadeWindowHours: 721) { graphMetrics { numCategories } } }',
            '{ failureGraph(analysisId: "%s", minCooccurrence: 0) { graphMetrics { numCategories } } }',
            '{ failureGraph(analysisId: "%s", minCooccurrence: 1001) { graphMetrics { numCategories } } }',
            '{ keystoneCategories(analysisId: "%s", limit: 0) { node } }',
            '{ cascadeChains(analysisId: "%s", limit: 101) { chain } }',
        ]:
            body = client.post("/graphql", json={"query": q % aid}).json()
            assert body["errors"] and "must be between" in body["errors"][0], body
        body = client.post("/graphql", json={"query": "{ keystoneCategoriesAcross(limit: 500) { node } }"}).json()
        assert "must be between" in body["errors"][0]

    def test_resolver_errors_sanitized(self, client, monkeypatch, caplog):
        from web.api import graphql_schema as gql

        def boom(*a, **k):
            raise RuntimeError("secret /var/lib/stuff")
        monkeypatch.setattr(gql, "get_failure_report", boom)
        body = client.post("/graphql", json={"query": '{ cascadeChains(analysisId: "AN-20260101-000000") { chain } }'}).json()
        assert body["errors"] == ["Internal error while resolving field 'cascadeChains'"]
        assert "secret" in caplog.text  # logged server-side only

    def test_timeout(self, api_module, client, monkeypatch):
        from web.api import graphql_schema as gql
        release = threading.Event()

        def slow(*a, **k):
            release.wait(5)
            return {"data": None}, True
        monkeypatch.setattr(gql, "execute_query", slow)
        monkeypatch.setattr(api_module, "ANALYSIS_TIMEOUT_SECONDS", 0.2)
        resp = client.post("/graphql", json={"query": "{ availableAnalyses }"})
        release.set()
        _assert_detail(resp, 504)


# ── Running from a checkout ──────────────────────────────────────────────────

def test_uvicorn_style_import_from_web_api_dir(tmp_path):
    """`cd web/api && uvicorn main:app` must be able to import `modeler`."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(RELIABILITY_API_KEY="k", CONFIG_DIR=str(tmp_path / "c"), OUTPUT_DIR=str(tmp_path / "o"))
    proc = subprocess.run(
        [sys.executable, "-c", "import main; print(main.app.version)"],
        cwd=REPO_ROOT / "web" / "api", env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("2.9.0")


def test_import_refused_without_key(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "RELIABILITY_API_KEY",
                                                              "ALLOW_INSECURE_NO_AUTH")}
    proc = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=REPO_ROOT / "web" / "api", env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode != 0
    assert "RELIABILITY_API_KEY is not set" in proc.stderr
