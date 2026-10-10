"""
Plot rendering for the analysis pipeline.

Uses matplotlib's object-oriented ``Figure`` API with the Agg canvas only — no
``pyplot`` global state — so concurrent requests in worker threads cannot
interfere with each other and figures are released as soon as they go out of
scope (nothing is registered with pyplot's figure manager, so nothing leaks).
"""

import logging
from collections import Counter

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

_DPI = 120


def _new_figure(figsize):
    fig = Figure(figsize=figsize)
    FigureCanvasAgg(fig)
    return fig


def _save(fig: Figure, path: str) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=_DPI)
    return path


def plot_reliability_growth(t, n, curves, results, ensemble, tt, prefix):
    try:
        fig = _new_figure((10, 6))
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(t, np.arange(1, n + 1), 'o', label=f'Observed ({n})', alpha=0.7)
        for m, curve in curves.items():
            label = results[m][3] if m in results else m
            ax.plot(tt, curve, label=label)
        if ensemble is not None:
            ax.plot(tt, ensemble, '--', linewidth=2.5, label='Ensemble (recommended)')
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Cumulative Failures')
        ax.set_title('Reliability Growth – Observed vs Predicted')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plot_path = _save(fig, f"{prefix}_reliability_plot.png")
        logger.info("Saved reliability plot to %s", plot_path)
        return plot_path
    except Exception:
        logger.exception("Failed to plot reliability growth (prefix=%s)", prefix)
        return None


def plot_failure_intensity(tt, curves_intensity, ensemble_intensity, prefix):
    try:
        fig = _new_figure((10, 6))
        ax = fig.add_subplot(1, 1, 1)
        for m, curve in curves_intensity.items():
            label = m.upper() if len(m) <= 2 else m
            ax.plot(tt, curve, label=f"{label} Intensity")
        if ensemble_intensity is not None:
            ax.plot(tt, ensemble_intensity, '--', linewidth=2.5, label='Ensemble Intensity')
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Failures per Hour (Intensity)')
        ax.set_title('Failure Intensity over Time (Rate of Occurrence)')
        if curves_intensity or ensemble_intensity is not None:
            ax.legend()
        ax.grid(True, alpha=0.3)
        plot_path = _save(fig, f"{prefix}_intensity_plot.png")
        logger.info("Saved intensity plot to %s", plot_path)
        return plot_path
    except Exception:
        logger.exception("Failed to plot failure intensity (prefix=%s)", prefix)
        return None


def plot_categories(categorized_list, prefix):
    """Bar chart of failures per category plus cumulative per-category trends.

    Returns the PNG path, or None when there is nothing to plot or rendering fails.
    """
    if not categorized_list:
        logger.info("No categorized failures; skipping category plot")
        return None
    try:
        events = []  # (time_hours, [categories])
        cat_counts = Counter()
        for row in categorized_list:
            cats = [c for c in str(row[2]).split(", ") if c]
            events.append((float(row[1]), cats))
            cat_counts.update(cats)

        sorted_cats = cat_counts.most_common()
        cat_names = [x[0] for x in sorted_cats]
        cat_vals = [x[1] for x in sorted_cats]

        max_time = max(t for t, _ in events)
        time_grid = np.linspace(0, max_time, 200)
        labels = sorted(cat_names)
        stack_data = []
        for cat in labels:
            event_times = np.sort([t for t, cats in events if cat in cats])
            stack_data.append(np.searchsorted(event_times, time_grid, side='right'))

        fig = _new_figure((14, 6))
        ax1, ax2 = fig.subplots(1, 2)

        y_pos = np.arange(len(cat_names))
        ax1.barh(y_pos, cat_vals, align='center', color='skyblue')
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(cat_names)
        ax1.invert_yaxis()  # labels read top-to-bottom
        ax1.set_xlabel('Total Failures')
        ax1.set_title('Failures by Category')
        for i, v in enumerate(cat_vals):
            ax1.text(v, i, str(v), color='black', va='center', fontweight='bold')

        ax2.stackplot(time_grid, stack_data, labels=labels, alpha=0.7)
        ax2.set_xlabel('Time (hours)')
        ax2.set_ylabel('Cumulative Failures')
        ax2.set_title('Category Trends Over Time')
        ax2.legend(loc='upper left', fontsize='small')
        ax2.grid(True, alpha=0.3)

        cat_plot_path = _save(fig, f"{prefix}_category_plot.png")
        logger.info("Saved category plot to %s", cat_plot_path)
        return cat_plot_path
    except Exception:
        logger.exception("Failed to create category plot (prefix=%s)", prefix)
        return None
