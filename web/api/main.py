import os
import sys
import uuid
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
from pathlib import Path
from datetime import datetime
import base64
import json
import time

# Add the app directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append("/app")

from modeler.data import load_failure_data, categorize_description, load_fault_categories
from modeler.models import fit_model, go_mu, mo_mu, go_intensity, mo_intensity
from modeler.plots import plot_reliability_growth, plot_failure_intensity, plot_categories

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

app = FastAPI(title="Reliability Modeler API", version="2.0.1")

# ── CORS ────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

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

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
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
    with open(log_dir / f"{log_id}.json", "w") as f:
        json.dump(entry, f)

@app.get("/logs")
async def get_logs():
    log_dir = ROOT_DIR / "output" / "logs"
    if not log_dir.exists():
        return []
    
    logs = []
    for log_file in log_dir.glob("*.json"):
        with open(log_file, "r") as f:
            logs.append(json.load(f))
    
    return sorted(logs, key=lambda x: x['date'], reverse=True)

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
            with open(BASE_DIR / "settings.json", "w") as f:
                json.dump(settings_data, f)
            logger.info("Settings updated")
        except IOError as e:
            logger.error(f"Failed to write settings: {e}")
            raise HTTPException(status_code=500, detail="Failed to save settings")
            
    return {"status": "success"}

@app.post("/analyze")
async def analyze_failure_data(
    file: UploadFile = File(...),
    future_hours: float = 1000.0,
):
    # Validate future_hours
    if not np.isfinite(future_hours) or future_hours < MIN_FUTURE_HOURS or future_hours > MAX_FUTURE_HOURS:
        raise HTTPException(status_code=400, detail=f"future_hours must be between {MIN_FUTURE_HOURS} and {MAX_FUTURE_HOURS}")

    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum size of {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Validate MIME type and extension
    if file.content_type and file.content_type not in ("text/csv", "application/csv", "text/plain", "application/octet-stream"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Please upload a CSV file.")

    # Sanitize: use UUID filename to prevent path traversal
    safe_filename = f"{uuid.uuid4().hex}.csv"
    temp_uploads = ROOT_DIR / "temp_uploads"
    temp_uploads.mkdir(exist_ok=True)
    csv_path = temp_uploads / safe_filename
    with open(csv_path, "wb") as f:
        f.write(contents)

    # Quick CSV structure check
    try:
        first_line = contents.split(b'\n', 1)[0].decode('utf-8', errors='replace')
        if ',' not in first_line:
            os.remove(csv_path)
            raise HTTPException(status_code=400, detail="File does not appear to be a valid CSV (no comma separators found)")
    except UnicodeDecodeError:
        os.remove(csv_path)
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")
    
    return await run_analysis_pipeline(csv_path, file.filename or "uploaded.csv", future_hours)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.1", "timestamp": datetime.now().isoformat()}

@app.get("/sample-data")
async def analyze_sample_data():
    sample_path = BASE_DIR / "sample_data.csv"
    if not sample_path.exists():
        sample_path = Path("/app/sample_data.csv")
    
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample data not found")
        
    return await run_analysis_pipeline(sample_path, "sample_data.csv", 1000.0)

def _compute_aic(ll: float, k: int) -> float:
    """Shared AIC calculation: AIC = 2k - 2ln(L)"""
    return 2 * k - 2 * ll

async def run_analysis_pipeline(csv_path: Path, filename: str, future_hours: float):
    req_id = getattr(getattr(__import__('contextvars').ContextVar('_'), '__default__', None), None) if False else None
    try:
        settings = load_persistent_settings()
        if settings.optimization_method not in VALID_OPTIMIZATION_METHODS:
            settings.optimization_method = "L-BFGS-B"
        
        config_path = ROOT_DIR / "fault_categories.conf"
        if not config_path.exists():
            config_path = Path("/app/fault_categories.conf")
            
        # 1. Load data
        t, categorized, t0, fault_categories = load_failure_data(
            csv_path, config_path, multi_label=settings.multi_label
        )
        
        if len(t) == 0:
            raise HTTPException(status_code=400, detail="No valid failure data found in CSV. Ensure the file has timestamp and description columns.")

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

        return {
            "id": log_id,
            "summary": {
                "total_failures": n,
                "duration_hours": round(T, 2),
                "start_time": t0.isoformat() if hasattr(t0, 'isoformat') else str(t0)
            },
            "models": results_list,
            "plots": plots_b64,
            "categorized_failures": categorized[:100]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis failed. Please check your CSV format and try again.")
    finally:
        if csv_path.parent.name == "temp_uploads" and csv_path.exists():
            try:
                csv_path.unlink()
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
