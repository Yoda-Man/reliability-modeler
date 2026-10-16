"""
Reliability Modeler API.

Configuration is entirely environment-driven (see README / CONTRACT):
RELIABILITY_API_KEY (required unless ALLOW_INSECURE_NO_AUTH=true), CONFIG_DIR,
DEFAULT_CONFIG_PATH, OUTPUT_DIR, RETENTION_DAYS, ANALYSIS_TIMEOUT_SECONDS,
MAX_BODY_BYTES, RATE_LIMIT_PER_MINUTE, ALLOWED_ORIGINS, SENTRY_AUTH_TOKEN,
SENTRY_BASE_URL, LOG_LEVEL.
"""

import asyncio
import base64
import html as _html
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

# Make `modeler` importable when running from a checkout (`cd web/api &&
# uvicorn main:app`) as well as from the flat Docker layout (/app/modeler).
_API_DIR = Path(__file__).resolve().parent
for _candidate in (_API_DIR, _API_DIR.parent.parent):
    if (_candidate / "modeler" / "__init__.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from modeler import __version__
from modeler import config as rm_config
from modeler.data import TaxonomyError, load_fault_categories, parse_fault_categories
from modeler.graphs import build_failure_graphs, generate_graph_insights
from modeler.logutil import configure_logging, request_id_var
from modeler.models import fit_model, go_mu, mo_mu, go_intensity, mo_intensity
from modeler.plots import plot_reliability_growth, plot_failure_intensity, plot_categories
from modeler.sentry import (
    SentryCancelled,
    SentryError,
    list_sentry_projects,
    load_sentry_failures,
    load_sentry_failures_all,
)

try:
    from . import graphql_schema as gql
except ImportError:
    import graphql_schema as gql

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("api")


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}")
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {value}")
    return value


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# ── Security configuration (fail closed) ─────────────────────────────────────
def load_api_key() -> str:
    """Return the configured API key, or "" when auth is explicitly disabled.

    Raises RuntimeError (refusing to start) when no key is set and the
    ALLOW_INSECURE_NO_AUTH escape hatch is not enabled.
    """
    key = os.getenv("RELIABILITY_API_KEY", "").strip()
    if key:
        return key
    if _env_bool("ALLOW_INSECURE_NO_AUTH"):
        logger.warning("SECURITY WARNING: RELIABILITY_API_KEY is not set and ALLOW_INSECURE_NO_AUTH=true. "
                       "API key authentication is DISABLED; every endpoint is reachable by anyone "
                       "who can reach this server. Never run this way in production.")
        return ""
    raise RuntimeError("RELIABILITY_API_KEY is not set. Refusing to start without authentication. "
                       "Set RELIABILITY_API_KEY (e.g. `openssl rand -hex 32`), or set "
                       "ALLOW_INSECURE_NO_AUTH=true for local development only.")


API_KEY = load_api_key()
AUTH_EXEMPT_PATHS = {"/health", "/health/live"}
RATE_LIMIT_EXEMPT_PATHS = {"/health/live"}

ANALYSIS_TIMEOUT_SECONDS = _env_int("ANALYSIS_TIMEOUT_SECONDS", 120, minimum=1)
MAX_BODY_BYTES = _env_int("MAX_BODY_BYTES", 1024 * 1024, minimum=1)
# RATE_LIMIT_MAX is the pre-2.9 name, still honoured as a fallback.
RATE_LIMIT_PER_MINUTE = _env_int("RATE_LIMIT_PER_MINUTE", _env_int("RATE_LIMIT_MAX", 30, 1), minimum=1)
RATE_LIMIT_WINDOW_SECONDS = 60
RETENTION_DAYS = _env_int("RETENTION_DAYS", 90, minimum=0)
TEMP_PLOT_MAX_AGE_SECONDS = 3600
MAX_TAXONOMY_CHARS = 256 * 1024
MAX_GRAPHQL_BYTES = 256 * 1024

VALID_OPTIMIZATION_METHODS = ("L-BFGS-B", "TNC", "SLSQP", "Nelder-Mead")
MIN_FUTURE_HOURS = 1
MAX_FUTURE_HOURS = 100000
ANALYSIS_ID_RE = gql.ANALYSIS_ID_RE
_REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9-]")


# ── Metrics (hand-rolled Prometheus text format) ─────────────────────────────
class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.http_requests: Dict[Tuple[str, int], int] = {}
        self.analyses: Dict[str, int] = {}
        self.analysis_duration_sum = 0.0
        self.analysis_duration_count = 0
        self.ingest_failures = 0

    def observe_request(self, method: str, status: int) -> None:
        with self._lock:
            key = (method, int(status))
            self.http_requests[key] = self.http_requests.get(key, 0) + 1

    def observe_analysis(self, result: str, duration: Optional[float] = None) -> None:
        with self._lock:
            self.analyses[result] = self.analyses.get(result, 0) + 1
            if duration is not None:
                self.analysis_duration_sum += duration
                self.analysis_duration_count += 1

    def ingest_failed(self) -> None:
        with self._lock:
            self.ingest_failures += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP rm_http_requests_total HTTP requests by method and status.",
                "# TYPE rm_http_requests_total counter",
            ]
            for (method, status), n in sorted(self.http_requests.items()):
                lines.append(f'rm_http_requests_total{{method="{method}",status="{status}"}} {n}')
            lines += [
                "# HELP rm_analyses_total Reliability analyses by result.",
                "# TYPE rm_analyses_total counter",
            ]
            for result, n in sorted(self.analyses.items()):
                lines.append(f'rm_analyses_total{{result="{result}"}} {n}')
            lines += [
                "# HELP rm_analysis_duration_seconds Time spent running analyses.",
                "# TYPE rm_analysis_duration_seconds summary",
                f"rm_analysis_duration_seconds_sum {self.analysis_duration_sum:.6f}",
                f"rm_analysis_duration_seconds_count {self.analysis_duration_count}",
                "# HELP rm_ingest_failures_total Failed Sentry ingests (fetch errors and timeouts).",
                "# TYPE rm_ingest_failures_total counter",
                f"rm_ingest_failures_total {self.ingest_failures}",
            ]
        return "\n".join(lines) + "\n"


metrics = Metrics()


# ── Retention ────────────────────────────────────────────────────────────────
def _prune_directory(dir_path: Path, cutoff: float) -> List[str]:
    """Delete files older than `cutoff` (epoch seconds) in a directory. Returns names pruned."""
    if not dir_path.exists():
        return []
    pruned = []
    for f in dir_path.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                pruned.append(f.name)
        except OSError:
            logger.warning("Failed to prune %s", f, exc_info=True)
    return pruned


def prune_output(retention_days: int) -> Dict[str, List[str]]:
    """Prune archived logs/analyses/plots older than `retention_days` and stale temp plots."""
    now = time.time()
    cutoff = now - retention_days * 86400
    result = {
        "logs": _prune_directory(rm_config.logs_dir(), cutoff),
        "analyses": _prune_directory(rm_config.analyses_dir(), cutoff),
        "plots": _prune_directory(rm_config.plots_dir(), cutoff),
        "temp_plots": _prune_directory(rm_config.temp_plots_dir(), now - TEMP_PLOT_MAX_AGE_SECONDS),
    }
    gql.forget_analyses(Path(name).stem for name in result["analyses"])
    total = sum(len(v) for v in result.values())
    if total:
        logger.info("Retention prune (%d days) removed %d file(s): %s", retention_days, total,
                    json.dumps({k: v[:20] + (["..."] if len(v) > 20 else []) for k, v in result.items() if v}))
    else:
        logger.info("Retention prune (%d days): nothing to remove", retention_days)
    return result


async def _retention_loop():
    """Prune on startup and then once a day."""
    while True:
        try:
            await asyncio.to_thread(prune_output, RETENTION_DAYS)
        except Exception:
            logger.exception("Scheduled retention prune failed")
        await asyncio.sleep(86400)


def _startup_checks() -> None:
    cfg_dir = rm_config.config_dir()
    out_dir = rm_config.output_dir()
    logger.info("Reliability Modeler API %s starting: CONFIG_DIR=%s OUTPUT_DIR=%s DEFAULT_CONFIG_PATH=%s",
                __version__, cfg_dir, out_dir, rm_config.default_config_path())
    try:
        rm_config.seed_taxonomy()
    except OSError:
        logger.exception("Failed to seed taxonomy into %s", cfg_dir)
    if not rm_config.is_writable_dir(cfg_dir):
        logger.warning("CONFIG_DIR %s is not writable: configuration changes cannot be saved. "
                       "Mount a writable persistent volume there.", cfg_dir)
    if not rm_config.is_writable_dir(out_dir):
        logger.error("OUTPUT_DIR %s is not writable: analyses cannot be archived.", out_dir)
    try:
        load_fault_categories(rm_config.taxonomy_path())
    except TaxonomyError as e:
        logger.error("Taxonomy not loaded: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup_checks()
    task = None
    if RETENTION_DAYS > 0:
        task = asyncio.create_task(_retention_loop())
    else:
        logger.info("RETENTION_DAYS=0: automatic retention pruning disabled")
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(
    title="Reliability Modeler API",
    version=__version__,
    lifespan=lifespan,
)


# ── Error handling: uniform {"detail": "<message>"} bodies ───────────────────
def _validation_message(errors) -> str:
    parts = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        msg = err.get("msg", "Invalid value")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "Invalid request"


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": _validation_message(exc.errors())})


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(jsonable_encoder(exc.detail))
    return JSONResponse(status_code=exc.status_code, content={"detail": detail},
                        headers=getattr(exc, "headers", None))


class BodyTooLarge(HTTPException):
    """Raised from the wrapped ASGI receive channel when a body exceeds MAX_BODY_BYTES.

    Subclasses HTTPException so FastAPI's body parsing re-raises it unchanged
    (instead of converting it into a generic 400).
    """

    def __init__(self):
        super().__init__(status_code=413, detail=f"Request body too large (max {MAX_BODY_BYTES} bytes)")


async def _send_json(send, status: int, detail: str, headers: Optional[Dict[str, str]] = None):
    body = json.dumps({"detail": detail}).encode("utf-8")
    raw_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), str(v).encode()))
    await send({"type": "http.response.start", "status": status, "headers": raw_headers})
    await send({"type": "http.response.body", "body": body})


# ── Gateway middleware: request id, logging, metrics, auth, rate limit, body limit
_rate_limit_store: Dict[str, deque] = {}
_rate_limit_lock = threading.Lock()


def _rate_limited(client_key: str) -> bool:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    with _rate_limit_lock:
        bucket = _rate_limit_store.setdefault(client_key, deque())
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            return True
        bucket.append(now)
        if len(_rate_limit_store) > 1000:
            for key in [k for k, b in _rate_limit_store.items() if not b or b[-1] <= window_start]:
                del _rate_limit_store[key]
    return False


def _is_authenticated(headers: Headers) -> bool:
    if not API_KEY:
        return True
    provided = headers.get("x-api-key", "")
    return secrets.compare_digest(provided.encode("utf-8"), API_KEY.encode("utf-8"))


class GatewayMiddleware:
    """Outermost pure-ASGI middleware.

    Order of checks: request id -> auth -> rate limit -> body size; then the
    app runs with a size-limited receive channel. Any unhandled exception is
    logged with the request id and turned into a sanitized 500.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        req_id = _REQUEST_ID_RE.sub("", headers.get("x-request-id", ""))[:64] or uuid.uuid4().hex[:16]
        token = request_id_var.set(req_id)
        scope.setdefault("state", {})["req_id"] = req_id
        method, path = scope["method"], scope["path"]
        peer = scope["client"][0] if scope.get("client") else "unknown"
        state = {"status": 500, "started": False}
        started_at = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state["started"] = True
                state["status"] = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = req_id
            await send(message)

        try:
            authed = _is_authenticated(headers)
            is_preflight = method == "OPTIONS" and "access-control-request-method" in headers
            if not authed and path not in AUTH_EXEMPT_PATHS and not is_preflight:
                logger.warning("Auth failed for %s on %s %s", peer, method, path)
                await _send_json(send_wrapper, 401, "Invalid or missing API key")
                return

            # X-Forwarded-For is only trusted on requests that carry the API key
            # (i.e. from the UI proxy); otherwise a client could spoof it to
            # dodge the limiter.
            client_key = peer
            xff = headers.get("x-forwarded-for", "")
            if xff and authed and API_KEY:
                client_key = xff.split(",")[0].strip() or peer
            if path not in RATE_LIMIT_EXEMPT_PATHS and _rate_limited(client_key):
                logger.warning("Rate limit exceeded for %s on %s %s", client_key, method, path)
                await _send_json(send_wrapper, 429, "Too many requests",
                                 {"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)})
                return

            content_length = headers.get("content-length")
            if content_length is not None:
                try:
                    too_big = int(content_length) > MAX_BODY_BYTES
                except ValueError:
                    await _send_json(send_wrapper, 400, "Invalid Content-Length header")
                    return
                if too_big:
                    await _send_json(send_wrapper, 413, f"Request body too large (max {MAX_BODY_BYTES} bytes)")
                    return

            received = 0

            async def limited_receive():
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > MAX_BODY_BYTES:
                        raise BodyTooLarge()
                return message

            await self.app(scope, limited_receive, send_wrapper)
        except BodyTooLarge as e:
            if not state["started"]:
                await _send_json(send_wrapper, 413, e.detail)
        except Exception:
            logger.exception("Unhandled error on %s %s", method, path)
            if not state["started"]:
                await _send_json(send_wrapper, 500, f"Internal server error (request id {req_id})")
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            metrics.observe_request(method, state["status"])
            logger.info("%s %s -> %d %.0fms", method, path, state["status"], elapsed_ms)
            request_id_var.reset(token)


ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
# Added last => outermost.
app.add_middleware(GatewayMiddleware)


# ── Models ───────────────────────────────────────────────────────────────────
class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    multi_label: bool = False
    optimization_method: Literal["L-BFGS-B", "TNC", "SLSQP", "Nelder-Mead"] = "L-BFGS-B"
    tolerance: float = Field(1e-6, gt=0, le=1)


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Optional[str] = Field(None, max_length=MAX_TAXONOMY_CHARS)
    settings: Optional[Settings] = None

    @field_validator("content")
    @classmethod
    def _check_taxonomy(cls, v):
        if v is None:
            return v
        for lineno, line in enumerate(v.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '[' not in stripped or not stripped.endswith(']'):
                raise ValueError(f"Invalid taxonomy format on line {lineno}. "
                                 "Each line must be: Category [keyword1, keyword2]")
        try:
            categories = parse_fault_categories(v)
        except TaxonomyError as e:
            raise ValueError(str(e))
        if not categories:
            raise ValueError("Taxonomy must define at least one category")
        return v


_SLUG_PATTERN = r"^[a-zA-Z0-9._-]+$"


class SentryIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org: str = Field(..., min_length=1, max_length=100, pattern=_SLUG_PATTERN)
    project: str = Field(..., min_length=1, max_length=100, pattern=_SLUG_PATTERN,
                         description="Project slug, or 'all' to aggregate every project")
    days: int = Field(30, ge=1, le=90)
    future_hours: float = Field(1000.0, ge=MIN_FUTURE_HOURS, le=MAX_FUTURE_HOURS, allow_inf_nan=False)


# ── Settings & archive persistence ───────────────────────────────────────────
def load_persistent_settings() -> Settings:
    path = rm_config.settings_path()
    if not path.exists():
        return Settings()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("settings.json must contain a JSON object")
        known = {k: v for k, v in raw.items() if k in Settings.model_fields}
        return Settings(**known)
    except (OSError, ValueError, ValidationError):
        logger.error("Failed to load %s; using default settings", path, exc_info=True)
        return Settings()


def save_to_archive(log_id: str, filename: str, summary: dict) -> None:
    entry = {
        "id": log_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "file": filename,
        "status": "Completed",
        "summary": summary,
    }
    rm_config.atomic_write_json(rm_config.logs_dir() / f"{log_id}.json", entry)


def _read_json_files(directory: Path) -> List[Tuple[Path, dict]]:
    entries = []
    if not directory.exists():
        return entries
    for path in directory.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Skipping unreadable/corrupt archive file %s", path, exc_info=True)
            continue
        if not isinstance(data, dict):
            logger.warning("Skipping archive file %s with unexpected shape", path)
            continue
        entries.append((path, data))
    return entries


def _taxonomy_status() -> Tuple[bool, Optional[str]]:
    try:
        load_fault_categories(rm_config.taxonomy_path())
        return True, None
    except TaxonomyError as e:
        return False, str(e)


# ── Health & metrics ─────────────────────────────────────────────────────────
@app.get("/health/live")
async def health_live():
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    output_writable = await asyncio.to_thread(rm_config.is_writable_dir, rm_config.output_dir())
    config_readable, _ = await asyncio.to_thread(_taxonomy_status)
    sentry_configured = bool(os.getenv("SENTRY_AUTH_TOKEN", "").strip())
    if not (output_writable and config_readable):
        status, code = "error", 503
    elif not sentry_configured:
        status, code = "degraded", 200
    else:
        status, code = "ok", 200
    body = {
        "status": status,
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "output_writable": output_writable,
            "config_readable": config_readable,
            "sentry_token_configured": sentry_configured,
        },
    }
    return JSONResponse(status_code=code, content=body)


@app.get("/metrics")
async def get_metrics():
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


# ── Logs / trends / reports ──────────────────────────────────────────────────
@app.get("/logs")
async def get_logs(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, min(offset, 10000))
    all_logs = [entry for _, entry in await asyncio.to_thread(_read_json_files, rm_config.logs_dir())]
    # 'date' has minute resolution; the ID embeds the second, so it breaks ties chronologically.
    all_logs.sort(key=lambda x: (str(x.get('date', '')), str(x.get('id', ''))), reverse=True)
    return {"total": len(all_logs), "logs": all_logs[offset:offset + limit]}


@app.post("/logs/prune")
async def prune_logs(retention_days: Optional[int] = None):
    """Delete archived logs, analyses, and plots older than `retention_days` (default RETENTION_DAYS or 90)."""
    if retention_days is None:
        retention_days = RETENTION_DAYS or 90
    if retention_days < 7:
        raise HTTPException(status_code=422, detail="retention_days must be at least 7")
    result = await asyncio.to_thread(prune_output, retention_days)
    pruned = sum(len(v) for v in result.values())
    return {
        "pruned": pruned,
        "by_directory": {k: len(v) for k, v in result.items()},
        "message": f"Removed {pruned} file(s) older than {retention_days} days",
    }


def _mtbf_and_rate(total_failures, duration_hours) -> Tuple[Optional[float], Optional[float]]:
    """MTBF (h) and failure rate (/h) for an archived run, or (None, None) when
    they are not meaningful (no duration, or fewer than 2 failures)."""
    try:
        tf = float(total_failures or 0)
        dh = float(duration_hours or 0)
    except (TypeError, ValueError):
        return None, None
    if dh <= 0 or tf < 2:
        return None, None
    return round(dh / tf, 4), round(tf / dh, 4)


def _trend_of(runs: List[dict]) -> dict:
    """Trend verdict and first->last change for runs of one source (oldest first)."""
    if len(runs) < 2:
        return {"trend": "insufficient_data" if not runs else "single_run"}
    first_mtbf = runs[0]["mtbf_hours"]
    last_mtbf = runs[-1]["mtbf_hours"]
    if last_mtbf > first_mtbf * 1.05:
        trend = "improving"
    elif last_mtbf < first_mtbf * 0.95:
        trend = "degrading"
    else:
        trend = "stable"
    return {
        "trend": trend,
        "mtbf_change_pct": round((last_mtbf - first_mtbf) / max(0.001, first_mtbf) * 100, 1),
        "rate_change_pct": round((runs[-1]["failure_rate_per_hour"] - runs[0]["failure_rate_per_hour"])
                                 / max(0.001, runs[0]["failure_rate_per_hour"]) * 100, 1),
    }


@app.get("/trends")
async def get_trends():
    """
    Compare MTBF, failure rate, and total failures across archived analysis runs.

    Runs are grouped by source (the archive entry's ``file``, e.g.
    ``sentry://org/project (30d)``) and each group gets its own trend, since
    comparing different projects or windows is meaningless. The top-level
    trend keys describe the group of the most recent run; ``runs`` lists all.
    """
    entries = await asyncio.to_thread(_read_json_files, rm_config.logs_dir())
    entries.sort(key=lambda pe: pe[0].stat().st_mtime if pe[0].exists() else 0)

    runs = []
    groups: Dict[str, List[dict]] = {}
    for path, entry in entries:
        summary = entry.get("summary") or {}
        tf = summary.get("total_failures", 0) or 0
        dh = summary.get("duration_hours", 0) or 0
        mtbf, rate = _mtbf_and_rate(tf, dh)
        if mtbf is None:
            continue
        run = {
            "id": entry.get("id", path.stem),
            "date": entry.get("date", ""),
            "file": str(entry.get("file", "")),
            "total_failures": tf,
            "duration_hours": round(dh, 2),
            "mtbf_hours": mtbf,
            "failure_rate_per_hour": rate,
        }
        runs.append(run)
        group = groups.pop(run["file"], [])
        group.append(run)
        groups[run["file"]] = group

    # dicts keep insertion order, so re-inserting on each run leaves the source
    # with the most recent run last; list groups most recently active first.
    group_list = [{"file": f, "runs": g, "num_runs": len(g), **_trend_of(g)}
                  for f, g in reversed(list(groups.items()))]

    body = {"groups": group_list, "runs": runs}
    if not runs:
        body["trend"] = "insufficient_data"
        return body
    latest = group_list[0]
    body.update({k: v for k, v in latest.items() if k not in ("file", "runs")})
    return body


def _safe_child(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise HTTPException(status_code=400, detail="Invalid analysis ID")
    return path


@app.get("/report/{analysis_id}/html")
async def get_html_report(analysis_id: str):
    """
    Generate a self-contained, print-ready HTML executive report for an analysis run.
    This file can be saved and emailed by any external scheduler (cron, CI, etc.).
    """
    if not ANALYSIS_ID_RE.match(analysis_id):
        raise HTTPException(status_code=400, detail="Invalid analysis ID")

    log_path = _safe_child(rm_config.logs_dir(), f"{analysis_id}.json")
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        if not isinstance(entry, dict):
            raise ValueError("archive entry is not a JSON object")
    except (OSError, UnicodeDecodeError, ValueError):
        logger.error("Archive record %s is unreadable or corrupt", log_path, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis {analysis_id} record is corrupt")

    summary = entry.get("summary") or {}
    tf = summary.get("total_failures", 0) or 0
    dh = summary.get("duration_hours", 0) or 0
    mtbf_v, rate_v = _mtbf_and_rate(tf, dh)
    mtbf = f"{mtbf_v:.2f}h" if mtbf_v is not None else "n/a"
    failure_rate = f"{rate_v:.2f}/h" if rate_v is not None else "n/a"
    safe_file = _html.escape(str(entry.get('file', 'N/A')))
    safe_date = _html.escape(str(entry.get('date', 'N/A')))
    safe_id = _html.escape(analysis_id)
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')

    report_plot = _safe_child(rm_config.plots_dir(), f"{analysis_id}_reliability.png")
    reliability_b64 = ""
    if report_plot.is_file():
        try:
            reliability_b64 = base64.b64encode(report_plot.read_bytes()).decode("utf-8")
        except OSError:
            logger.warning("Could not read report plot %s", report_plot, exc_info=True)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reliability Executive Report — {safe_id}</title>
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
  <h1>Reliability Executive Report</h1>
  <p class="meta">Analysis ID: {safe_id} &middot; File: {safe_file} &middot; Date: {safe_date} UTC</p>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="value">{tf}</div><div class="label">Total Failures</div></div>
  <div class="kpi"><div class="value">{mtbf}</div><div class="label">MTBF</div></div>
  <div class="kpi"><div class="value">{failure_rate}</div><div class="label">Failure Rate</div></div>
  <div class="kpi"><div class="value">{dh}h</div><div class="label">Duration</div></div>
</div>

<div class="section">
  <h2>Executive Summary</h2>
  <p>
    This report presents the results of a software reliability growth analysis
    conducted on <strong>{float(dh):.1f} hours</strong> of failure data containing
    <strong>{tf} incidents</strong>. The Mean Time Between Failures (MTBF) is
    <strong>{mtbf}</strong> with a failure rate of
    <strong>{failure_rate}</strong>.
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
  Reliability Modeler {__version__} &middot; Internal Use Only &middot; Generated {generated} UTC
</div>
</body>
</html>"""

    return {"html": html, "analysis_id": analysis_id}


# ── Configuration ────────────────────────────────────────────────────────────
@app.get("/config")
async def get_config():
    path = rm_config.taxonomy_path()
    content = ""
    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.error("Failed to read taxonomy %s", path, exc_info=True)
            raise HTTPException(status_code=500, detail="taxonomy not loaded")
    return {"content": content, "settings": load_persistent_settings()}


@app.post("/config")
async def save_config(update: ConfigUpdate):
    if update.content is None and update.settings is None:
        raise HTTPException(status_code=422, detail="Provide 'content' and/or 'settings'")
    if update.content is not None:
        path = rm_config.taxonomy_path()
        try:
            await asyncio.to_thread(rm_config.atomic_write_text, path, update.content)
        except OSError:
            logger.error("Failed to write taxonomy %s", path, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save configuration")
        logger.info("Taxonomy updated: %s", path)
    if update.settings is not None:
        path = rm_config.settings_path()
        try:
            await asyncio.to_thread(rm_config.atomic_write_json, path, update.settings.model_dump())
        except OSError:
            logger.error("Failed to write settings %s", path, exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save settings")
        logger.info("Settings updated: %s", path)
    return {"status": "success"}


# ── Analysis pipeline ────────────────────────────────────────────────────────
def _compute_aic(ll: float, k: int) -> float:
    """Shared AIC calculation: AIC = 2k - 2ln(L)"""
    return 2 * k - 2 * ll


def new_analysis_id(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"AN-{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


class AnalysisCancelled(Exception):
    """Raised inside the analysis worker once its request has timed out."""


def _checkpoint(cancel_event: Optional[threading.Event], stage: str) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled(stage)


CATEGORIZED_RESPONSE_LIMIT = 100  # most recent categorized events returned inline


def _run_analysis(t, categorized, t0, filename: str, future_hours: float,
                  cancel_event: Optional[threading.Event] = None) -> Optional[dict]:
    """Core analysis (CPU-bound, runs in a worker thread): fit models, plot, graph, archive.

    ``cancel_event`` is checked between steps; once it is set (the request
    timed out) the run stops and nothing is archived. Returns None then.
    """
    try:
        return _run_analysis_steps(t, categorized, t0, filename, future_hours, cancel_event)
    except AnalysisCancelled as e:
        logger.warning("Analysis of %s cancelled after timeout (before %s); nothing archived", filename, e)
        return None


def _run_analysis_steps(t, categorized, t0, filename, future_hours, cancel_event) -> dict:
    settings = load_persistent_settings()

    T = float(t[-1])
    n = len(t)
    tt = np.linspace(0, T + future_hours, 200)

    results_list = []
    curves = {}
    curves_intensity = {}
    names = {}

    for m in ['go', 'mo']:
        _checkpoint(cancel_event, f"{m} fit")
        try:
            params, ll, total_exp = fit_model(t, T, model_name=m, method=settings.optimization_method,
                                              tol=settings.tolerance)
        except Exception:
            logger.exception("Model fitting failed for %s", m)
            continue
        if params is None:
            logger.warning("No valid %s fit for this data", m)
            continue

        name = "Goel-Okumoto" if m == 'go' else "Musa-Okumoto"
        curves[m] = go_mu(tt, params) if m == 'go' else mo_mu(tt, params)
        curves_intensity[m] = go_intensity(tt, params) if m == 'go' else mo_intensity(tt, params)
        names[m] = name

        if m == 'go':
            param_map = {"a": float(params[0]), "b": float(params[1])}
        else:
            param_map = {"lambda0": float(params[0]), "theta": float(params[1])}

        results_list.append({
            "id": m,
            "name": name,
            "aic": round(_compute_aic(ll, len(params)), 4),
            "total_expected_failures": round(float(total_exp), 2) if total_exp is not None else None,
            "parameters": param_map,
        })

    _checkpoint(cancel_event, "plots")
    log_id = new_analysis_id()
    temp_dir = rm_config.temp_plots_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    prefix_name = f"plot_{uuid.uuid4().hex}"
    prefix = str(temp_dir / prefix_name)
    plots_b64 = {}
    report_plot_bytes = None
    try:
        rel_plot = plot_reliability_growth(t, n, curves, names, tt, prefix)
        intensity_plot = plot_failure_intensity(tt, curves_intensity, prefix)
        cat_plot = plot_categories(categorized, prefix)

        for name, path in [("reliability", rel_plot), ("intensity", intensity_plot), ("categories", cat_plot)]:
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                plots_b64[name] = base64.b64encode(data).decode('utf-8')
                if name == "reliability":
                    report_plot_bytes = data
    finally:
        for leftover in temp_dir.glob(f"{prefix_name}*"):
            try:
                leftover.unlink()
            except OSError:
                logger.warning("Could not remove temp plot %s", leftover, exc_info=True)

    _checkpoint(cancel_event, "graph analysis")
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

    _checkpoint(cancel_event, "archive")
    # Persist the reliability plot so the HTML report can embed it later
    if report_plot_bytes:
        report_plot_dir = rm_config.plots_dir()
        report_plot_dir.mkdir(parents=True, exist_ok=True)
        (report_plot_dir / f"{log_id}_reliability.png").write_bytes(report_plot_bytes)
    save_to_archive(log_id, filename, {"total_failures": n, "duration_hours": round(T, 2)})
    # Store categorized data for GraphQL graph queries and prime the report cache
    gql.store_analysis_data(log_id, categorized, report=graph_report)

    return {
        "id": log_id,
        "summary": {
            "total_failures": n,
            "duration_hours": round(T, 2),
            "start_time": t0.isoformat() if hasattr(t0, 'isoformat') else str(t0),
        },
        "future_hours": future_hours,
        "models": results_list,
        "plots": plots_b64,
        # Most recent events, still oldest -> newest.
        "categorized_failures": categorized[-CATEGORIZED_RESPONSE_LIMIT:],
        "categorized_total": len(categorized),
        "graph_insights": graph_insights,
        "graph_report": graph_summary,
    }


async def _analyze(t, categorized, t0, filename: str, future_hours: float) -> dict:
    """Run the analysis off the event loop with a real timeout."""
    started = time.perf_counter()
    cancel = threading.Event()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_analysis, t, categorized, t0, filename, future_hours, cancel),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        cancel.set()  # stop the worker at its next step; it will not archive
        metrics.observe_analysis("timeout", time.perf_counter() - started)
        logger.error("Analysis of %s timed out after %ss", filename, ANALYSIS_TIMEOUT_SECONDS)
        raise HTTPException(status_code=504, detail="Analysis timed out. Try a narrower time window.")
    except Exception:
        metrics.observe_analysis("error", time.perf_counter() - started)
        logger.exception("Analysis pipeline failed for %s", filename)
        raise HTTPException(status_code=500, detail="Analysis failed. Please check your data and try again.")
    metrics.observe_analysis("success", time.perf_counter() - started)
    return result


def _sentry_token() -> str:
    token = os.getenv("SENTRY_AUTH_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="SENTRY_AUTH_TOKEN not configured on the API server")
    return token


@app.post("/ingest/sentry")
async def ingest_sentry(payload: SentryIngestRequest):
    """
    Pull failure events from Sentry and run the reliability analysis.

    Body:
        {"org": "my-org", "project": "my-project", "days": 30, "future_hours": 1000}
        {"org": "my-org", "project": "all", "days": 30, "future_hours": 1000}   # aggregate all projects
    """
    auth_token = _sentry_token()
    org, project, days = payload.org, payload.project, payload.days

    config_path = rm_config.taxonomy_path()
    try:
        await asyncio.to_thread(load_fault_categories, config_path)
    except TaxonomyError as e:
        logger.error("Taxonomy not loaded: %s", e)
        raise HTTPException(status_code=500, detail="taxonomy not loaded")

    settings = load_persistent_settings()
    cancel = threading.Event()
    project_counts: Dict[str, int] = {}
    truncated = False
    try:
        if project == "all":
            t, categorized, t0, _, project_counts, truncated = await asyncio.wait_for(
                asyncio.to_thread(load_sentry_failures_all, org, auth_token, config_path, days,
                                  settings.multi_label, cancel_event=cancel),
                timeout=ANALYSIS_TIMEOUT_SECONDS,
            )
            display_name = f"sentry://{org}/ALL_PROJECTS ({days}d)"
        else:
            t, categorized, t0, _, truncated = await asyncio.wait_for(
                asyncio.to_thread(load_sentry_failures, org, project, auth_token, config_path, days,
                                  settings.multi_label, cancel_event=cancel),
                timeout=ANALYSIS_TIMEOUT_SECONDS,
            )
            display_name = f"sentry://{org}/{project} ({days}d)"
    except asyncio.TimeoutError:
        cancel.set()  # stop the worker thread at its next page / retry boundary
        metrics.ingest_failed()
        logger.error("Sentry ingest timed out for %s/%s", org, project)
        raise HTTPException(status_code=504, detail="Sentry fetch timed out. Try a narrower time window or a single project.")
    except TaxonomyError as e:
        logger.error("Taxonomy not loaded: %s", e)
        raise HTTPException(status_code=500, detail="taxonomy not loaded")
    except SentryCancelled:
        metrics.ingest_failed()
        raise HTTPException(status_code=504, detail="Sentry fetch was cancelled")
    except SentryError as e:
        metrics.ingest_failed()
        logger.error("Sentry ingest failed for %s/%s: %s", org, project, e)
        raise HTTPException(status_code=502, detail=str(e))

    if len(t) == 0:
        raise HTTPException(status_code=400, detail=f"No failure events found in Sentry for {org}/{project} in the last {days} days")

    result = await _analyze(t, categorized, t0, display_name, payload.future_hours)
    result["truncated"] = bool(truncated)
    if project_counts:
        result["projects"] = dict(sorted(project_counts.items(), key=lambda kv: kv[1], reverse=True))
    return result


@app.get("/ingest/sentry/projects")
async def list_sentry_projects_endpoint(org: str = ""):
    """
    List all projects in a Sentry organization. Returns [{slug, name}, ...].
    Requires SENTRY_AUTH_TOKEN env var.
    """
    if not org:
        raise HTTPException(status_code=422, detail="'org' query parameter is required")
    if not re.match(_SLUG_PATTERN, org) or len(org) > 100:
        raise HTTPException(status_code=422, detail="Invalid org slug")
    auth_token = _sentry_token()
    cancel = threading.Event()
    try:
        projects = await asyncio.wait_for(
            asyncio.to_thread(list_sentry_projects, org, auth_token, None, cancel),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        cancel.set()
        raise HTTPException(status_code=504, detail="Sentry project listing timed out")
    except SentryError as e:
        logger.error("Sentry project listing failed for %s: %s", org, e)
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "org": org,
        "count": len(projects),
        "projects": [
            {"slug": p.get("slug", ""), "name": p.get("name", p.get("slug", ""))}
            for p in projects if isinstance(p, dict)
        ],
    }


# ── GraphQL ──────────────────────────────────────────────────────────────────
@app.post("/graphql")
async def graphql_query(request: Request):
    """GraphQL endpoint for flexible failure graph queries."""
    body_bytes = await request.body()
    if len(body_bytes) > MAX_GRAPHQL_BYTES:
        raise HTTPException(status_code=413, detail=f"GraphQL query too large (max {MAX_GRAPHQL_BYTES // 1024} KB)")
    try:
        body = json.loads(body_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    query_str = body.get("query")
    variables = body.get("variables") or None
    operation_name = body.get("operationName") or None
    if not isinstance(query_str, str) or not query_str.strip():
        raise HTTPException(status_code=400, detail="Missing 'query' field")
    if variables is not None and not isinstance(variables, dict):
        raise HTTPException(status_code=400, detail="'variables' must be an object")
    if operation_name is not None and not isinstance(operation_name, str):
        raise HTTPException(status_code=400, detail="'operationName' must be a string")

    try:
        result, ok = await asyncio.wait_for(
            asyncio.to_thread(gql.execute_query, query_str, variables, operation_name),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="GraphQL query timed out")
    if not ok:
        return JSONResponse(status_code=400, content={"detail": "; ".join(result["errors"]), **result})
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
