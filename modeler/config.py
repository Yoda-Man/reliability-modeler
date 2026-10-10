"""
Filesystem layout and persistence helpers shared by the API and GraphQL layer.

Every path is resolved from environment variables *at call time* so tests (and
operators) can redirect storage without re-importing modules:

    CONFIG_DIR           holds fault_categories.conf + settings.json
                         (default: repo root locally, /app/config in Docker)
    DEFAULT_CONFIG_PATH  bundled default taxonomy used to seed CONFIG_DIR
                         (default: <repo>/fault_categories.conf)
    OUTPUT_DIR           archives / analyses / plots
                         (default: <repo>/output)

"Repo root" is the directory that contains the ``modeler`` package, which is
the project root in a checkout and ``/app`` in the Docker image.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

TAXONOMY_FILENAME = "fault_categories.conf"
SETTINGS_FILENAME = "settings.json"


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser() if raw else default


def config_dir() -> Path:
    return _env_path("CONFIG_DIR", REPO_ROOT)


def default_config_path() -> Path:
    return _env_path("DEFAULT_CONFIG_PATH", REPO_ROOT / TAXONOMY_FILENAME)


def output_dir() -> Path:
    return _env_path("OUTPUT_DIR", REPO_ROOT / "output")


def taxonomy_path() -> Path:
    return config_dir() / TAXONOMY_FILENAME


def settings_path() -> Path:
    return config_dir() / SETTINGS_FILENAME


def logs_dir() -> Path:
    return output_dir() / "logs"


def analyses_dir() -> Path:
    return output_dir() / "analyses"


def plots_dir() -> Path:
    return output_dir() / "plots"


def temp_plots_dir() -> Path:
    return output_dir() / "temp_plots"


def seed_taxonomy() -> bool:
    """Copy the bundled default taxonomy into CONFIG_DIR if none exists yet.

    Returns True if a file was seeded. Never overwrites an existing taxonomy.
    """
    target = taxonomy_path()
    if target.exists():
        return False
    source = default_config_path()
    if not source.is_file():
        logger.error("Cannot seed taxonomy: default config %s does not exist", source)
        return False
    if source.resolve() == target.resolve():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, source.read_bytes())
    logger.info("Seeded taxonomy %s from bundled default %s", target, source)
    return True


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (temp file + fsync + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, json.dumps(obj).encode("utf-8"))


def is_writable_dir(path: Path) -> bool:
    """True if ``path`` exists (or can be created) and a file can be written in it."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".probe-", delete=True) as f:
            f.write(b"ok")
        return True
    except OSError:
        return False
