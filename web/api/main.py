import os
import sys
import uuid
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import base64
import json
import time
import html as _html
import secrets

import asyncio

# Add the app directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append("/app")

from modeler.data import categorize_description, load_fault_categories
from modeler.models import fit_model, go_mu, mo_mu, go_intensity, mo_intensity
from modeler.plots import plot_reliability_growth, plot_failure_intensity, plot_categories
from modeler.graphs import build_failure_graphs, generate_graph_insights
from modeler.sentry import load_sentry_failures, load_sentry_failures_all, list_sentry_projects, SentryError
try:
    from .graphql_schema import schema, store_analysis_data
except ImportError:
    from graphql_schema import schema, store_analysis_data

# Define base directory for relative path resolution
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S',
)
logger = logging.getLogger("api")

app = FastAPI(title="Reliability Modeler API", version="2.7.2")


# ── Startup config persistence check ─────────────────────────────────────────
def _warn_ephemeral_storage():
    """Log a warning if config files are on potentially ephemeral storage."""
    config_path = ROOT_DIR / "fault_categories.conf"
    settings_path = BASE_DIR / "settings.json"
    for path, name in [(config_path, "fault_categories.conf"), (settings_path, "settings.json")]:
        parent = path.parent
        if not any(parent.iterdir()):
            continue  # parent doesn't exist yet, will be created
        # Check if parent is a known ephemeral location
        ephemeral_markers = ["/tmp", "/var/tmp", "temp_"]
        if any(m in str(parent) for m in ephemeral_markers):
            logger.warning(f"⚠️  {name} is on ephemeral storage ({parent}). "
                           f"Config changes will be LOST on container restart. "
                           f"Mount a persistent volume at {parent}.")


_warn_ephemeral_storage()


# ── Startup: prune logs older than 90 days ───────────────────────────────────
def _prune_logs_on_startup():
    log_dir = ROOT_DIR / "output" / "logs"
    if not log_dir.exists():
        return
    cutoff = datetime.now().timestamp() - (90 * 86400)
    pruned = 0
    for log_file in log_dir.glob("*.json"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                pruned += 1
        except Exception:
            pass
    if pruned > 0:
        logger.info(f"Startup: pruned {pruned} log files older than 90 days")


_prune_logs_on_startup()


# ── CORS ────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── API Key from env (used by UI via NEXT_PUBLIC_ var passthrough) ───────────
API_KEY = os.getenv("RELIABILITY_API_KEY", "")
AUTH_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json"}
_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "120"))

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if not API_KEY:
        return await call_next(request)  # auth disabled if no key configured
    if request.url.path in AUTH_EXEMPT_PATHS or request.url.path.startswith("/health"):
        return await call_next(request)
    if request.method == "GET":
        return await call_next(request)  # GET is read-only, safe without auth
    provided = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(provided, API_KEY):
        logger.warning(f"Auth failed for {request.client.host if request.client else 'unknown'} on {request.method} {request.url.path}")
        return JSONResponse(status_code=401, content={"error": "Invalid or missing API key"})
    return await call_next(request)


# ── Rate Limiting (simple in-memory) ─────────────────────────────────────────
_rate_limit_store: dict[str, list] = {}
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = [t for t in _rate_limit_store.get(client_ip, []) if t > window_start]
    if len(timestamps) >= RATE_LIMIT_MAX:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(status_code=429, content={"error": "Too many requests", "retry_after": RATE_LIMIT_WINDOW})
    timestamps.append(now)
    _rate_limit_store[client_ip] = timestamps
    # Prune expired entries periodically (keep only clients with recent activity)
    if len(_rate_limit_store) > 500:
        cutoff = now - (RATE_LIMIT_WINDOW * 2)
        stale = [ip for ip, ts_list in _rate_limit_store.items()
                  if not any(t > cutoff for t in ts_list)]
        for ip in stale:
            del _rate_limit_store[ip]
    response = await call_next(request)
    return response

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    request.state.req_id = req_id
    logger.info(f"[{req_id}] {request.method} {request.url.path}")
    start = time.time()
    response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000
    logger.info(f"[{req_id}] {response.status_code} {elapsed_ms:.0f}ms")
    response.headers["X-Request-ID"] = req_id
    return response

VALID_OPTIMIZATION_METHODS = {"L-BFGS-B", "TNC", "SLSQP", "Nelder-Mead"}
MIN_FUTURE_HOURS = 1
MAX_FUTURE_HOURS = 100000

class Settings(BaseModel):
    multi_label: bool = False
    optimization_method: str = "TNC"
    tolerance: float = 1e-6

def load_persistent_settings() -> Settings:
    settings_path = BASE_DIR / "settings.json"
    if settings_path.exists():
        with open(settings_path, "r") as f:
            return Settings(**json.load(f))
    return Settings()

def save_to_archive(log_id, filename, summary):
    log_dir = ROOT_DIR / "output" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": log_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "file": filename,
        "status": "Completed",
        "summary": summary
    }
    tmp_path = log_dir / f".{log_id}.tmp"
    final_path = log_dir / f"{log_id}.json"
    with open(tmp_path, "w") as f:
        json.dump(entry, f)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(final_path)  # atomic on same filesystem

@app.get("/logs")
async def get_logs(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, min(offset, 10000))
    log_dir = ROOT_DIR / "output" / "logs"
    if not log_dir.exists():
        return {"total": 0, "logs": []}
    
    all_logs = []
    for log_file in log_dir.glob("*.json"):
        try:
            with open(log_file, "r") as f:
                all_logs.append(json.load(f))
        except Exception:
            continue
    
    all_logs.sort(key=lambda x: x.get('date', ''), reverse=True)
    total = len(all_logs)
    page = all_logs[offset:offset + limit]
    
    return {"total": total, "logs": page}


@app.post("/logs/prune")
async def prune_logs(retention_days: int = 90):
    """Delete log archives older than `retention_days` days. Default 90."""
    log_dir = ROOT_DIR / "output" / "logs"
    if not log_dir.exists():
        return {"pruned": 0, "message": "No log directory found"}
    
    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    pruned = 0
    for log_file in log_dir.glob("*.json"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                pruned += 1
        except Exception:
            continue
    
    logger.info(f"Pruned {pruned} log files older than {retention_days} days")
    return {"pruned": pruned, "message": f"Removed {pruned} log(s) older than {retention_days} days"}


@app.get("/trends")
async def get_trends():
    """
    Compare MTBF, failure rate, and total failures across all archived analysis runs.
    Returns time-series data suitable for trend-line charts.
    """
    log_dir = ROOT_DIR / "output" / "logs"
    if not log_dir.exists():
        return {"runs": [], "trend": "insufficient_data"}

    runs = []
    for log_file in sorted(log_dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            with open(log_file, "r") as f:
                entry = json.load(f)
        except Exception:
            continue
        summary = entry.get("summary", {})
        tf = summary.get("total_failures", 0)
        dh = summary.get("duration_hours", 0)
        if tf > 0 and dh > 0:
            runs.append({
                "id": entry.get("id", log_file.stem),
                "date": entry.get("date", ""),
                "file": entry.get("file", ""),
                "total_failures": tf,
                "duration_hours": round(dh, 2),
                "mtbf_hours": round(dh / tf, 4),
                "failure_rate_per_hour": round(tf / dh, 4),
            })

    if len(runs) < 2:
        return {"runs": runs, "trend": "insufficient_data" if len(runs) == 0 else "single_run"}

    # Compute trend direction for MTBF
    first_mtbf = runs[0]["mtbf_hours"]
    last_mtbf = runs[-1]["mtbf_hours"]
    if last_mtbf > first_mtbf * 1.05:
        trend = "improving"
    elif last_mtbf < first_mtbf * 0.95:
        trend = "degrading"
    else:
        trend = "stable"

    # Compute % change
    mtbf_change_pct = round((last_mtbf - first_mtbf) / max(0.001, first_mtbf) * 100, 1)
    rate_change_pct = round((runs[-1]["failure_rate_per_hour"] - runs[0]["failure_rate_per_hour"])
                             / max(0.001, runs[0]["failure_rate_per_hour"]) * 100, 1)

    return {
        "runs": runs,
        "trend": trend,
        "mtbf_change_pct": mtbf_change_pct,
        "rate_change_pct": rate_change_pct,
        "num_runs": len(runs),
    }


@app.get("/report/{analysis_id}/html")
async def get_html_report(analysis_id: str):
    """
    Generate a self-contained, print-ready HTML executive report for an analysis run.
    This file can be saved and emailed by any external scheduler (cron, CI, etc.).
    """
    # Sanitize: reject path traversal attempts
    if '..' in analysis_id or '/' in analysis_id or '\\' in analysis_id:
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    log_dir = ROOT_DIR / "output" / "logs"
    log_path = log_dir / f"{analysis_id}.json"
    # Resolve and verify the path stays inside log_dir
    resolved = log_path.resolve()
    if not str(resolved).startswith(str(log_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid analysis ID")
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    with open(log_path, "r") as f:
        entry = json.load(f)

    summary = entry.get("summary", {})
    tf = summary.get("total_failures", 0)
    dh = summary.get("duration_hours", 0)
    mtbf = round(dh / max(1, tf), 2)
    failure_rate = round(tf / max(0.01, dh), 2)
    safe_file = _html.escape(entry.get('file', 'N/A'))
    safe_date = _html.escape(entry.get('date', 'N/A'))
    safe_id = _html.escape(analysis_id)

    # Find any plots for this run
    plot_dir = ROOT_DIR / "temp_plots"
    reliability_b64 = ""
    if plot_dir.exists():
        for png in sorted(plot_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
            with open(png, "rb") as pf:
                reliability_b64 = base64.b64encode(pf.read()).decode("utf-8")
            break

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reliability Executive Report — {analysis_id}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; color: #1e293b; max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
  .header {{ border-bottom: 3px solid #3b82f6; padding-bottom: 16px; margin-bottom: 32px; }}
  .header h1 {{ font-size: 24px; color: #0f172a; }}
  .header .meta {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
  .kpi {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; text-align: center; }}
  .kpi .value {{ font-size: 28px; font-weight: 700; color: #0f172a; }}
  .kpi .label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
  .section {{ margin-bottom: 32px; }}
  .section h2 {{ font-size: 16px; color: #334155; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 16px; }}
  .section p {{ font-size: 13px; line-height: 1.7; color: #475569; }}
  .chart-container {{ text-align: center; }}
  .chart-container img {{ max-width: 100%; border-radius: 8px; border: 1px solid #e2e8f0; }}
  .footer {{ border-top: 1px solid #e2e8f0; padding-top: 16px; font-size: 11px; color: #94a3b8; text-align: center; }}
  @media print {{ body {{ padding: 20px; }} .kpi-grid {{ grid-template-columns: repeat(4, 1fr); }} }}
</style>
</head>
<body>
<div class="header">
  <h1>🔬 Reliability Executive Report</h1>
  <p class="meta">Analysis ID: {safe_id} &middot; File: {safe_file} &middot; Date: {safe_date}</p>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="value">{tf}</div><div class="label">Total Failures</div></div>
  <div class="kpi"><div class="value">{mtbf}h</div><div class="label">MTBF</div></div>
  <div class="kpi"><div class="value">{failure_rate}/h</div><div class="label">Failure Rate</div></div>
  <div class="kpi"><div class="value">{dh}h</div><div class="label">Duration</div></div>
</div>

<div class="section">
  <h2>Executive Summary</h2>
  <p>
    This report presents the results of a software reliability growth analysis
    conducted on <strong>{dh:.1f} hours</strong> of failure data containing
    <strong>{tf} incidents</strong>. The Mean Time Between Failures (MTBF) is
    <strong>{mtbf} hours</strong> with a failure rate of
    <strong>{failure_rate} failures per hour</strong>.
  </p>
  <p style="margin-top: 12px;">
    This report was generated by the Reliability Modeler — an internal-use tool
    for software quality engineering. For operational questions, refer to the
    <code>SUPPORT.md</code> runbook in the project repository.
  </p>
</div>

{f'''<div class="section">
  <h2>Reliability Growth Chart</h2>
  <div class="chart-container">
    <img src="data:image/png;base64,{reliability_b64}" alt="Reliability Growth" />
  </div>
</div>''' if reliability_b64 else ''}

<div class="footer">
  Reliability Modeler &middot; Internal Use Only &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC
</div>
</body>
</html>"""

    return {"html": html, "analysis_id": analysis_id}


@app.get("/config")
async def get_config():
    # Priority: Local ROOT_DIR config, then Docker-style /app config
    config_path = ROOT_DIR / "fault_categories.conf"
    if not config_path.exists():
        config_path = Path("/app/fault_categories.conf")
    
    if config_path.exists():
        with open(config_path, "r") as f:
            content = f.read()
        return {"content": content, "settings": load_persistent_settings()}
    return {"content": "", "settings": load_persistent_settings()}

def _validate_taxonomy(content: str) -> bool:
    """Basic validation: each non-comment, non-empty line must have Category[keywords] format."""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '[' not in stripped or ']' not in stripped:
            return False
    return True

@app.post("/config")
async def save_config(data: dict):
    if "content" in data:
        if not _validate_taxonomy(data["content"]):
            raise HTTPException(status_code=400, detail="Invalid taxonomy format. Each line must be: Category [keyword1, keyword2]")
        config_path = ROOT_DIR / "fault_categories.conf"
        try:
            with open(config_path, "w") as f:
                f.write(data["content"])
                f.flush()
                os.fsync(f.fileno())
            logger.info(f"Config updated: {config_path}")
        except IOError as e:
            logger.error(f"Failed to write config: {e}")
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    
    if "settings" in data:
        settings_data = data["settings"]
        if "optimization_method" in settings_data:
            if settings_data["optimization_method"] not in VALID_OPTIMIZATION_METHODS:
                raise HTTPException(status_code=400, detail=f"Invalid optimization method. Choose from: {', '.join(sorted(VALID_OPTIMIZATION_METHODS))}")
        try:
            tmp_path = BASE_DIR / ".settings.json.tmp"
            with open(tmp_path, "w") as f:
                json.dump(settings_data, f)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(BASE_DIR / "settings.json")
            logger.info("Settings updated")
        except IOError as e:
            logger.error(f"Failed to write settings: {e}")
            raise HTTPException(status_code=500, detail="Failed to save settings")
            
    return {"status": "success"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.7.2", "timestamp": datetime.now().isoformat()}

def _compute_aic(ll: float, k: int) -> float:
    """Shared AIC calculation: AIC = 2k - 2ln(L)"""
    return 2 * k - 2 * ll

async def _analyze_from_data(t, categorized, t0, filename: str, future_hours: float):
    """Core analysis: fit models, build plots, archive, and graph — from already-normalized data."""
    try:
        settings = load_persistent_settings()
        if settings.optimization_method not in VALID_OPTIMIZATION_METHODS:
            settings.optimization_method = "L-BFGS-B"

        # 2. Fit models
        T = float(t[-1])
        n = len(t)
        tt = np.linspace(0, T + future_hours, 200)
        
        results_list = []
        curves = {}
        curves_intensity = {}
        fit_data = {}

        for m in ['go', 'mo']:
            try:
                params, ll, se, total_exp = fit_model(t, T, model_name=m, method=settings.optimization_method, tol=settings.tolerance)
            except Exception as model_err:
                logger.error(f"Model fitting failed for {m}: {model_err}")
                continue
            if params is None:
                logger.warning(f"Model {m} failed to converge")
                continue
                
            name = "Goel-Okumoto" if m == 'go' else "Musa-Okumoto"
            
            mu = go_mu(tt, params) if m == 'go' else mo_mu(tt, params)
            intensity = go_intensity(tt, params) if m == 'go' else mo_intensity(tt, params)
            
            curves[m] = mu
            curves_intensity[m] = intensity
            
            # For plot_reliability_growth which expects specific results dict
            fit_data[m] = (params, ll, se, name) 

            param_map = {}
            if m == 'go':
                param_map = {"a": float(params[0]), "b": float(params[1])}
            else:
                param_map = {"lambda0": float(params[0]), "theta": float(params[1])}

            k = len(params)
            aic = _compute_aic(ll, k)

            results_list.append({
                "id": m,
                "name": name,
                "aic": round(aic, 4),
                "total_expected_failures": round(float(total_exp), 2) if total_exp is not None else None,
                "parameters": param_map
            })

        # 3. Plots
        plots_b64 = {}
        temp_plots = ROOT_DIR / "temp_plots"
        temp_plots.mkdir(exist_ok=True)
        prefix = str(temp_plots / f"plot_{datetime.now().strftime('%H%M%S')}")

        rel_plot = plot_reliability_growth(t, n, curves, fit_data, None, tt, prefix)
        intensity_plot = plot_failure_intensity(tt, curves_intensity, None, prefix)
        cat_plot = plot_categories(categorized, prefix)

        for name, path in [("reliability", rel_plot), ("intensity", intensity_plot), ("categories", cat_plot)]:
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    plots_b64[name] = base64.b64encode(f.read()).decode('utf-8')
                os.remove(path)

        # 4. Save to archive
        log_id = f"AN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        save_to_archive(log_id, filename, {
            "total_failures": n,
            "duration_hours": round(T, 2)
        })

        # Store categorized data for GraphQL graph queries
        store_analysis_data(log_id, categorized)

        # 5. Build graph analytics (non-blocking — returns None if networkx missing)
        graph_report = build_failure_graphs(categorized)
        graph_insights = generate_graph_insights(graph_report) if graph_report else []
        graph_summary = None
        if graph_report:
            graph_summary = {
                "keystone_categories": [
                    {"name": c.node, "pagerank": c.pagerank, "is_bridge": c.is_bridge}
                    for c in graph_report.centrality if c.is_keystone
                ],
                "top_cascade": (
                    {"chain": " → ".join(graph_report.cascade_chains[0].chain),
                     "confidence": graph_report.cascade_chains[0].confidence}
                    if graph_report.cascade_chains else None
                ),
                "num_communities": graph_report.metrics.num_communities,
                "graph_density": graph_report.metrics.graph_density,
                "graph_json": graph_report.graph_json,
            }

        return {
            "id": log_id,
            "summary": {
                "total_failures": n,
                "duration_hours": round(T, 2),
                "start_time": t0.isoformat() if hasattr(t0, 'isoformat') else str(t0)
            },
            "models": results_list,
            "plots": plots_b64,
            "categorized_failures": categorized[:100],
            "graph_insights": graph_insights,
            "graph_report": graph_summary,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis failed. Please check your data and try again.")

@app.post("/ingest/sentry")
async def ingest_sentry(payload: dict):
    """
    Pull failure events from Sentry and run the reliability analysis.

    Body:
        {"org": "my-org", "project": "my-project", "days": 30, "future_hours": 1000}
        {"org": "my-org", "project": "all", "days": 30, "future_hours": 1000}   # aggregate all projects

    Requires SENTRY_AUTH_TOKEN env var to be set on the API server.
    """
    org = payload.get("org")
    project = payload.get("project")
    if not org:
        raise HTTPException(status_code=400, detail="'org' is required")
    if not project:
        raise HTTPException(status_code=400, detail="'project' is required (use 'all' to aggregate every project)")

    auth_token = os.getenv("SENTRY_AUTH_TOKEN", "")
    if not auth_token:
        raise HTTPException(status_code=503, detail="SENTRY_AUTH_TOKEN not configured on the API server")

    days = int(payload.get("days", 30))
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="'days' must be between 1 and 365")

    future_hours = float(payload.get("future_hours", 1000.0))
    if not np.isfinite(future_hours) or future_hours < MIN_FUTURE_HOURS or future_hours > MAX_FUTURE_HOURS:
        raise HTTPException(status_code=400, detail=f"future_hours must be between {MIN_FUTURE_HOURS} and {MAX_FUTURE_HOURS}")

    config_path = ROOT_DIR / "fault_categories.conf"
    if not config_path.exists():
        config_path = Path("/app/fault_categories.conf")

    project_counts = {}
    try:
        if project == "all":
            t, categorized, t0, _, project_counts = await asyncio.to_thread(
                load_sentry_failures_all,
                org, auth_token, config_path, days,
                load_persistent_settings().multi_label,
            )
            display_name = f"sentry://{org}/ALL_PROJECTS ({days}d)"
        else:
            t, categorized, t0, _ = await asyncio.to_thread(
                load_sentry_failures,
                org, project, auth_token, config_path, days,
                load_persistent_settings().multi_label,
            )
            display_name = f"sentry://{org}/{project} ({days}d)"
    except SentryError as e:
        logger.error(f"Sentry ingest failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    if len(t) == 0:
        raise HTTPException(status_code=400, detail=f"No failure events found in Sentry for {org}/{project} in the last {days} days")

    result = await asyncio.wait_for(
        _analyze_from_data(t, categorized, t0, display_name, future_hours),
        timeout=_ANALYSIS_TIMEOUT_SECONDS
    )

    # Attach per-project breakdown when aggregating all projects
    if project_counts:
        result["projects"] = dict(sorted(project_counts.items(), key=lambda kv: kv[1], reverse=True))
    return result


@app.get("/ingest/sentry/projects")
async def list_sentry_projects_endpoint(org: str):
    """
    List all projects in a Sentry organization. Returns [{slug, name, platform}, ...].
    Requires SENTRY_AUTH_TOKEN env var.
    """
    if not org:
        raise HTTPException(status_code=400, detail="'org' query parameter is required")
    auth_token = os.getenv("SENTRY_AUTH_TOKEN", "")
    if not auth_token:
        raise HTTPException(status_code=503, detail="SENTRY_AUTH_TOKEN not configured on the API server")
    try:
        projects = await asyncio.to_thread(list_sentry_projects, org, auth_token)
    except SentryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "org": org,
        "count": len(projects),
        "projects": [
            {"slug": p.get("slug", ""), "name": p.get("name", p.get("slug", ""))}
            for p in projects
        ],
    }


@app.post("/graphql")
async def graphql_query(request: Request):
    """GraphQL endpoint for flexible failure graph queries."""
    # Enforce body size limit
    body_bytes = await request.body()
    if len(body_bytes) > 256 * 1024:  # 256 KB max
        raise HTTPException(status_code=413, detail="GraphQL query too large (max 256 KB)")
    try:
        body = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    query_str = body.get("query", "")
    variables = body.get("variables", {})
    
    if not query_str:
        raise HTTPException(status_code=400, detail="Missing 'query' field")

    # Reject introspection queries (schema/type disclosure)
    if "__schema" in query_str or "__type" in query_str:
        raise HTTPException(status_code=403, detail="Introspection is disabled")
    
    try:
        result = schema.execute(query_str, variable_values=variables)
    except Exception as e:
        logger.error(f"GraphQL execution error: {e}")
        raise HTTPException(status_code=500, detail="GraphQL query execution failed")
    
    if result.errors:
        return {"data": result.data, "errors": [str(e) for e in result.errors]}
    
    return {"data": result.data}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
