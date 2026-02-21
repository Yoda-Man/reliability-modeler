# Reliability Modeler - User Manual

## 1. Introduction

The **Reliability Modeler** is a professional web application designed to help software teams visualize and predict software reliability growth. It leverages advanced statistical modeling to transform raw failure logs into actionable technical and management insights.

The engine utilizes two primary Non-Homogeneous Poisson Process (NHPP) models:
*   **Goel-Okumoto (GO)**: Modeling the exponential decrease in failure rates as faults are removed.
*   **Musa-Okumoto (MO)**: A logarithmic model that often provides a more realistic, conservative estimate of reliability.

## 2. Navigating the Interface

### 2.1 Management Dashboard
The primary command center for analysis.
*   **Upload Zone**: Drag and drop your failure CSV here. The engine automatically detects timestamp and description columns.
*   **KPI Grid**: Instant access to Total Failures, MTBF (Mean Time Between Failures), Predicted Residuals, and the Best Fit Model.
*   **Growth Projection Chart**: Interactive plot showing observed failures vs. model predictions.
*   **Strategic Insights**: AI-driven summaries of which model provides the highest statistical confidence.

### 2.2 Log Archives
A historical record of all analysis sessions.
*   **Persistence**: Every upload is automatically indexed and archived.
*   **Search**: Quickly filter past reports by filename or Analysis ID (e.g., `AN-2026...`).
*   **Metrics Review**: Revisit the failure counts and system duration for any previous run without re-uploading.

### 2.3 System Configurations
Fine-tune how the engine thinks.
*   **Fault Taxonomy**: A live editor where you can map keywords to categories (e.g., `Memory [leak, oom, heap]`). These rules drive the "Categorical Insight" charts.
*   **Behavioral Toggles**:
    *   *Multi-Label Tagging*: Allow a single failure to belong to multiple categories if keywords overlap.
    *   *Auto Data Scrubbing*: Automatically remove malformed entries and duplicates during analysis.
*   **Advanced Engine Settings**:
    *   *Optimization Algorithm*: Choose the mathematical solver (L-BFGS-B, TNC, SLSQP, Nelder-Mead).
    *   *Fitting Tolerance*: Set the precision threshold for model convergence.

### 2.4 Methodology View
A comprehensive guide to the underlying math.
*   Explains GO vs. MO applications.
*   Defines AIC (Akaike Information Criterion) and how to use it for model selection.
*   Provides guidelines for interpreting "Intensity" and "Residuals" in a management context.

## 3. Data Preparation

### 3.1 CSV Requirements
The tool is highly flexible but works best with:
1.  **Timestamp**: ISO format (`2026-01-01 10:00:00`) or relative hours (`14.5`).
2.  **Description**: Text describing the failure (used by the Taxonomy engine).
3.  **Category (Optional)**: If you've already categorized your data, the tool will respect yours.

## 4. Troubleshooting

*   **"No valid failure data found"**: Ensure your CSV is not empty and that the timestamp column is correctly formatted.
*   **"Failed to fit model"**: This usually occurs with very sparse data (fewer than 3 points). Try adjusting the **Advanced Engine Settings** to a more robust solver like `Nelder-Mead`.
*   **Changes not reflecting?**: Remember to click **Save Changes** in the Configurations tab before running a new analysis.

---
*Empowering data-driven software releases.*
