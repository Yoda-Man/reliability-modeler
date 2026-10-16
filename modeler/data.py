"""
Fault categorization — shared helpers used by all ingestion sources (Sentry).

Data ingestion happens exclusively through the Sentry connector
(`modeler/sentry.py`), which calls `load_fault_categories()` and
`categorize_description()` to assign fault categories to incoming events.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Single label used for events that match no taxonomy rule.
UNCATEGORIZED = "Uncategorized"


class TaxonomyError(Exception):
    """Raised when the fault taxonomy file is missing, unreadable or empty."""


def parse_fault_categories(text: str):
    """Parse taxonomy text into a list of (category_name, {keywords}) tuples.

    Format (one rule per line; '#' starts a comment line):
        Category [keyword1, keyword2, keyword3]

    Category names must not contain ',' (categories are joined with ", "
    downstream); such a name raises TaxonomyError.
    """
    categories = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#') or '[' not in line:
            continue
        cat_name, rest = line.split('[', 1)
        cat_name = cat_name.strip()
        if ',' in cat_name:
            raise TaxonomyError(f"Category name {cat_name!r} on line {lineno} must not contain ','")
        keywords = {k.strip().lower() for k in rest.rstrip(']').split(',') if k.strip()}
        if cat_name and keywords:
            categories.append((cat_name, keywords))
    return categories


def load_fault_categories(config_path: Path):
    """Load the fault taxonomy from a config file.

    Returns a non-empty list of (category_name, {keywords}) tuples.

    Raises:
        TaxonomyError: if the file is missing, unreadable, or defines no
            categories. Callers must surface this instead of silently
            categorising every event as Uncategorized.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise TaxonomyError(f"Taxonomy file not found: {config_path}")
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise TaxonomyError(f"Taxonomy file {config_path} is unreadable: {e}") from e
    categories = parse_fault_categories(text)
    if not categories:
        raise TaxonomyError(f"Taxonomy file {config_path} defines no categories")
    logger.info("Loaded %d fault categories from %s", len(categories), config_path)
    return categories


def categorize_description(desc: str, categories, multi_label: bool = False):
    """Categorize a failure description against the loaded taxonomy.

    Args:
        desc:        failure description text (may be None/empty)
        categories:  list of (category_name, {keywords}) from load_fault_categories
        multi_label: if True, return a list of all matching categories

    Returns:
        A single category string (multi_label=False) or a list (multi_label=True).
        Events matching no rule get UNCATEGORIZED.
    """
    matches = []
    if categories and desc:
        desc_lower = str(desc).lower()
        matches = [cat_name for cat_name, kws in categories if any(kw in desc_lower for kw in kws)]
    if multi_label:
        return matches or [UNCATEGORIZED]
    return matches[0] if matches else UNCATEGORIZED
