"""
Reliability Modeler MCP server.

Exposes Sentry-derived failure data and reliability analyses to MCP clients
(Claude Code, Codex, Yodaman, ...) over stdio. It is a thin client of the
running stack: every call goes through the UI proxy (Basic auth) or straight
to the API (X-API-Key), so auth, validation and storage stay in one place.

Env:
  RM_URL       base URL (default http://localhost:${UI_PORT:-3000}/api — the local UI proxy)
  RM_USERNAME  / RM_PASSWORD  UI login. Only when RM_URL is unset does it fall back to
               UI_USERNAME / UI_PASSWORD from the repo .env, so local credentials are never
               sent to another host.
  RM_API_KEY   send X-API-Key instead (only reachable inside the compose network: the API
               port is not published)
"""

import json
import os
import urllib.parse
from pathlib import Path

import httpx2 as httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Keys dropped from analysis results: base64 PNGs and the full graph dump are
# megabytes of tokens an agent cannot use (graph data is available via graphql).
HEAVY_KEYS = {"plots", "graph_json"}


def _unquote(raw: str) -> str:
    """Value as docker compose reads it: quoted values are taken verbatim
    (a '#' inside quotes is kept); unquoted values end at a ' #' comment."""
    v = raw.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        if end != -1:
            return v[1:end]
    for i, ch in enumerate(raw):
        if ch == "#" and i > 0 and raw[i - 1] in " \t":
            return raw[:i].strip()
    return v


def _dotenv(path: Path) -> dict:
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text().splitlines()
             if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): _unquote(v) for k, v in pairs}


def make_client() -> httpx.Client:
    env = {**_dotenv(ENV_FILE), **os.environ}
    headers, auth = {}, None
    url = env.get("RM_URL")
    if env.get("RM_API_KEY"):
        headers["X-API-Key"] = env["RM_API_KEY"]
    else:
        # The repo's UI login is only for the local stack: never send it to RM_URL.
        username = env.get("RM_USERNAME") or (None if url else env.get("UI_USERNAME"))
        password = env.get("RM_PASSWORD") or (None if url else env.get("UI_PASSWORD"))
        if password:
            auth = httpx.BasicAuth(username or "admin", password)
    url = url or f"http://localhost:{env.get('UI_PORT') or 3000}/api"
    # The UI proxy allows up to 250s (Sentry fetch + analysis); wait a bit longer.
    return httpx.Client(base_url=url.rstrip("/"), headers=headers, auth=auth, timeout=260)


client = make_client()


def _call(method: str, path: str, **kwargs):
    try:
        resp = client.request(method, path, **kwargs)
    except httpx.HTTPError as e:
        raise ToolError(f"Reliability Modeler unreachable at {client.base_url}: {e}") from e
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ToolError(f"HTTP {resp.status_code}: {detail}")
    return resp.json()


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in HEAVY_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


mcp = MCPServer(
    "reliability-modeler",
    instructions=(
        "Reliability analyses of production errors pulled from Sentry. Start with "
        "get_analysis_brief (newest analysis by default): verdict, trend, top issues, warnings "
        "and next steps in one call. To fix bugs: list_top_issues, then get_issue_context(group_id) "
        "for the stack trace and code location. run_analysis pulls fresh events (slow, up to ~4 min); "
        "list_sentry_organizations / list_sentry_projects find what to analyse. Category-level views: "
        "list_keystone_failures and get_failure_context(category); graphql for full failure graphs."
    ),
)


@mcp.tool()
def list_analyses(limit: int = 20, offset: int = 0) -> dict:
    """Archived analysis runs, newest first: ID, date, source, total failures and duration. Use graphql for per-run graph detail."""
    return _strip(_call("GET", "/logs", params={"limit": limit, "offset": offset}))


@mcp.tool()
def get_trends() -> dict:
    """MTBF and failure-rate trends grouped per source (`groups`), each with an improving/stable/degrading
    verdict; the top-level trend is for the source of the most recent run."""
    return _call("GET", "/trends")


@mcp.tool()
def list_sentry_organizations() -> dict:
    """Every Sentry organization the configured token can see, across US and EU regions (slug, name, region)."""
    return _call("GET", "/ingest/sentry/organizations")


@mcp.tool()
def list_sentry_projects(org: str) -> dict:
    """Sentry projects available in an organization (slug and name)."""
    return _call("GET", "/ingest/sentry/projects", params={"org": org})


@mcp.tool()
def run_analysis(org: str, project: str, days: int = 30, future_hours: float = 1000) -> dict:
    """Pull the last `days` (1-90) of Sentry error events for a project (or 'all') and fit
    reliability-growth models, forecasting `future_hours` (1-100000) ahead. Returns summary, model fits,
    the most recent categorized failures and graph insights; `truncated: true` means Sentry's event cap was hit."""
    return _strip(_call("POST", "/ingest/sentry",
                        json={"org": org, "project": project, "days": days, "future_hours": future_hours}))


@mcp.tool()
def graphql(query: str) -> dict:
    """Run a read-only GraphQL query. Fields: availableAnalyses, failureGraph(analysisId),
    keystoneCategories(analysisId), cascadeChains(analysisId), keystoneCategoriesAcross(limit).
    Example: { availableAnalyses }"""
    return _call("POST", "/graphql", json={"query": query})


def _analysis_id(analysis_id: str) -> str:
    """Resolve 'latest' to the newest archived analysis."""
    if analysis_id != "latest":
        return analysis_id
    logs = _call("GET", "/logs", params={"limit": 1}).get("logs") or []
    if not logs:
        raise ToolError("No analyses yet: call run_analysis first.")
    return logs[0]["id"]


@mcp.tool()
def list_keystone_failures(analysis_id: str = "latest", limit: int = 10) -> dict:
    """Failure categories of one analysis (default: the newest) ranked by PageRank in the failure
    network. Keystone (top 20%) categories trigger the most downstream failures, so fixing them
    helps most; bridges link otherwise separate failure clusters. Follow up with
    get_failure_context(category) to see the stack traces behind a category."""
    aid = _analysis_id(analysis_id)
    query = ("query($id: String!, $n: Int) { keystoneCategories(analysisId: $id, limit: $n) "
             "{ node pagerank betweenness isKeystone isBridge } }")
    data = _call("POST", "/graphql", json={"query": query, "variables": {"id": aid, "n": limit}})
    if data.get("errors"):
        raise ToolError(f"GraphQL error: {data['errors']}")
    return {"analysis_id": aid, "categories": (data.get("data") or {}).get("keystoneCategories") or []}


@mcp.tool()
def get_failure_context(category: str, analysis_id: str = "latest", limit: int = 3) -> dict:
    """Stack traces for up to `limit` (1-5) recent Sentry events in one failure category of an
    analysis (default: the newest): exception chain with type and message, culprit, release,
    environment, and the top stack frames (file, function, line, code line), with the app's own
    code first, plus a link to the event in Sentry. Use the file/function/line to locate and fix
    the bug. Local variables, request and user data are never included."""
    aid = urllib.parse.quote(_analysis_id(analysis_id), safe="")
    return _call("GET", f"/analyses/{aid}/context", params={"category": category, "limit": limit})


@mcp.tool()
def get_analysis_brief(analysis_id: str = "latest") -> dict:
    """Everything about one analysis (default: the newest) in one call: failures, MTBF, best model and
    expected remaining failures, reliability trend for that source, top 5 issues, keystone categories,
    warnings about data quality, ignored noise, and concrete next steps. Start here."""
    return _call("GET", f"/analyses/{urllib.parse.quote(_analysis_id(analysis_id), safe='')}/brief")


@mcp.tool()
def list_top_issues(analysis_id: str = "latest", limit: int = 10) -> dict:
    """Sentry issues of an analysis ranked by event count: one row per bug, with share of all failures,
    culprit, file location, first/last seen, burst flag and Sentry link. Fix from the top."""
    aid = urllib.parse.quote(_analysis_id(analysis_id), safe="")
    return _call("GET", f"/analyses/{aid}/issues", params={"limit": limit})


@mcp.tool()
def get_issue_context(group_id: str, analysis_id: str = "latest") -> dict:
    """Stack trace of the most recent event of one Sentry issue (group_id from list_top_issues):
    exception type and message, culprit, release, environment and the top stack frames (file, function,
    line, code line, the app's own code first). Local variables and user data are never included."""
    aid = urllib.parse.quote(_analysis_id(analysis_id), safe="")
    return _call("GET", f"/analyses/{aid}/issues/{urllib.parse.quote(group_id, safe='')}/context")


if __name__ == "__main__":
    mcp.run()
