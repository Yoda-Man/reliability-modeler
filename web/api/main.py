import os
import sys
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# Add the app directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append("/app")

from modeler.data import load_failure_data, categorize_description, load_fault_categories
from modeler.models import fit_model, go_mu, mo_mu, go_intensity, mo_intensity
from modeler.plots import plot_reliability_growth, plot_failure_intensity, plot_categories

from pydantic import BaseModel

app = FastAPI(title="Reliability Modeler API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Settings(BaseModel):
    multi_label: bool = False
    data_scrubbing: bool = True
    optimization_method: str = "TNC"
    tolerance: float = 1e-6

def load_persistent_settings() -> Settings:
    settings_path = Path("settings.json")
    if settings_path.exists():
        with open(settings_path, "r") as f:
            return Settings(**json.load(f))
    return Settings()

def save_to_archive(log_id, filename, summary):
    log_dir = Path("output/logs")
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
    log_dir = Path("output/logs")
    if not log_dir.exists():
        return []
    
    logs = []
    for log_file in log_dir.glob("*.json"):
        with open(log_file, "r") as f:
            logs.append(json.load(f))
    
    return sorted(logs, key=lambda x: x['date'], reverse=True)

@app.get("/config")
async def get_config():
    config_path = Path("fault_categories.conf")
    if not config_path.exists():
        config_path = Path("/app/fault_categories.conf")
    
    if config_path.exists():
        with open(config_path, "r") as f:
            content = f.read()
        return {"content": content, "settings": load_persistent_settings()}
    return {"content": "", "settings": load_persistent_settings()}

@app.post("/config")
async def save_config(data: dict):
    config_path = Path("fault_categories.conf")
    if "content" in data:
        with open(config_path, "w") as f:
            f.write(data["content"])
    
    if "settings" in data:
        with open("settings.json", "w") as f:
            json.dump(data["settings"], f)
            
    return {"status": "success"}

@app.post("/analyze")
async def analyze_failure_data(
    file: UploadFile = File(...),
    future_hours: float = 1000.0,
):
    temp_uploads = Path("temp_uploads")
    temp_uploads.mkdir(exist_ok=True)
    csv_path = temp_uploads / file.filename
    with open(csv_path, "wb") as f:
        f.write(await file.read())
    
    return await run_analysis_pipeline(csv_path, file.filename, future_hours)

@app.get("/sample-data")
async def analyze_sample_data():
    sample_path = Path("sample_data.csv")
    if not sample_path.exists():
        sample_path = Path("/app/sample_data.csv")
    
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample data not found")
        
    return await run_analysis_pipeline(sample_path, "sample_data.csv", 1000.0)

async def run_analysis_pipeline(csv_path: Path, filename: str, future_hours: float):
    try:
        settings = load_persistent_settings()
        config_path = Path("fault_categories.conf")
        if not config_path.exists():
            config_path = Path("/app/fault_categories.conf")
            
        # 1. Load data
        t, categorized, t0, fault_categories = load_failure_data(
            csv_path, config_path, multi_label=settings.multi_label
        )
        
        if len(t) == 0:
            raise Exception("No valid failure data found in CSV")

        # 2. Fit models
        T = float(t[-1])
        n = len(t)
        tt = np.linspace(0, T + future_hours, 200)
        
        results_list = []
        curves = {}
        curves_intensity = {}
        fit_data = {}

        for m in ['go', 'mo']:
            params, aic = fit_model(t, model=m, method=settings.optimization_method, tol=settings.tolerance)
            name = "Goel-Okumoto" if m == 'go' else "Musa-Okumoto"
            
            mu = go_mu(tt, params) if m == 'go' else mo_mu(tt, params)
            intensity = go_intensity(tt, params) if m == 'go' else mo_intensity(tt, params)
            
            curves[m] = mu
            curves_intensity[m] = intensity
            
            # For plot_reliability_growth which expects specific results dict
            # results[m] = (params, ll, se, total_exp) -> we simplify or adapt
            total_exp = params[0] if m == 'go' else None
            fit_data[m] = (params, None, None, name) 

            param_map = {}
            if m == 'go':
                param_map = {"a": params[0], "b": params[1]}
            else:
                param_map = {"lambda0": params[0], "theta": params[1]}

            results_list.append({
                "id": m,
                "name": name,
                "aic": round(aic, 4),
                "total_expected_failures": round(total_exp, 2) if total_exp else None,
                "parameters": {k: round(float(v), 6) for k, v in param_map.items()}
            })

        # 3. Plots
        plots_b64 = {}
        temp_plots = Path("temp_plots")
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
    except Exception as e:
        print(f"Pipeline error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if csv_path.name == "temp_upload.csv" or csv_path.parent.name == "temp_uploads":
            if csv_path.exists() and "sample_data" not in csv_path.name:
                csv_path.unlink()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
