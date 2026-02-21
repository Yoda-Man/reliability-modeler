# Changelog

All notable changes to the **Reliability Modeler** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-02-21

### Added (Web Architecture)
-   **Containerized Web UI**: Full migration from CLI-only to a dual-tier Next.js and FastAPI architecture.
-   **Executive Dashboard**: Management-optimized UI with Recharts visualizations and real-time KPIs.
-   **Functional Log Archives**: Persistent analysis history with search and status tracking.
-   **Interactive Configurations**: Live-editor for fault taxonomy and analysis behavioral toggles.
-   **Advanced Engine Controls**: UI support for optimization algorithm selection and fitting tolerance.
-   **Methodology View**: Embedded documentation for GO and MO models directly in the app.
-   **Persistence Layer**: Introduced `settings.json` and automated log archiving in the Docker environment.
-   **CSV Format Guide**: Visual in-app guide for data ingestion.

## [1.0.0] - 2026-02-17

### Initial Release
-   **Reliability Modeler**: Core tool for fitting Goel-Okumoto and Musa-Okumoto models.
-   **Failure Intensity Visualization**: Stability charts showing failure rate over time.
-   **Release Build System**: Automated creation of standalone executables.
-   **Date-Based Output**: Automatic organization of results by date.
-   **Reporting**: Detailed CSVs, plots, and human-readable summaries.
