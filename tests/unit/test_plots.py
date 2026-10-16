"""Plot rendering uses the OO Figure API: files are produced, nothing leaks into pyplot."""
import sys

import numpy as np

from modeler.plots import plot_categories, plot_failure_intensity, plot_reliability_growth


def _data():
    t = np.array([1.0, 2.0, 4.0, 7.0, 11.0])
    tt = np.linspace(0, 20, 50)
    curves = {"go": tt * 0.5, "mo": np.log1p(tt)}
    results = {"go": "Goel-Okumoto"}
    cats = [("x", float(v), "Database, Network" if i % 2 else "Memory", "d") for i, v in enumerate(t)]
    return t, tt, curves, results, cats


def _pyplot_figures():
    plt = sys.modules.get("matplotlib.pyplot")
    return plt.get_fignums() if plt else []


def test_all_plots_written(tmp_path):
    t, tt, curves, results, cats = _data()
    prefix = str(tmp_path / "p")
    rel = plot_reliability_growth(t, len(t), curves, results, tt, prefix)
    inten = plot_failure_intensity(tt, curves, prefix)
    cat = plot_categories(cats, prefix)
    for path in (rel, inten, cat):
        assert path and open(path, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    assert _pyplot_figures() == []


def test_intensity_without_curves(tmp_path):
    _, tt, _, _, _ = _data()
    assert plot_failure_intensity(tt, {}, str(tmp_path / "p"))


def test_categories_empty_returns_none(tmp_path):
    assert plot_categories([], str(tmp_path / "p")) is None
    assert list(tmp_path.iterdir()) == []


def test_errors_return_none_and_log(tmp_path, caplog):
    bad_prefix = str(tmp_path / "missing-dir" / "p")
    t, tt, curves, results, cats = _data()
    assert plot_reliability_growth(t, len(t), curves, results, tt, bad_prefix) is None
    assert plot_failure_intensity(tt, curves, bad_prefix) is None
    assert plot_categories(cats, bad_prefix) is None
    assert caplog.text.count("Failed to") == 3
