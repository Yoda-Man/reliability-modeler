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
    list_sentry_organizations,
    list_sentry_projects,
    load_sentry_failures,
    load_sentry_failures_all,
    get_event_context,
    summarize_event,
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
    t, cat_list, t0, cats, truncated = load_sentry_failures("acme", "web", "tok", taxonomy, days=7, base_url=fake.base)
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
    t, *_, truncated = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 2
    assert truncated is True
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
    t, cat_list, t0, cats, truncated = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
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
    t, cat_list, t0, cats, counts, truncated = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert counts == {"Web": 2, "API": 1}
    assert list(t) == [0.0, 1.0, 2.0]
    assert cat_list[1][3].startswith("[project: API]")
    assert "skipping project gone" in caplog.text


def test_all_projects_caps_count(fake, taxonomy, caplog):
    fake.route(PROJECTS, (200, [{"slug": f"p{i}"} for i in range(3)], {}))
    fake.route("/api/0/projects/acme/p0/events/", (200, [_event(0)], {}))
    *_, counts, _truncated = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base, max_projects=1)
    assert counts == {"p0": 1}
    assert "only the first 1" in caplog.text


def test_all_projects_empty_org(fake, taxonomy):
    fake.route(PROJECTS, (200, [], {}))
    t, cat_list, t0, cats, counts, truncated = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 0 and counts == {}


def test_all_projects_no_events(fake, taxonomy):
    fake.route(PROJECTS, (200, [{"slug": "web"}], {}))
    fake.route(EVENTS, (200, [], {}))
    t, cat_list, t0, cats, counts, truncated = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 0 and counts == {"web": 0}


def test_all_projects_cancel_propagates(fake, taxonomy):
    fake.route(PROJECTS, (200, [{"slug": "web"}, {"slug": "api"}], {}))
    ev = threading.Event()

    def set_after_first(*a, **k):
        ev.set()
        return [], False
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


def test_all_projects_truncation_trims_to_common_start(fake, taxonomy, monkeypatch):
    """A project that hit the event cap only covers recent history; every project
    is trimmed to start at its oldest kept event so the merged timeline is not skewed."""
    monkeypatch.setattr(sentry, "MAX_PAGES", 1)
    api_events = "/api/0/projects/acme/api/events/"
    fake.route(PROJECTS, (200, [{"slug": "web", "name": "Web"}, {"slug": "api", "name": "API"}], {}))
    # web: complete history 0..9h; api: capped (more pages exist), newest first, oldest kept = 5h
    fake.route(EVENTS, (200, [_event(i) for i in range(10)], {}))
    fake.route(api_events, (200, [_event(i, "http 500") for i in (9, 7, 5)], fake.link(api_events, "c1")))
    t, cat_list, t0, cats, counts, truncated = load_sentry_failures_all("acme", "tok", taxonomy,
                                                                         base_url=fake.base)
    assert truncated is True
    assert counts == {"Web": 5, "API": 3}
    assert t0 == datetime(2026, 1, 1, 5, tzinfo=timezone.utc)
    assert list(t)[0] == 0.0 and len(t) == 8


def test_all_projects_not_truncated(fake, taxonomy):
    fake.route(PROJECTS, (200, [{"slug": "web"}], {}))
    fake.route(EVENTS, (200, [_event(0), _event(1)], {}))
    *_, counts, truncated = load_sentry_failures_all("acme", "tok", taxonomy, base_url=fake.base)
    assert truncated is False and counts == {"web": 2}


# ── Organizations and regions ────────────────────────────────────────────────

def test_is_saas_only_trusts_https_sentry_hosts():
    assert sentry._is_saas("https://sentry.io/api/0")
    assert sentry._is_saas("https://de.sentry.io")
    assert not sentry._is_saas("http://de.sentry.io")          # no plain HTTP
    assert not sentry._is_saas("https://sentry.io.evil.com")   # look-alike host
    assert not sentry._is_saas("https://evil.com/sentry.io")


def test_self_hosted_lists_orgs_on_configured_base(fake, monkeypatch):
    monkeypatch.setattr(sentry, "_org_region", {})
    fake.route("/api/0/organizations/", (200, [{"slug": "acme", "name": "Acme"}, {"slug": "bad/slug"}], {}))
    orgs = list_sentry_organizations("tok", base_url=fake.base)
    assert orgs == [{"slug": "acme", "name": "Acme", "region": fake.base.rstrip("/")}]
    assert fake.requests[0][1] == {"member": ["1"]}


def test_saas_resolves_each_org_to_its_region(fake, monkeypatch, taxonomy):
    """An EU org's projects and events are read from its regional API, not the default host."""
    root = fake.base[: -len("/api/0/")]
    monkeypatch.setattr(sentry, "_org_region", {})
    monkeypatch.setattr(sentry, "_is_saas", lambda url: url.startswith(root))  # treat the fake as sentry.io
    monkeypatch.setattr(sentry, "CONTROL_API_URL", f"{root}/control/api/0")
    fake.route("/control/api/0/organizations/",
               (200, [{"slug": "acme", "name": "Acme", "links": {"regionUrl": f"{root}/eu"}}], {}))
    fake.route("/eu/api/0/organizations/acme/projects/", (200, [{"slug": "web", "name": "Web"}], {}))
    fake.route("/eu/api/0/projects/acme/web/events/", (200, [_event(0), _event(1)], fake.link(EVENTS, "x", results=False)))

    assert [p["slug"] for p in list_sentry_projects("acme", "tok", base_url=fake.base)] == ["web"]
    t, *_ = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base)
    assert len(t) == 2
    paths = [r[0] for r in fake.requests]
    assert paths.count("/control/api/0/organizations/") == 1  # region looked up once, then cached
    assert "/eu/api/0/projects/acme/web/events/" in paths
    assert not any(p.startswith("/api/0/organizations/acme") for p in paths)


def test_region_outside_sentry_is_ignored(fake, monkeypatch):
    """A regionUrl that isn't a Sentry host never receives the token."""
    root = fake.base[: -len("/api/0/")]
    monkeypatch.setattr(sentry, "_org_region", {})
    monkeypatch.setattr(sentry, "_is_saas", lambda url: url.startswith(root))
    monkeypatch.setattr(sentry, "CONTROL_API_URL", f"{root}/control/api/0")
    fake.route("/control/api/0/organizations/",
               (200, [{"slug": "acme", "links": {"regionUrl": "https://evil.example"}}], {}))
    orgs = list_sentry_organizations("tok", base_url=fake.base)
    assert orgs[0]["region"] == fake.base.rstrip("/")


def test_region_lookup_failure_falls_back_to_base(fake, monkeypatch):
    root = fake.base[: -len("/api/0/")]
    monkeypatch.setattr(sentry, "_org_region", {})
    monkeypatch.setattr(sentry, "_is_saas", lambda url: url.startswith(root))
    monkeypatch.setattr(sentry, "CONTROL_API_URL", f"{root}/control/api/0")
    fake.route("/control/api/0/organizations/", (401, {"detail": "no"}, {}))
    fake.route("/api/0/organizations/acme/projects/", (200, [{"slug": "web"}], {}))
    assert [p["slug"] for p in list_sentry_projects("acme", "tok", base_url=fake.base)] == ["web"]


# ── Event samples and stack-trace context ───────────────────────────────────

def _eid(n):
    return f"{n:032x}"


def test_samples_keep_newest_events_per_category_capped(fake, taxonomy):
    events = [dict(_event(i, "DB timeout" if i % 2 else "http 502"), eventID=_eid(i)) for i in range(14)]
    events.append(dict(_event(20), eventID="not-a-sentry-id"))
    fake.route(EVENTS, (200, events, fake.link(EVENTS, "x", results=False)))
    index = {}
    load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base, event_index=index)
    samples = index["samples"]
    assert sorted(samples) == ["Database", "Network"]
    assert len(samples["Database"]) == sentry.SAMPLES_PER_CATEGORY
    assert [r["event_id"] for r in samples["Database"]] == [_eid(i) for i in (13, 11, 9, 7, 5)]  # newest first
    assert samples["Network"][0] == {"project": "web", "event_id": _eid(12), "title": "http 502",
                                     "date": events[12]["dateCreated"]}


FULL_EVENT = {
    "eventID": _eid(7), "groupID": "4242", "title": "TimeoutError: db timeout", "culprit": "orders.repo in fetch",
    "platform": "python", "dateCreated": "2026-01-01T00:00:00Z", "release": {"version": "shop@4.2.0"},
    "tags": [{"key": "environment", "value": "production"}, {"key": "user", "value": "alice@example.com"},
             {"key": "url", "value": "https://shop/checkout?card=4111"}, {"key": "level", "value": "error"}],
    "entries": [
        {"type": "request", "data": {"data": {"password": "hunter2"}}},
        {"type": "exception", "data": {"values": [
            {"type": "ConnectionError", "value": "refused", "stacktrace": {"frames": [
                {"filename": "socket.py", "function": "connect", "lineNo": 9, "inApp": False}]}},
            {"type": "TimeoutError", "value": "db timeout", "stacktrace": {"frames": [
                {"filename": "site-packages/sqlalchemy/pool.py", "function": "_do_get", "lineNo": 300, "inApp": False},
                {"filename": "app/main.py", "function": "handler", "lineNo": 12, "inApp": True,
                 "context": [[11, "def handler():"], [12, "    return repo.fetch()"]], "vars": {"secret": "x"}},
                {"filename": "app/orders/repo.py", "function": "fetch", "lineNo": 40, "inApp": True,
                 "context": [[40, "    rows = db.execute(QUERY)"]], "vars": {"token": "y"}},
            ]}},
        ]}},
    ],
}


def test_summarize_event_keeps_debug_context_and_drops_personal_data():
    out = summarize_event(FULL_EVENT, "acme", "https://de.sentry.io/api/0")
    raised = out["exceptions"][-1]
    assert raised["type"] == "TimeoutError"
    assert [f["file"] for f in raised["frames"]] == ["app/orders/repo.py", "app/main.py"]  # own code, crash site first
    assert raised["frames"][0] == {"file": "app/orders/repo.py", "function": "fetch", "line": 40,
                                   "code": "    rows = db.execute(QUERY)", "in_app": True}
    assert out["exceptions"][0]["frames"][0]["file"] == "socket.py"  # no own frames: falls back to library frames
    assert out["release"] == "shop@4.2.0" and out["environment"] == "production"
    assert out["tags"] == {"environment": "production", "level": "error"}
    assert out["sentry_url"] == f"https://acme.sentry.io/issues/4242/events/{_eid(7)}/"
    text = json.dumps(out)
    for secret in ("hunter2", "alice@example.com", "4111", '"secret"', '"token"', "vars"):
        assert secret not in text


def test_summarize_event_no_sentry_link_for_self_hosted():
    assert summarize_event(FULL_EVENT, "acme", "https://sentry.internal/api/0")["sentry_url"] is None


def test_get_event_context_fetches_one_event(fake):
    path = f"/api/0/projects/acme/web/events/{_eid(7)}/"
    fake.route(path, (200, FULL_EVENT, {}))
    out = get_event_context("acme", "web", _eid(7), "tok", base_url=fake.base)
    assert out["title"] == "TimeoutError: db timeout"
    assert fake.requests[-1][0] == path and fake.requests[-1][2] == "Bearer tok"


def test_get_event_context_validates_input_and_shape(fake):
    with pytest.raises(SentryError, match="Invalid event id"):
        get_event_context("acme", "web", "../../etc", "tok", base_url=fake.base)
    path = f"/api/0/projects/acme/web/events/{_eid(1)}/"
    fake.route(path, (200, [1, 2], {}))
    with pytest.raises(SentryError, match="JSON object"):
        get_event_context("acme", "web", _eid(1), "tok", base_url=fake.base)


# ── Issues, ignore rules and richer descriptions (2.15) ─────────────────────

def test_synthetic_title_and_html_error_page_get_a_useful_description():
    ev = {"title": "processDueCampaigns", "location": "/app/dist/jobs/campaign-scheduler.js",
          "metadata": {"synthetic": True, "type": "Error", "function": "processDueCampaigns",
                       "value": "<!DOCTYPE html>\n<html>..."}}
    desc = sentry._event_description(ev)
    assert desc == ("Error in processDueCampaigns (/app/dist/jobs/campaign-scheduler.js) "
                    "[upstream HTTP response was an HTML error page]")
    plain = {"title": "TypeError: x is undefined", "metadata": {"type": "TypeError", "value": "x is undefined"}}
    assert sentry._event_description(plain) == "TypeError: x is undefined"


def test_ignore_rule_wins_whatever_its_position(tmp_path):
    cats = [("Network", {"http", "cors"}), ("Ignore", {"miner.invalid"})]
    assert sentry.is_ignored("CORS: origin http://miner.invalid not allowed", cats)
    assert not sentry.is_ignored("CORS: origin https://api.example.com not allowed", cats)


def _issue_event(i, gid, title, hours=0):
    return dict(_event(hours if hours else i, title), eventID=_eid(i), groupID=gid,
                culprit=f"{title} culprit", location="/app/x.js")


def test_index_ranks_issues_flags_bursts_and_drops_ignored(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("SENTRY_BASE_URL", "https://sentry.io/api/0/")
    taxonomy = tmp_path / "t.conf"
    taxonomy.write_text("Network [cors, http]\nIgnore [miner.invalid]\nGeneral Error [error]\n")
    burst = [_issue_event(i, "1", "Error: Invariant failed", hours=100 + i * 0.1) for i in range(25)]
    spread = [_issue_event(100 + i, "2", "CORS: origin https://api.acme.co not allowed", hours=i * 20) for i in range(5)]
    noise = [_issue_event(200 + i, "3", "CORS: origin http://miner.invalid not allowed") for i in range(3)]
    fake.route(EVENTS, (200, burst + spread + noise, fake.link(EVENTS, "x", results=False)))
    index = {}
    t, cat_list, *_ = load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base, event_index=index)
    assert len(t) == 30  # the 3 ignored events are not in the timeline
    out = sentry.finalize_event_index(index, "acme", base_url="https://sentry.io/api/0/")
    assert [(i["group_id"], i["count"], i["burst"]) for i in out["issues"]] == [("1", 25, True), ("2", 5, False)]
    first = out["issues"][0]
    assert first["category"] == "General Error" and first["culprit"] == "Error: Invariant failed culprit"
    assert first["sentry_url"] == "https://acme.sentry.io/issues/1/" and "_times" not in first
    assert first["first_seen"] < first["last_seen"]
    assert out["ignored"] == {"count": 3, "top_titles": [{"title": "CORS: origin http://miner.invalid not allowed",
                                                          "count": 3}]}
    assert "3" not in {i["group_id"] for i in out["issues"]}


def test_issue_url_only_for_sentry_io():
    assert sentry.issue_url("acme", "42", "https://de.sentry.io/api/0/") == "https://acme.sentry.io/issues/42/"
    assert sentry.issue_url("acme", "42", "https://sentry.internal/api/0/") is None
    assert sentry.issue_url("acme", "x42", "https://sentry.io/api/0/") is None


def test_issue_title_is_its_most_common_variant(fake, taxonomy):
    events = ([_issue_event(i, "7", "CORS: origin https://api.acme.co not allowed", hours=i) for i in range(5)]
              + [_issue_event(10, "7", "CORS: origin http://bot.example not allowed", hours=50)])  # newest
    fake.route(EVENTS, (200, events, fake.link(EVENTS, "x", results=False)))
    index = {}
    load_sentry_failures("acme", "web", "tok", taxonomy, base_url=fake.base, event_index=index)
    issue = sentry.finalize_event_index(index, "acme")["issues"][0]
    assert issue["title"] == "CORS: origin https://api.acme.co not allowed" and issue["count"] == 6
    assert "_titles" not in issue
