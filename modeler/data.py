"""
Fault categorization — shared helpers used by all ingestion sources (Sentry).

This module no longer parses CSV files. Data ingestion happens exclusively
through the Sentry connector (`modeler/sentry.py`), which calls
`categorize_description()` and `load_fault_categories()` to assign fault
categories to incoming failure events.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def load_fault_categories(config_path: Path):
    """Load the fault taxonomy from a config file.

    Format (one rule per line):
        Category [keyword1, keyword2, keyword3]

    Returns a list of (category_name, {keywords}) tuples, or None on error.
    """
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
    """Categorize a failure description against the loaded taxonomy.

    Args:
        desc:        failure description text (may be None/empty)
        categories:  list of (category_name, {keywords}) from load_fault_categories
        multi_label: if True, return a list of all matching categories

    Returns:
        A single category string (multi_label=False) or a list (multi_label=True).
    """
    if not categories or not desc:
        return ["Uncategorized"] if multi_label else "Uncategorized"
    desc_lower = str(desc).lower()
    matches = [cat_name for cat_name, kws in categories if any(kw in desc_lower for kw in kws)]
    if multi_label:
        return matches if matches else ["Other / Uncategorized"]
    else:
        return matches[0] if matches else "Other / Uncategorized"
