# Software Reliability Growth Modeler

A powerful, easy-to-use tool for modeling and predicting software reliability using the **Goel-Okumoto (GO)** and **Musa-Okumoto (MO)** Non-Homogeneous Poisson Process (NHPP) models.

This tool helps software managers and engineers estimate:
*   How many latent bugs remain in the system.
*   Future failure intensity (how likely a crash is tomorrow).
*   When the software will reach a desired reliability level.

## Features

*   **Dual Modeling**: Fits both GO and MO models simultaneously.
*   **Automatic Model Selection**: Calculates **AIC (Akaike Information Criterion)** to recommend the best-fitting model for your specific data.
*   **Ensemble Prediction**: Offers an "Ensemble" curve that averages the models for a balanced prediction.
*   **Error Categorization**: Automatically tags failures based on keywords (e.g., "Database", "UI", "Network") using a configurable rules file.
*   **Visualizations**: Generates high-quality reliability growth plots (Observed vs. Predicted).
*   **Human-Readable Summaries**: specific "Plain English" reports for non-technical stakeholders.
*   **Data Export**: Comprehensive CSV exports of parameters, predictions, and categorization trends.
*   **Automated Logging**: All runs are logged to the `output/` directory (e.g., `run_TIMESTAMP.log`) for audit trails.
*   **Modular Architecture**: Cleanly separated logic in `modeler/` package for easy maintenance.

## Prerequisites

*   Python 3.8+
*   Required libraries:
    *   `numpy`
    *   `scipy`
    *   `matplotlib`
    *   `pandas`
    *   `python-dateutil`

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-repo/reliability-modeler.git
    cd reliability-modeler
    ```

2.  Install dependencies using the requirements file:
    ```bash
    pip install -r requirements.txt
    ```

## Building from Source

To create a standalone executable (`.exe`) for easier distribution:

1.  Run the build script:
    ```cmd
    build_release.bat
    ```
2.  Find the complete release package in the `Reference_Release/` folder.
    *   This folder works independently and can be zipped/shared.

    ```bash
    pip install -r requirements.txt
    ```

## Quick Start

1.  **Prepare your data**: Ensure you have a CSV file with failure timestamps (e.g., `error_log.csv`) placed in the `input/` folder.
    *   *Default columns expected*: A timestamp column (e.g., "Date Time") and a description column.

2.  **Run the modeler**:
    ```bash
    python reliability_modeler.py
    ```
    Or simply double-click **`run_analysis.bat`** on Windows.

3.  **View Results**:
    The tool will generate several files in the `output/YYYY/MM/DD/` folder (automatically creating the directories if they don't exist), prefixed with the breakdown timestamp:
    *   `..._reliability_plot.png`: Validates the model fit visually.
    *   `..._human_summary.txt`: A text report explaining the findings in simple language.
    *   `..._predictions.csv`: Detailed numerical data for further analysis.

## Automated Testing

To verify that the environment is set up correctly and the tool runs as expected, you can run the automated test suite:

```powershell
# Integration Tests (End-to-End)
powershell -ExecutionPolicy Bypass -File tests/run_tests.ps1

# Unit Tests (Fast, component level)
run_unit_tests.bat
```

## Usage Options

```bash
usage: reliability_modeler.py [-h] [--csv CSV] [--config CONFIG] [--model {go,mo,both}] 
                              [--start-time START_TIME] [--multi-label] [--silent] 
                              [--export-only] [--prefix PREFIX]

options:
  -h, --help            show this help message and exit
  --csv CSV             Path to failure data CSV (default: input/error_log.csv)
  --config CONFIG       Path to category config (default: fault_categories.conf)
  --model {go,mo,both}  Model to fit (default: both)
  --start-time START_TIME
                        Explicit start time of testing (YYYY-MM-DD HH:MM:SS)
  --multi-label         Allow multiple categories per error description
  --prefix PREFIX       Custom prefix for output files
  --output-dir OUTPUT_DIR
                        Directory to save output files (default: output)
```


## Project Structure

*   `reliability_modeler.py`: Entry point wrapper.
*   `modeler/`: Main package.
    *   `models.py`: GO/MO math and optimization.
    *   `data.py`: CSV loading and categorization.
    *   `plots.py`: Matplotlib charts.
    *   `export.py`: Reports and summaries.
*   `tests/`: Test scripts.
    *   `unit/`: Pytest unit tests.
    *   `run_tests.ps1`: Integration test runner.
*   `input/`: Default data folder.
*   `output/`: Results and Logs.

For more details, see the [USER_MANUAL.md](USER_MANUAL.md).

## License

[MIT License](LICENSE)
