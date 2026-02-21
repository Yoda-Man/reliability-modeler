# Reliability Modeler - User Manual

## 1. Introduction

The **Reliability Modeler** is a command-line tool designed to help software teams visualize and predict software reliability growth. It uses two classic Non-Homogeneous Poisson Process (NHPP) models:
*   **Goel-Okumoto (GO)**: Assumes a finite number of faults that are removed over time.
*   **Musa-Okumoto (MO)**: Assumes failures occur at a rate that decreases logarithmically as testing proceeds.

By fitting these models to your historical bug data, the tool estimates key metrics like the total expected number of failures and the current failure intensity.

## 2. Preparing Your Data

### 2.1 Fault Data (CSV)

The tool requires a CSV file containing at least two columns:
1.  **Timestamp**: The date and time the failure occurred. (e.g., `Date Time Of Error`)
2.  **Description**: A text description of the error. (e.g., `Error or Fault Description`)

**Example `error_log.csv`:**
```csv
Date Time Of Error,Error or Fault Description
2025-01-01 08:12:45,NullPointerException in auth service
2025-01-01 09:30:10,Database timeout
...
```

The default location for your data file is the `input/` folder.

### 2.2 Category Configuration (Optional)

To categorize errors automatically (e.g., "Database" vs. "UI"), you can customize `fault_categories.conf`.

**Format:** `CategoryName [keyword1, keyword2, ...]`

**Example `fault_categories.conf`:**
```ini
Database          [db, sql, query, postgres, mysql, timeout]
Authentication    [login, auth, 401, 403, forbidden]
UI                [render, component, click, display]
```
Lines starting with `#` are ignored.

## 3. Running the Tool

Open your terminal or command prompt and navigate to the project directory.

### Basic Usage
Run with default settings (looks for `input/error_log.csv`):
```bash
python reliability_modeler.py
```

### Specify Files
If your files have different names:
```bash
python reliability_modeler.py --csv my_data.csv --config my_categories.conf
```

### Custom Output Prefix
To organize results by run (e.g., "Run1_..."):
```bash
python reliability_modeler.py --prefix Run1
```

### Custom Output Directory
To save files to a base folder (defaults to `output/`):
```bash
python reliability_modeler.py --output-dir my_results
```
*Note: The tool will automatically create `YYYY/MM/DD` subfolders inside your specified directory.*

### Set Specific Start Time
If testing started before the first logged error, specify the actual start time:
```bash
python reliability_modeler.py --start-time "2025-01-01 08:00:00"
```

### Select Model
Run only one specific model:
```bash
python reliability_modeler.py --model go  # Only Goel-Okumoto
python reliability_modeler.py --model mo  # Only Musa-Okumoto
```

## 4. Understanding the Output

The tool generates several files for each run, organized by date in the `output/YYYY/MM/DD/` directory. The script is smart enough to create these folders automatically if they don't exist.

### 4.0 Execution Log (`run_TIMESTAMP.log`)
A full technical log of what the tool did, including data loading details, model fitting convergence info, and any minor warnings that didn't stop execution. Useful for debugging.

### 4.1 Reliability Plot (`*_reliability_plot.png`)
*   **Blue Dots**: Actual observed cumulative failures over time.
*   **Lines**: The fitted model curves.
*   **Dashed Line (Ensemble)**: The average prediction of both models (often the most robust predictor).

**Interpretation**:
*   If the curve is flattening out, reliability is growing (bugs are becoming harder to find).
*   If the curve is steep and linear, the software is still unstable.

### 4.2 Human Summary (`*_human_summary.txt`)
A plain-text file designed for managers. It answers:
*   "How many bugs have we found?"
*   "How many more do we expect in the next X hours?"
*   "What are the biggest problem areas?"

### 4.3 Detailed CSVs
*   `*_parameters.csv`: Mathematical parameters (a, b for GO; lambda0, theta for MO) and statistical fit quality (AIC). Lower AIC indicates a better fit.
*   `*_predictions.csv`: Hour-by-hour predicted cumulative failures with 95% confidence intervals.
*   `*_categorized.csv`: The original data with an added "Categories" column.
*   `*_category_trends.csv`: Cumulative count of failures per category over time, useful for plotting category-specific growth.

## 5. Troubleshooting

*   **"No columns found"**: Ensure your CSV headers contain keywords like "Date", "Time", "Error", or "Description".
*   **"Not enough data"**: The model requires at least 3 failure points to attempt a fit.
*   **Linear Algebra Errors**: If the data is too sparse or perfectly linear, the optimization might fail to converge. Try using more data points.
*   **Timezone Warnings**: The tool attempts to handle timezones, but consistent UTC or local time strings are recommended.

## 6. Developer Notes

If you want to modify or extend the tool:

*   **Structure**: The core logic is in the `modeler/` directory. `reliability_modeler.py` is just a launch wrapper.
*   **Unit Tests**: Run `run_unit_tests.bat` to verify changes to the math or logic.
*   **Dependencies**: If you add libraries, update `requirements.txt`. 
