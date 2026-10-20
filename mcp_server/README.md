# Reliability Modeler MCP server

Feeds Sentry-derived failure data and reliability analyses to any MCP client (Claude Code, Codex, Yodaman, Claude Desktop, ...) over stdio.

It is a thin client of the running stack. Every call goes through the UI proxy (or straight to the API), so auth, validation and storage are unchanged. The stack must be running (`docker compose up -d`).

## Tools

| Tool | What it returns |
|------|-----------------|
| `list_analyses(limit, offset)` | Archived runs, newest first: ID, date, source, total failures, duration |
| `get_trends()` | MTBF / failure-rate trend per source (`groups`): improving, stable or degrading |
| `list_sentry_organizations()` | Every Sentry organization the token can see, across US and EU regions |
| `list_keystone_failures(analysis_id, limit)` | Categories ranked by PageRank with keystone/bridge flags (default: newest analysis) |
| `get_analysis_brief(analysis_id)` | One call: failures, MTBF, best model, trend, top issues, keystones, warnings, next steps (default: newest analysis). Start here |
| `list_top_issues(analysis_id, limit)` | Sentry issues ranked by events: share, culprit, location, burst flag, Sentry link |
| `get_issue_context(group_id, analysis_id)` | Stack trace of an issue's latest event: exception, top frames with file/function/line/code |
| `get_failure_context(category, analysis_id, limit)` | Stack traces behind a category: exception, culprit, release, top frames (file, function, line, code), Sentry link |
| `list_sentry_projects(org)` | Sentry projects in an organization |
| `run_analysis(org, project, days, future_hours)` | Pulls 1–90 days of Sentry events and fits models (up to ~4 min). `truncated: true` means a project hit the per-project event cap |
| `graphql(query)` | Failure graph, keystone categories and cascade chains per analysis (read-only schema) |

Plots (base64 PNG) and the raw graph dump are stripped from results to keep agent context small.

## Setup

```bash
python3 -m venv mcp_server/.venv
mcp_server/.venv/bin/pip install -r mcp_server/requirements.txt
```

## Credentials

By default the server calls `http://localhost:${UI_PORT:-3000}/api` (the local UI proxy; `UI_PORT` is read from the environment or the repo's `.env`) and reads `UI_USERNAME` / `UI_PASSWORD` from the repo's `.env`, so no secret goes in an agent's config. Overrides:

| Env | Use |
|-----|-----|
| `RM_URL` | Another deployment, e.g. `https://rm.internal/api`. When set, the repo `.env` login is **not** used: pass `RM_USERNAME` / `RM_PASSWORD` for that deployment |
| `RM_USERNAME`, `RM_PASSWORD` | UI login for `RM_URL`, or when there's no repo `.env` |
| `RM_API_KEY` | Call the API directly with `X-API-Key` (set `RM_URL=http://api:8000`). Only works from inside the compose network: `docker-compose.yml` does not publish the API port to the host |

## Register with a client

Run these from the repo root. The Claude Code command works as pasted; in the config files, replace `<repo>` with the output of `pwd` (an absolute path, without the angle brackets).

**Claude Code**

```bash
claude mcp add reliability-modeler --scope user -- "$(pwd)/mcp_server/.venv/bin/python" "$(pwd)/mcp_server/server.py"
```

**Codex**: add to `~/.codex/config.toml`:

```toml
[mcp_servers.reliability-modeler]
command = "<repo>/mcp_server/.venv/bin/python"
args = ["<repo>/mcp_server/server.py"]
```

**Yodaman, Claude Desktop, or any other MCP client**: register a stdio server with the same command and args. For JSON-config clients:

```json
{
  "mcpServers": {
    "reliability-modeler": {
      "command": "<repo>/mcp_server/.venv/bin/python",
      "args": ["<repo>/mcp_server/server.py"]
    }
  }
}
```

## Test

```bash
cd mcp_server && .venv/bin/pip install pytest==9.1.1 && .venv/bin/python -m pytest -q test_server.py
```
