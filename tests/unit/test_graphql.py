"""
Unit tests for the GraphQL schema — persistence and query behavior.

Verifies that categorized analysis data is persisted to disk and can be
queried via GraphQL (including the disk fallback after a simulated restart).
"""
import pytest

graphene = pytest.importorskip("graphene")

from web.api.graphql_schema import (
    schema,
    store_analysis_data,
    list_available_analyses,
    _get_categorized_data,
    _ANALYSES_DIR,
    _analysis_store,
)


def _sample_categorized() -> list:
    return [
        ("2025-08-01T08:00:00", 0.0, "Database", "SQL timeout"),
        ("2025-08-01T08:05:00", 0.083, "Database", "deadlock"),
        ("2025-08-01T08:10:00", 0.167, "Network", "gateway timeout"),
        ("2025-08-01T08:15:00", 0.25, "Database, Network", "connection refused"),
        ("2025-08-01T08:20:00", 0.333, "Authentication", "JWT expired"),
        ("2025-08-01T08:25:00", 0.417, "Authentication, Security", "XSS via auth"),
    ]


def test_store_persists_to_disk():
    analysis_id = "AN-TEST-GQL-PERSIST"
    data = _sample_categorized()
    store_analysis_data(analysis_id, data)

    disk_path = _ANALYSES_DIR / f"{analysis_id}.json"
    assert disk_path.exists(), "Categorized data should be persisted to disk"

    # Cleanup
    disk_path.unlink(missing_ok=True)
    _analysis_store.pop(analysis_id, None)


def test_disk_fallback_after_restart():
    """Simulate restart: data on disk but not in memory."""
    analysis_id = "AN-TEST-GQL-FALLBACK"
    data = _sample_categorized()
    store_analysis_data(analysis_id, data)

    # Simulate restart: clear in-memory cache
    _analysis_store.clear()

    # Should still retrieve from disk (JSON round-trips tuples to lists)
    retrieved = _get_categorized_data(None, analysis_id)
    assert retrieved is not None
    assert [list(row) for row in retrieved] == [list(row) for row in data]

    # Cleanup
    (_ANALYSES_DIR / f"{analysis_id}.json").unlink(missing_ok=True)
    _analysis_store.clear()


def test_available_analyses_lists_ids():
    analysis_id = "AN-TEST-GQL-LIST"
    store_analysis_data(analysis_id, _sample_categorized())

    ids = list_available_analyses()
    assert analysis_id in ids

    # Cleanup
    (_ANALYSES_DIR / f"{analysis_id}.json").unlink(missing_ok=True)
    _analysis_store.pop(analysis_id, None)


def test_schema_query_available_analyses():
    analysis_id = "AN-TEST-GQL-QUERY"
    store_analysis_data(analysis_id, _sample_categorized())

    result = schema.execute("{ availableAnalyses }")
    assert result.errors is None, f"GraphQL query failed: {result.errors}"
    assert analysis_id in result.data["availableAnalyses"]

    # Cleanup
    (_ANALYSES_DIR / f"{analysis_id}.json").unlink(missing_ok=True)
    _analysis_store.pop(analysis_id, None)


def test_schema_query_keystone_categories():
    analysis_id = "AN-TEST-GQL-KEYSTONE"
    store_analysis_data(analysis_id, _sample_categorized())

    query = '{ keystoneCategories(analysisId: "%s", limit: 5) { node pagerank isKeystone } }' % analysis_id
    result = schema.execute(query)
    assert result.errors is None, f"GraphQL query failed: {result.errors}"
    keystones = result.data["keystoneCategories"]
    assert isinstance(keystones, list)
    assert len(keystones) > 0, "Should return at least one category"

    # Cleanup
    (_ANALYSES_DIR / f"{analysis_id}.json").unlink(missing_ok=True)
    _analysis_store.pop(analysis_id, None)
