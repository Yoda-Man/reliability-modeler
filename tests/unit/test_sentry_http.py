"""
Sentry fetch-path tests against a local fake HTTP server (no internet).

Covers cursor pagination, retry/backoff on 429 and 5xx (incl. Retry-After),
non-retryable errors, malformed responses, dropped unparseable events,
the "all projects" aggregation, and cooperative cancellation.
"""
import json
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from modeler import sentry
from modeler.data import TaxonomyError
from modeler.sentry import (
    SentryCancelled,
    SentryError,
    list_sentry_projects,
    load_sentry_failures,
    load_sentry_failures_all,
)


class FakeSentry:
    """Scriptable fake: routes map a path to a list of responses served in order
    (the last response repeats). A response is (status, body, headers)."""

    def __init__(self):
        self.routes = {}
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                fake.requests.append((parsed.path, qs, self.headers.get("Authorization")))
                key = (parsed.path, qs.get("cursor", [None])[0])
                queue = fake.routes.get(key) or fake.routes.get((parsed.path, "*"))
                if not queue:
                    status, body, headers = 404, b"{}", {}
                else:
                    status, body, headers = queue.pop(0) if len(queue) > 1 else queue[0]
                if not isinstance(body, bytes):
                    body = json.dumps(body).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/0/"

    def route(self, path, *responses, cursor=None):
        self.routes[(path, cursor)] = list(responses)

    def link(self, path, cursor, results=True):
        return {"Link": f'<{self.base}{path[len("/api/0/"):]}?&cursor={cursor}>; rel="next"; '
                        f'results="{"true" if results else "false"}"; cursor="{cursor}"'}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake():
    f = FakeSentry()
    yield f
    f.close()


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(sentry, "BACKOFF_BASE_SECONDS", 0.0)
    monkeypatch.setattr(sentry, "REQUEST_TIMEOUT_SECONDS", 5)


@pytest.fixture
def taxonomy(tmp_path):
    p = tmp_path / "fault_categories.conf"
    p.write_text("Database [db, sql]\nNetwork [timeout, http]\n")
    return p


def _event(i, title="DB timeout", base=datetime(2026, 1, 1, tzinfo=timezone.utc)):
    return {"dateCreated": (base + timedelta(hours=i)).isoformat().replace("+00:00", "Z"), "title": title}


EVENTS = "/api/0/projects/acme/web/events/"


def test_pagination_follows_cursor(fake, taxonomy):
    fake.route(EVENTS, (200, [_event(0), _event(1)], fake.link(EVENTS, "c1")))
    fake.route(EVENTS, (200, [_event(2, "http 502")], fake.link(EVENTS, "c2", results=False)), cursor="c1")
    t, cat_list, t0, cats = load_sentry_failures("acme", "web", "tok", taxonomy, days=7, base_url=fake.base)
    assert list(t) == [0.0, 1.0, 2.0]
    assert [c[2] for c in cat_list] == ["Database", "Database", "Network"]
    assert len(fake.requests) == 2
    first_qs = fake.requests[0][1]
    assert first_qs["statsPeriod"] == ["7d"] and first_qs["limit"] == ["100"]
    assert fake.requests[0][2] == "Bearer tok"


def test_max_pages_truncates(fake, taxonomy, monkeypatch, caplog):
    monkeypatch.setattr(sentry, "MAX_PAGES", 2)
    fake.route(EVENTS, (200, [_event(0)], fake.link(EVENTS, "c1")))
    fake.route(EVENTS, (200, [_event(1)], fake.link(EVENTS, "c2")), cursor="c1")
    t, *_ = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 2
    assert "truncated" in caplog.text


def test_429_retried_with_retry_after(fake, taxonomy, monkeypatch):
    sleeps = []
    monkeypatch.setattr(sentry.time, "sleep", lambda s: sleeps.append(s))
    fake.route(EVENTS, (429, {"detail": "slow down"}, {"Retry-After": "2"}),
               (200, [_event(0), _event(1)], {}))
    t, *_ = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 2
    assert len(fake.requests) == 2
    assert sleeps == [2.0]


def test_5xx_retries_exhausted(fake, taxonomy, monkeypatch, caplog):
    monkeypatch.setattr(sentry.time, "sleep", lambda s: None)
    fake.route(EVENTS, (503, b"oops", {}))
    with pytest.raises(SentryError, match="HTTP 503"):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(fake.requests) == 1 + sentry.MAX_RETRIES
    assert "retry 3/3" in caplog.text


def test_429_exhausted_message(fake, taxonomy, monkeypatch):
    monkeypatch.setattr(sentry.time, "sleep", lambda s: None)
    fake.route(EVENTS, (429, b"{}", {}))
    with pytest.raises(SentryError, match="rate limit"):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)


@pytest.mark.parametrize("status,match", [(401, "authentication"), (403, "denied"), (404, "not found")])
def test_non_retryable_errors(fake, taxonomy, status, match):
    fake.route(EVENTS, (status, b"{}", {}))
    with pytest.raises(SentryError, match=match):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(fake.requests) == 1


@pytest.mark.parametrize("body", [b"<html>", b'{"not": "a list"}'])
def test_malformed_response(fake, taxonomy, body):
    fake.route(EVENTS, (200, body, {}))
    with pytest.raises(SentryError):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)


def test_bad_events_dropped_and_logged(fake, taxonomy, caplog):
    events = [_event(0), {"title": "no timestamp"}, {"dateCreated": "garbage"},
              {"dateCreated": 12345}, _event(3)]
    fake.route(EVENTS, (200, events, {}))
    t, cat_list, *_ = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 2
    assert "dropped 3 of 5 events" in caplog.text


def test_no_events(fake, taxonomy):
    fake.route(EVENTS, (200, [], {}))
    t, cat_list, t0, cats = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 0 and cat_list == [] and cats


def test_missing_taxonomy_raises_before_fetch(fake, tmp_path):
    with pytest.raises(TaxonomyError):
        load_sentry_failures("acme", "web", "tok", tmp_path / "missing.conf", base_url=fake.base)
    assert fake.requests == []


def test_network_error_retried_then_raised(taxonomy, monkeypatch):
    monkeypatch.setattr(sentry.time, "sleep", lambda s: None)
    calls = []
    real = sentry.urllib.request.urlopen

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(sentry.urllib.request, "urlopen", counting)
    with pytest.raises(SentryError, match="network error"):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url="http://127.0.0.1:9/api/0/")
    assert len(calls) == 1 + sentry.MAX_RETRIES


def test_cancel_before_fetch(fake, taxonomy):
    fake.route(EVENTS, (200, [_event(0)], {}))
    ev = threading.Event()
    ev.set()
    with pytest.raises(SentryCancelled):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base, cancel_event=ev)
    assert fake.requests == []


def test_cancel_interrupts_backoff(fake, taxonomy, monkeypatch):
    monkeypatch.setattr(sentry, "BACKOFF_BASE_SECONDS", 30.0)
    fake.route(EVENTS, (503, b"", {}))
    ev = threading.Event()
    threading.Timer(0.2, ev.set).start()
    with pytest.raises(SentryCancelled):
        load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base, cancel_event=ev)
    assert len(fake.requests) == 1


PROJECTS = "/api/0/organizations/acme/projects/"


def test_list_projects_paginates(fake):
    fake.route(PROJECTS, (200, [{"slug": "web", "name": "Web"}], fake.link(PROJECTS, "p1")))
    fake.route(PROJECTS, (200, [{"slug": "api"}], {}), cursor="p1")
    projects = list_sentry_projects("acme", "tok", fake.base)
    assert [p["slug"] for p in projects] == ["web", "api"]


def test_list_projects_404(fake):
    with pytest.raises(SentryError, match="not found"):
        list_sentry_projects("acme", "tok", fake.base)


def test_list_projects_uses_env_base_url(fake, monkeypatch):
    monkeypatch.setenv("SENTRY_BASE_URL", fake.base)
    fake.route(PROJECTS, (200, [], {}))
    assert list_sentry_projects("acme", "tok") == []


def test_all_projects_aggregates_and_skips_failures(fake, taxonomy, caplog):
    fake.route(PROJECTS, (200, [{"slug": "web", "name": "Web"}, {"slug": "api", "name": "API"},
                                {"slug": "gone"}, {"name": "no slug"}], {}))
    fake.route(EVENTS, (200, [_event(0), _event(2)], {}))
    fake.route("/api/0/projects/acme/api/events/", (200, [_event(1, "http timeout"), {"bad": 1}], {}))
    t, cat_list, t0, cats, counts = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert counts == {"Web": 2, "API": 1}
    assert list(t) == [0.0, 1.0, 2.0]
    assert cat_list[1][3].startswith("[project: API]")
    assert "skipping project gone" in caplog.text


def test_all_projects_caps_count(fake, taxonomy, caplog):
    fake.route(PROJECTS, (200, [{"slug": f"p{i}"} for i in range(3)], {}))
    fake.route("/api/0/projects/acme/p0/events/", (200, [_event(0)], {}))
    *_, counts = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base, max_projects=1)
    assert counts == {"p0": 1}
    assert "only the first 1" in caplog.text


def test_all_projects_empty_org(fake, taxonomy):
    fake.route(PROJECTS, (200, [], {}))
    t, cat_list, t0, cats, counts = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 0 and counts == {}


def test_all_projects_no_events(fake, taxonomy):
    fake.route(PROJECTS, (200, [{"slug": "web"}], {}))
    fake.route(EVENTS, (200, [], {}))
    t, cat_list, t0, cats, counts = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 0 and counts == {"web": 0}


def test_all_projects_cancel_propagates(fake, taxonomy):
    fake.route(PROJECTS, (200, [{"slug": "web"}, {"slug": "api"}], {}))
    ev = threading.Event()

    def set_after_first(*a, **k):
        ev.set()
        return []
    with pytest.raises(SentryCancelled):
        import unittest.mock as m
        with m.patch.object(sentry, "_fetch_project_events", side_effect=set_after_first):
            load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base, cancel_event=ev)


def test_retry_delay_parsing():
    assert sentry._retry_delay(1, "5") == 5.0
    assert sentry._retry_delay(1, "9999") == sentry.MAX_BACKOFF_SECONDS
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    assert 5 <= sentry._retry_delay(1, future) <= 10
    assert sentry._retry_delay(3, "not a date") == min(sentry.MAX_BACKOFF_SECONDS,
                                                         sentry.BACKOFF_BASE_SECONDS * 4)
    assert sentry._retry_delay(2, None) == sentry.BACKOFF_BASE_SECONDS * 2


def test_extract_cursor_results_false():
    link = '<https://x/?cursor=1:0:0>; rel="next"; results="false"; cursor="1:0:0"'
    assert sentry._extract_next_cursor(link) is None
