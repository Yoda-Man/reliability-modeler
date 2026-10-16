import json
import os

os.environ.update({"RM_URL": "http://rm.test/api", "RM_API_KEY": "k"})

import httpx2 as httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server


def _use(handler):
    server.client = httpx.Client(base_url="http://rm.test/api", headers={"X-API-Key": "k"},
                                 transport=httpx.MockTransport(handler))


def test_run_analysis_strips_heavy_fields_and_sends_payload():
    seen = {}

    def handler(req):
        seen["path"], seen["key"], seen["body"] = req.url.path, req.headers["x-api-key"], json.loads(req.content)
        return httpx.Response(200, json={"id": "AN-1", "plots": {"r": "b64"},
                                         "graph_report": {"graph_json": {}, "num_communities": 2}})

    _use(handler)
    out = server.run_analysis("acme", "web", days=7, future_hours=2500)
    assert seen == {"path": "/api/ingest/sentry", "key": "k",
                    "body": {"org": "acme", "project": "web", "days": 7, "future_hours": 2500}}
    assert out == {"id": "AN-1", "graph_report": {"num_communities": 2}}


def test_api_error_detail_reaches_agent():
    _use(lambda req: httpx.Response(503, json={"detail": "SENTRY_AUTH_TOKEN not configured"}))
    with pytest.raises(ToolError, match="HTTP 503: SENTRY_AUTH_TOKEN not configured"):
        server.list_sentry_projects("acme")


def test_unreachable_server_is_a_tool_error():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    _use(handler)
    with pytest.raises(ToolError, match="unreachable"):
        server.get_trends()


def _dotenv_file(tmp_path, monkeypatch, text):
    (tmp_path / ".env").write_text(text)
    monkeypatch.setattr(server, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("RM_API_KEY")


def test_basic_auth_from_dotenv_for_local_stack(tmp_path, monkeypatch):
    _dotenv_file(tmp_path, monkeypatch, "# c\nUI_USERNAME=admin\nUI_PASSWORD='s3cret'\n")
    monkeypatch.delenv("RM_URL")
    c = server.make_client()
    req = c.build_request("GET", "/logs")
    assert req.url == "http://localhost:3000/api/logs"
    assert "x-api-key" not in req.headers
    assert c.auth is not None


def test_dotenv_ui_login_never_sent_to_rm_url(tmp_path, monkeypatch):
    _dotenv_file(tmp_path, monkeypatch, "UI_USERNAME=admin\nUI_PASSWORD=s3cret\n")
    assert server.make_client().auth is None
    monkeypatch.setenv("RM_PASSWORD", "remote")
    assert server.make_client().auth is not None


def test_default_url_honours_ui_port(tmp_path, monkeypatch):
    _dotenv_file(tmp_path, monkeypatch, "UI_PORT=3100  # host port\n")
    monkeypatch.delenv("RM_URL")
    assert str(server.make_client().base_url) == "http://localhost:3100/api/"
    monkeypatch.setenv("UI_PORT", "8080")
    assert str(server.make_client().base_url) == "http://localhost:8080/api/"


def test_dotenv_inline_comments_like_compose(tmp_path):
    (tmp_path / ".env").write_text(
        "A=plain # comment\nB='p#q' # c\nC=\"x # y\"\nD=a#b\nE= # empty\n")
    assert server._dotenv(tmp_path / ".env") == {"A": "plain", "B": "p#q", "C": "x # y", "D": "a#b", "E": ""}
