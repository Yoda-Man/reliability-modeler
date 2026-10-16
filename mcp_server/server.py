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
        "list_analyses or get_trends for existing data; run_analysis pulls fresh events "
        "(slow, up to ~4 min). Use graphql for failure graphs, keystone categories and "
        "cascade chains of a specific analysis ID."
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


if __name__ == "__main__":
    mcp.run()
