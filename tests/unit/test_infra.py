"""Tests for shared config/persistence helpers and JSON logging."""
import json
import logging

import pytest

from modeler import config as rm_config
from modeler.logutil import JsonFormatter, RequestIdFilter, configure_logging, request_id_var


class TestConfigPaths:
    def test_env_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "o"))
        monkeypatch.setenv("DEFAULT_CONFIG_PATH", str(tmp_path / "d.conf"))
        assert rm_config.taxonomy_path() == tmp_path / "c" / "fault_categories.conf"
        assert rm_config.settings_path() == tmp_path / "c" / "settings.json"
        assert rm_config.analyses_dir() == tmp_path / "o" / "analyses"
        assert rm_config.temp_plots_dir() == tmp_path / "o" / "temp_plots"
        assert rm_config.default_config_path() == tmp_path / "d.conf"

    def test_defaults_are_repo_relative(self, monkeypatch):
        for var in ("CONFIG_DIR", "OUTPUT_DIR", "DEFAULT_CONFIG_PATH"):
            monkeypatch.delenv(var, raising=False)
        root = rm_config.REPO_ROOT
        assert (root / "modeler" / "__init__.py").is_file()
        assert rm_config.config_dir() == root
        assert rm_config.output_dir() == root / "output"
        assert rm_config.default_config_path() == root / "fault_categories.conf"

    def test_seed_copies_once(self, tmp_path, monkeypatch):
        default = tmp_path / "default.conf"
        default.write_text("A [b]\n")
        monkeypatch.setenv("DEFAULT_CONFIG_PATH", str(default))
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "cfg"))
        assert rm_config.seed_taxonomy() is True
        assert rm_config.taxonomy_path().read_text() == "A [b]\n"
        rm_config.taxonomy_path().write_text("Changed [x]\n")
        assert rm_config.seed_taxonomy() is False
        assert rm_config.taxonomy_path().read_text() == "Changed [x]\n"

    def test_seed_missing_default(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("DEFAULT_CONFIG_PATH", str(tmp_path / "nope.conf"))
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "cfg"))
        assert rm_config.seed_taxonomy() is False
        assert "Cannot seed taxonomy" in caplog.text

    def test_seed_same_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("DEFAULT_CONFIG_PATH", str(tmp_path / "fault_categories.conf"))
        # target missing and identical to source: nothing to do
        assert rm_config.seed_taxonomy() is False

    def test_atomic_write_cleans_up_on_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "f.json"
        target.write_text("old")

        def fail(*a):
            raise OSError("boom")
        monkeypatch.setattr(rm_config.os, "replace", fail)
        with pytest.raises(OSError):
            rm_config.atomic_write_json(target, {"a": 1})
        assert target.read_text() == "old"
        assert [p.name for p in tmp_path.iterdir()] == ["f.json"]

    def test_atomic_write_roundtrip(self, tmp_path):
        rm_config.atomic_write_json(tmp_path / "sub" / "x.json", {"a": 1})
        assert json.loads((tmp_path / "sub" / "x.json").read_text()) == {"a": 1}

    def test_is_writable_dir(self, tmp_path):
        assert rm_config.is_writable_dir(tmp_path / "new")
        f = tmp_path / "file"
        f.write_text("x")
        assert not rm_config.is_writable_dir(f)


class TestJsonLogging:
    def _record(self, msg="hello %s", args=("world",), exc_info=None):
        rec = logging.LogRecord("api", logging.INFO, __file__, 1, msg, args, exc_info)
        RequestIdFilter().filter(rec)
        return rec

    def test_fields(self):
        token = request_id_var.set("rid-1")
        try:
            out = json.loads(JsonFormatter().format(self._record()))
        finally:
            request_id_var.reset(token)
        assert set(out) == {"ts", "level", "logger", "msg", "request_id"}
        assert out["msg"] == "hello world" and out["request_id"] == "rid-1"
        assert out["ts"].endswith("+00:00")

    def test_quotes_and_newlines_escaped(self):
        line = JsonFormatter().format(self._record('a "quoted"\nline', ()))
        assert "\n" not in line
        assert json.loads(line)["msg"] == 'a "quoted"\nline'

    def test_exception_included(self):
        try:
            raise ValueError("bad")
        except ValueError:
            import sys
            rec = self._record("oops", (), sys.exc_info())
        out = json.loads(JsonFormatter().format(rec))
        assert "ValueError: bad" in out["exc"]

    def test_configure_idempotent(self):
        configure_logging("DEBUG")
        configure_logging("INFO")
        root = logging.getLogger()
        assert [h.get_name() for h in root.handlers].count("rm-json") == 1
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
