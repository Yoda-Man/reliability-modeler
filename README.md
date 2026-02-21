# Software Reliability Growth Modeler (Web Ready)

A premium, containerized web application for modeling and predicting software reliability using the **Goel-Okumoto (GO)** and **Musa-Okumoto (MO)** Non-Homogeneous Poisson Process (NHPP) models.

This tool transforms raw failure logs into actionable intelligence, helping management estimate:
*   **MTBF Evolution**: Current and projected system reliability.
*   **Predicted Residuals**: How many latent faults likely remain in the system.
*   **Stability Trends**: When the software will reach a desired reliability threshold for release.

## 🚀 Key Features

*   **Executive Dashboard**: High-fidelity visualizations of reliability growth and failure intensity.
*   **Dynamic Configuration**: Live-edit the fault taxonomy and engine parameters directly from the UI.
*   **Dual Modeling Engine**: Fits both GO and MO models with automatic AIC (Akaike Information Criterion) recommendation.
*   **Analysis Archive**: Automatically persists every analysis run for historical comparison and audit trails.
*   **Smart Categorization**: Uses a customizable rules engine to tag failures (e.g., "Database", "Security", "UI") automatically.
*   **Containerized Stack**: Fully orchestrated with Docker for one-command deployment.

## 📦 Rapid Deployment

The easiest way to run the Reliability Modeler is using Docker.

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Yoda-Man/reliability-modeler.git
    cd reliability-modeler
    ```

2.  **Launch with Docker Compose**:
    ```bash
    docker-compose up --build
    ```

3.  **Access the Application**:
    *   **Web UI**: [http://localhost:3000](http://localhost:3000)
    *   **Backend API**: [http://localhost:8000](http://localhost:8000)

## 📖 Quick Start

1.  **Prepare Data**: Have a CSV file ready with failure timestamps and descriptions.
2.  **Upload**: Use the **Dashboard** drag-and-drop zone to ingest your file.
3.  **Analyze**: View instant KPIs, growth curves, and intensity plots.
4.  **Configure**: Head to the **Configurations** tab to refine how the engine classifies faults or to adjust mathematical solver settings.
5.  **Review History**: Visit the **Logs Archive** to revisit past reports.

## 🛠️ Advanced Engine Settings

The Modeler now supports granular control over the statistical fitting process:
*   **Optimization Algorithm**: Toggle between `L-BFGS-B`, `TNC`, `SLSQP`, and `Nelder-Mead`.
*   **Fitting Tolerance**: Adjust the convergence threshold for high-stakes precision.
*   **Multi-Label Tagging**: Enable overlapping categorization for complex failure descriptions.

## 📁 Project Structure

*   **/web/ui**: Next.js 14 frontend (Tailwind CSS, Recharts, Lucide).
*   **/web/api**: FastAPI backend wrapper.
*   **/modeler**: The core mathematical engine (GO/MO implementations).
*   **/output**: Persistent storage for analysis logs and generated plots.
*   `docker-compose.yml`: Orchestration for the full stack.

## 💻 CLI Usage (Legacy/Advanced)

The core engine remains accessible via CLI for automated pipelines:
```bash
python reliability_modeler.py --csv input/error_log.csv --model both
```

## 🧪 Testing

```powershell
# Run the full test suite
powershell -ExecutionPolicy Bypass -File tests/run_tests.ps1
```

---
*Developed for excellence in software quality engineering.*
