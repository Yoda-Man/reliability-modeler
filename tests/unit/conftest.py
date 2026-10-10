"""
Shared fixtures for the unit suite.

Environment is configured *before* the API module is imported so the
mandatory-auth check passes and nothing ever touches the real repo-level
config or output directories. Every test additionally gets its own
CONFIG_DIR / OUTPUT_DIR under pytest's tmp_path.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

API_KEY = "unit-test-key"
_SESSION_DIR = Path(tempfile.mkdtemp(prefix="rm-unit-"))

os.environ["RELIABILITY_API_KEY"] = API_KEY
os.environ.pop("ALLOW_INSECURE_NO_AUTH", None)
os.environ.pop("SENTRY_AUTH_TOKEN", None)
os.environ["CONFIG_DIR"] = str(_SESSION_DIR / "config")
os.environ["OUTPUT_DIR"] = str(_SESSION_DIR / "output")
os.environ["DEFAULT_CONFIG_PATH"] = str(REPO_ROOT / "fault_categories.conf")
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["RETENTION_DAYS"] = "90"
os.environ.setdefault("MPLBACKEND", "Agg")


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point CONFIG_DIR / OUTPUT_DIR at fresh per-test directories."""
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "output"
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    from web.api import graphql_schema
    graphql_schema.clear_caches()
    yield {"config": config_dir, "output": output_dir}
    graphql_schema.clear_caches()


@pytest.fixture
def api_module():
    from web.api import main
    main._rate_limit_store.clear()
    return main


@pytest.fixture
def client(api_module):
    from fastapi.testclient import TestClient
    with TestClient(api_module.app, headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def anon_client(api_module):
    from fastapi.testclient import TestClient
    with TestClient(api_module.app) as c:
        yield c
