"""
End-to-end smoke test: runs the full CLI pipeline and verifies all output files.

Run with: python -m pytest tests/e2e/ -v
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modeler.data import load_failure_data
from modeler.models import fit_model, go_mu, mo_mu
from modeler.export import export_and_summarize
from modeler.plots import plot_reliability_growth, plot_failure_intensity, plot_categories


def test_full_pipeline_smoke():
    """Run the complete analysis pipeline on sample data and verify outputs."""
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_path = project_root / "web" / "api" / "sample_data.csv"
    config_path = project_root / "fault_categories.conf"

    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = str(Path(tmpdir) / "e2e_test")

        # 1. Load data
        t, categorized, t0, fault_categories = load_failure_data(csv_path, config_path)
        assert len(t) > 0, "Should load at least one failure event"
        assert len(categorized) > 0, "Should have categorized failures"

        t = np.sort(t)
        T = float(t[-1])
        n = len(t)
        tt = np.linspace(0, T * 1.6, 100)

        # 2. Fit both models
        results = {}
        curves = {}
        for m in ['go', 'mo']:
            params, ll, se, total_exp = fit_model(t, T, model_name=m)
            assert params is not None, f"{m} model should converge"
            assert ll is not None, f"{m} model should have log-likelihood"
            results[m] = (params, ll, se, total_exp)
            curves[m] = go_mu(tt, params) if m == 'go' else mo_mu(tt, params)

        # 3. Export
        ensemble = (curves['go'] + curves['mo']) / 2 if len(curves) == 2 else None
        generated, warnings = export_and_summarize(
            results, tt, curves, t, np.arange(1, n + 1), ensemble,
            categorized, prefix, fault_categories, t, T
        )

        # 4. Verify output files
        assert len(generated) > 0, "Should generate output files"
        summary_path = Path(f"{prefix}_human_summary.txt")
        assert summary_path.exists(), "Should generate human summary"
        content = summary_path.read_text()
        assert "Reliability Summary" in content, "Summary should contain reliability info"
        assert "failures" in content.lower(), "Summary should mention failures"

        params_path = Path(f"{prefix}_parameters.csv")
        assert params_path.exists(), "Should generate parameters CSV"

        # 5. Verify graph analytics if networkx available
        try:
            from modeler.graphs import build_failure_graphs
            report = build_failure_graphs(categorized)
            if report:
                assert len(report.centrality) > 0, "Should have centrality scores"
                assert report.metrics is not None, "Should have graph metrics"
        except ImportError:
            pass  # networkx not installed — acceptable


def test_cli_help():
    """Verify CLI --help and --version work."""
    import subprocess
    project_root = Path(__file__).resolve().parent.parent.parent

    # --help
    result = subprocess.run(
        [sys.executable, str(project_root / "reliability_modeler.py"), "--help"],
        capture_output=True, text=True, cwd=str(project_root)
    )
    assert result.returncode == 0, f"--help failed: {result.stderr}"
    assert "Reliability Growth Modeler" in result.stdout

    # --version
    result = subprocess.run(
        [sys.executable, str(project_root / "reliability_modeler.py"), "--version"],
        capture_output=True, text=True, cwd=str(project_root)
    )
    assert result.returncode == 0, f"--version failed: {result.stderr}"
    assert "Reliability Modeler" in result.stdout
