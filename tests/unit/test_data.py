import pytest

from modeler.data import (
    UNCATEGORIZED,
    TaxonomyError,
    categorize_description,
    load_fault_categories,
    parse_fault_categories,
)


def test_categorize_basic():
    categories = [('Database', {'db', 'sql'}), ('UI', {'button', 'css'})]

    assert categorize_description("Connection failed to SQL server", categories) == "Database"
    assert categorize_description("Button not clickable", categories) == "UI"
    assert categorize_description("Something random", categories) == UNCATEGORIZED == "Uncategorized"


def test_categorize_empty():
    categories = [('Database', {'db'})]
    assert categorize_description("", categories) == UNCATEGORIZED
    assert categorize_description(None, categories) == UNCATEGORIZED
    assert categorize_description(None, categories, multi_label=True) == [UNCATEGORIZED]
    assert categorize_description("nothing", categories, multi_label=True) == [UNCATEGORIZED]


def test_categorize_multi_label():
    categories = [('Database', {'db'}), ('High Priority', {'critical'})]
    desc = "Critical DB failure"

    labels = categorize_description(desc, categories, multi_label=True)
    assert labels == ["Database", "High Priority"]
    # single-label returns the first match in definition order
    assert categorize_description(desc, categories, multi_label=False) == "Database"


def test_parse_ignores_comments_and_junk():
    text = "# comment\n\nDatabase [DB, sql ]\nno brackets here\nEmpty []\n[orphan]\n"
    assert parse_fault_categories(text) == [("Database", {"db", "sql"})]


def test_load_valid(tmp_path):
    p = tmp_path / "t.conf"
    p.write_text("Database [db]\nNetwork [http]\n")
    assert [c for c, _ in load_fault_categories(p)] == ["Database", "Network"]


def test_load_missing_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="not found"):
        load_fault_categories(tmp_path / "missing.conf")


def test_load_empty_raises(tmp_path):
    p = tmp_path / "t.conf"
    p.write_text("# nothing\n")
    with pytest.raises(TaxonomyError, match="no categories"):
        load_fault_categories(p)


def test_load_unreadable_raises(tmp_path):
    p = tmp_path / "t.conf"
    p.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(TaxonomyError, match="unreadable"):
        load_fault_categories(p)


def test_comma_in_category_name_rejected():
    with pytest.raises(TaxonomyError, match="line 2.*must not contain ','"):
        parse_fault_categories("Disk [disk]\nNetwork, DNS [dns]\n")
