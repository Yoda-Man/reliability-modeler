
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import dateutil.parser
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def load_fault_categories(config_path: Path):
    if not config_path.is_file():
        logger.warning(f"Config file not found: {config_path}")
        return None
    categories = []
    try:
        with open(config_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '[' not in line:
                    continue
                parts = line.split('[', 1)
                cat_name = parts[0].strip()
                keywords = [k.strip().lower() for k in parts[1].rstrip(']').split(',') if k.strip()]
                if keywords:
                    categories.append((cat_name, set(keywords)))
        logger.info(f"Loaded {len(categories)} fault categories from {config_path}")
        return categories
    except Exception as e:
        logger.error(f"Error loading fault categories: {e}")
        return None


def categorize_description(desc: str, categories, multi_label: bool = False):
    if not categories or not desc:
        return ["Uncategorized"] if multi_label else "Uncategorized"
    desc_lower = str(desc).lower()
    matches = [cat_name for cat_name, kws in categories if any(kw in desc_lower for kw in kws)]
    if multi_label:
        return matches if matches else ["Other / Uncategorized"]
    else:
        return matches[0] if matches else "Other / Uncategorized"


def load_failure_data(csv_path: Path, config_path: Path, start_time_str: str = None,
                      multi_label: bool = False):
    fault_categories = load_fault_categories(config_path)

    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        raise

    dt_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['date','time','datetime','logged','timestamp'])), df.columns[0])
    desc_col = next((c for c in df.columns if c != dt_col and any(k in str(c).lower() for k in ['desc','error','fault','message'])), None)
    
    logger.debug(f"Identified columns - Timestamp: {dt_col}, Description: {desc_col}")

    # Robust loading: Extract (dt, desc) pairs, then sort
    full_events = []
    
    # Use iterrows for safety
    errors = 0
    for index, row in df.iterrows():
        try:
            val = str(row[dt_col])
            dt = dateutil.parser.parse(val, fuzzy=True)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            
            desc = str(row[desc_col]) if desc_col else ""
            full_events.append((dt, desc))
        except Exception:
            errors += 1
            continue

    if errors > 0:
        logger.warning(f"Skipped {errors} rows due to parsing errors.")

    if not full_events:
        logger.warning("No valid data found in CSV!")
        return np.array([]), [], datetime.now(timezone.utc), fault_categories

    full_events.sort(key=lambda x: x[0])
    sorted_times = [x[0] for x in full_events]
    sorted_descs = [x[1] for x in full_events]

    t0 = dateutil.parser.parse(start_time_str) if start_time_str else sorted_times[0]
    if t0.tzinfo is None: t0 = t0.replace(tzinfo=timezone.utc)

    failure_events = []
    
    for dt, desc in zip(sorted_times, sorted_descs):
        cats = categorize_description(desc, fault_categories, multi_label)
        rel_hours = (dt - t0).total_seconds() / 3600.0
        if rel_hours >= 0:
            failure_events.append((dt, rel_hours, cats, desc))

    failure_events.sort(key=lambda x: x[1])
    t_hours = np.array([ev[1] for ev in failure_events])

    cat_list = []
    for ev in failure_events:
        dt_iso = ev[0].isoformat()
        time_h = round(ev[1], 4)
        cats_str = ", ".join(ev[2]) if isinstance(ev[2], list) else ev[2]
        cat_list.append((dt_iso, time_h, cats_str, ev[3]))
    
    logger.info(f"Processed {len(failure_events)} valid failure events.")
    return t_hours, cat_list, t0, fault_categories
