
import sys
import os
from pathlib import Path
import numpy as np

# Add root to sys.path
sys.path.append(os.getcwd())

from modeler.data import load_failure_data

csv_path = Path("input/error_log.csv")
config_path = Path("fault_categories.conf")

try:
    t, categorized, t0, fault_categories = load_failure_data(csv_path, config_path)
    print(f"Loaded {len(t)} events.")
    if len(t) > 0:
        print(f"First event rel_hours: {t[0]}")
    else:
        print("No events loaded!")
except Exception as e:
    print(f"Error: {e}")
