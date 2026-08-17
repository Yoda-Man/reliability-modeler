# Reliability Modeler — User Manual

## 1. Introduction

The **Reliability Modeler** analyzes failure events pulled directly from **Sentry** to visualize and predict software reliability growth. It applies Non-Homogeneous Poisson Process (NHPP) models to your error events, transforming them into actionable technical and management insights.

The engine uses two NHPP models:
- **Goel-Okumoto (GO)** — models exponential decrease in failure rate as faults are removed.
- **Musa-Okumoto (MO)** — a logarithmic model that often gives a more realistic, conservative estimate.

> **Data source:** Sentry only. There is no CSV upload or CLI — the tool reads events from your Sentry organization.

## 2. Getting Started

1. Ensure the API server has `SENTRY_AUTH_TOKEN` configured (ask your administrator).
2. Open the **Sentry** tab.
3. Enter your **organization slug**.
4. Choose a **project slug**, or enable **"Analyze all projects"** to aggregate the whole org.
5. Set the **look-back window** (days) and click **Pull & Analyze**.

The analysis runs automatically and opens the **Dashboard** with your results.

## 3. Navigating the Interface

### 3.1 Sentry
The entry point. Enter an org and project (or "all projects"), pick a time window, and pull events from Sentry.

### 3.2 Dashboard
The primary command center for analysis results.
- **KPI Grid**: Total Failures, MTBF, Predicted Residuals, Best Fit Model, Failure Rate.
- **Growth Projection**: Observed failures vs. model predictions.
- **Failure Categories**: Interactive breakdown of failures by taxonomy.
- **MTBF Trend**: How reliability changes over the observation window.
- **Risk Landscape**: Categories plotted by failure count × graph centrality.
- **Failure Heatmap**: Failure density by day-of-week and hour-of-day.
- **Fault Network Intelligence**: Keystone categories and failure cascades.
- **Project Breakdown**: Which Sentry project contributes the most failures (when analyzing "all projects").

### 3.3 Trends
Cross-run comparison — is MTBF improving or degrading across analysis sessions?

### 3.4 Logs Archive
A historical record of all analysis sessions, searchable and paginated.

### 3.5 Configurations
Fine-tune the engine:
- **Fault Taxonomy**: Map keywords to categories (e.g. `Memory [leak, oom, heap]`).
- **Multi-Label Tagging**: Allow a failure to belong to multiple categories.
- **Advanced Engine Settings**: Optimization algorithm and fitting tolerance.

### 3.6 Methodology
A guide to the underlying math — GO vs. MO, AIC for model selection, and how to interpret intensity and residuals.

## 4. Interpreting Results

- **MTBF (higher is better)** — average hours between failures.
- **Predicted Residuals** — estimated undiscovered faults remaining.
- **AIC (lower is better)** — which model fits your data best; the "Best" badge marks the winner.
- **Keystone categories** — fixing these has the greatest ripple effect across your system.
- **Cascades** — error patterns like `Auth → Database → Memory` that reveal which failures trigger others.

## 5. Troubleshooting

- **"No failure events found"** — check the org/project slugs (case-sensitive) or widen the day range.
- **"Failed to pull data from Sentry"** — the API server may be missing `SENTRY_AUTH_TOKEN`, or the token lacks `event:read` scope. Contact your administrator.
- **"Model failed to converge"** — data is too sparse (fewer than 3 events). Try a busier project or a wider time window.
- **Changes not reflecting?** — click **Save Changes** in the Configurations tab before running a new analysis.

---
*Empowering data-driven software releases.*
