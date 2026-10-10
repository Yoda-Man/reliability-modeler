# Reliability Modeler: User Manual

Version 2.9.0

## 1. Introduction

The **Reliability Modeler** analyses failure events pulled directly from **Sentry** to visualise and predict software reliability growth. It applies Non-Homogeneous Poisson Process (NHPP) models to your error events and turns them into technical and management insights.

The engine uses two NHPP models:
- **Goel-Okumoto (GO)**: models an exponential decrease in failure rate as faults are removed.
- **Musa-Okumoto (MO)**: a logarithmic model that often gives a more conservative estimate.

All data comes from your Sentry organisation; there is nothing to upload.

## 2. Logging in

Open the address your administrator gave you (by default `http://<server>:3000`). Your browser shows a **sign-in prompt**. Enter the username and password provided by your administrator (the default username is `admin`).

- The browser remembers the credentials for the session. To sign out, close all browser windows (or clear saved site credentials).
- If the prompt keeps reappearing, the username or password is wrong.
- If you see **"UI_PASSWORD not configured"**, the server has not been set up yet. Contact your administrator.

## 3. Getting started

1. Check the **System Status** badge at the bottom of the sidebar (see section 4).
2. Open the **Sentry** tab.
3. Enter your **organisation slug**.
4. Choose a **project slug**, or enable **"Analyze all projects"** to aggregate the whole organisation.
5. Set the **look-back window** (days) and click **Pull & Analyze**.

The analysis runs on the server (typically a few seconds, up to two minutes for large organisations) and opens the **Dashboard** with your results.

## 4. System Status badge

The badge in the sidebar checks the server's health automatically.

| Badge | Meaning | What to do |
|-------|---------|------------|
| Green | Everything is working | Nothing |
| Amber (degraded) | The application works, but the server has no Sentry token, so new analyses will fail | Contact your administrator |
| Red (unavailable / error) | The server cannot be reached, or its storage is not usable | Wait a minute and reload; if it persists, contact your administrator |

## 5. Navigating the interface

### 5.1 Sentry
The entry point. Enter an org and project (or "all projects"), pick a time window, and pull events from Sentry.

### 5.2 Dashboard
The primary view for analysis results.
- **KPI Grid**: Total Failures, MTBF, Predicted Residuals, Best Fit Model, Failure Rate.
- **Growth Projection**: observed failures vs. model predictions.
- **Failure Categories**: breakdown of failures by taxonomy.
- **MTBF Trend**: how reliability changes over the observation window.
- **Risk Landscape**: categories plotted by failure count x graph centrality.
- **Failure Heatmap**: failure density by day of week and hour of day.
- **Fault Network Intelligence**: keystone categories and failure cascades.
- **Project Breakdown**: which Sentry project contributes the most failures (when analysing "all projects").

### 5.3 Trends
Cross-run comparison: is MTBF improving or degrading across analysis sessions?

### 5.4 Logs Archive
A record of past analysis sessions, searchable and paginated. Each entry has an ID such as `AN-20261010-142233-a1b2c3` (date, UTC time and a short unique suffix). Older entries have IDs without the suffix; both work. Analyses older than the retention period (90 days by default) are removed automatically.

### 5.5 Configurations
- **Fault Taxonomy**: map keywords to categories (e.g. `Memory [leak, oom, heap]`).
- **Multi-Label Tagging**: allow a failure to belong to multiple categories.
- **Advanced Engine Settings**: optimisation algorithm and fitting tolerance.

Click **Save Changes** to apply. Saved settings persist across server restarts and upgrades.

### 5.6 Methodology
A guide to the underlying maths: GO vs. MO, AIC for model selection, and how to read intensity and residuals.

## 6. Interpreting results

- **MTBF (higher is better)**: average hours between failures.
- **Predicted Residuals**: estimated undiscovered faults remaining.
- **AIC (lower is better)**: which model fits your data best; the "Best" badge marks the winner.
- **Keystone categories**: fixing these has the greatest ripple effect across your system.
- **Cascades**: patterns like `Auth -> Database -> Memory` that show which failures trigger others.

## 7. Error messages

When something fails, the affected panel shows a red error box with the message from the server, the HTTP status code and, where possible, a **Retry** button. Empty results ("nothing here yet") are shown differently from errors. If one panel fails, the rest of the application keeps working; if a whole view fails, reload the page.

| Message (or status) | Meaning | What to do |
|---------------------|---------|------------|
| "No failure events found" | Sentry returned no events for that org/project/window | Check the slugs (case-sensitive) or widen the window |
| "Failed to pull data from Sentry" / HTTP 502 | Sentry rejected or failed the request (token, permissions, slug, outage) | Retry later; if it persists, contact your administrator |
| "Model failed to converge" | Too few events (fewer than 3) | Use a busier project or a wider window |
| HTTP 401 | The server rejected the request's credentials | Reload the page and sign in again; if it persists, contact your administrator |
| HTTP 413 "Request body too large" | Submitted data (usually a very large taxonomy) is too big | Shorten the taxonomy |
| HTTP 429 "Too many requests" | You sent many requests in a short time | Wait a minute and try again |
| HTTP 504 / "timed out" | The analysis took too long | Use a shorter window or a single project |
| HTTP 503 | The server is not ready (storage problem or not configured) | Contact your administrator |

When reporting a problem, include the time and, if you can, the **X-Request-ID** shown in your browser's developer tools (Network tab). It lets the administrator find the exact request in the logs.

## 8. Tips

- **Changes not reflected?** Click **Save Changes** in Configurations before running a new analysis.
- **Large organisations:** "Analyze all projects" covers up to 50 projects; analyse busy projects individually for more detail.

---
*Empowering data-driven software releases.*
