
import pytest
from modeler.data import categorize_description

def test_categorize_basic():
    categories = [('Database', {'db', 'sql'}), ('UI', {'button', 'css'})]
    
    assert categorize_description("Connection failed to SQL server", categories) == "Database"
    assert categorize_description("Button not clickable", categories) == "UI"
    assert categorize_description("Something random", categories) == "Other / Uncategorized"

def test_categorize_empty():
    categories = [('Database', {'db'})]
    assert categorize_description("", categories) == "Uncategorized"
    assert categorize_description(None, categories) == "Uncategorized"

def test_categorize_multi_label():
    categories = [('Database', {'db'}), ('High Priority', {'critical'})]
    desc = "Critical DB failure"
    
    # multi_label=True returns list
    labels = categorize_description(desc, categories, multi_label=True)
    assert "Database" in labels
    assert "High Priority" in labels
    
    # multi_label=False returns first match (order depends on list order)
    # Since 'Database' is first in list, it should return that or High Priority depending on loop
    # The current logic matches in order of definition
    assert categorize_description(desc, categories, multi_label=False) == "Database"
