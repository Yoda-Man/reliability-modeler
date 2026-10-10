"""
Unit tests for the GraphQL schema — persistence and query behavior.

Verifies that categorized analysis data is persisted to disk and can be
queried via GraphQL (including the disk fallback after a simulated restart).
"""
import pytest

graphene = pytest.importorskip("graphene")

from modeler import config as rm_config
from web.api import graphql_schema as gql
from web.api.graphql_schema import (
    schema,
    store_analysis_data,
    list_available_analyses,
    get_categorized_data,
    _analysis_store,
)


def _analyses_dir():
    return rm_config.analyses_dir()


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
    analysis_id = "AN-20250101-000001"
    data = _sample_categorized()
    store_analysis_data(analysis_id, data)

    disk_path = _analyses_dir() / f"{analysis_id}.json"
    assert disk_path.exists(), "Categorized data should be persisted to disk"

    # Cleanup
    disk_path.unlink(missing_ok=True)
    gql.forget_analyses([analysis_id])


def test_disk_fallback_after_restart():
    """Simulate restart: data on disk but not in memory."""
    analysis_id = "AN-20250101-000002"
    data = _sample_categorized()
    store_analysis_data(analysis_id, data)

    # Simulate restart: clear in-memory cache
    _analysis_store.clear()

    # Should still retrieve from disk (JSON round-trips tuples to lists)
    retrieved = get_categorized_data(analysis_id)
    assert retrieved is not None
    assert [list(row) for row in retrieved] == [list(row) for row in data]

    # Cleanup
    (_analyses_dir() / f"{analysis_id}.json").unlink(missing_ok=True)
    _analysis_store.clear()


def test_available_analyses_lists_ids():
    analysis_id = "AN-20250101-000003"
    store_analysis_data(analysis_id, _sample_categorized())

    ids = list_available_analyses()
    assert analysis_id in ids

    # Cleanup
    (_analyses_dir() / f"{analysis_id}.json").unlink(missing_ok=True)
    gql.forget_analyses([analysis_id])


def test_schema_query_available_analyses():
    analysis_id = "AN-20250101-000004"
    store_analysis_data(analysis_id, _sample_categorized())

    result = schema.execute("{ availableAnalyses }")
    assert result.errors is None, f"GraphQL query failed: {result.errors}"
    assert analysis_id in result.data["availableAnalyses"]

    # Cleanup
    (_analyses_dir() / f"{analysis_id}.json").unlink(missing_ok=True)
    gql.forget_analyses([analysis_id])


def test_schema_query_keystone_categories():
    analysis_id = "AN-20250101-000005"
    store_analysis_data(analysis_id, _sample_categorized())

    query = '{ keystoneCategories(analysisId: "%s", limit: 5) { node pagerank isKeystone } }' % analysis_id
    result = schema.execute(query)
    assert result.errors is None, f"GraphQL query failed: {result.errors}"
    keystones = result.data["keystoneCategories"]
    assert isinstance(keystones, list)
    assert len(keystones) > 0, "Should return at least one category"

    # Cleanup
    (_analyses_dir() / f"{analysis_id}.json").unlink(missing_ok=True)
    gql.forget_analyses([analysis_id])


def test_cross_analysis_keystone_frequency():
    """Categories that are keystone in multiple analyses should rank first."""
    # Two analyses that both have 'Database' as a keystone category
    id1 = "AN-20250101-000006"
    id2 = "AN-20250101-000007"
    store_analysis_data(id1, _sample_categorized())
    store_analysis_data(id2, _sample_categorized())

    query = '{ keystoneCategoriesAcross(limit: 10) { node keystoneCount totalAnalyses } }'
    result = schema.execute(query)
    assert result.errors is None, f"GraphQL query failed: {result.errors}"
    rows = result.data["keystoneCategoriesAcross"]

    assert isinstance(rows, list)
    assert len(rows) > 0, "Should return at least one category"
    assert rows[0]["totalAnalyses"] == 2, "Both analyses should be examined"
    # Every row should have a keystone count between 1 and total analyses
    for row in rows:
        assert 1 <= row["keystoneCount"] <= 2

    # Cleanup
    (_analyses_dir() / f"{id1}.json").unlink(missing_ok=True)
    (_analyses_dir() / f"{id2}.json").unlink(missing_ok=True)
    _analysis_store.clear()


def test_path_traversal_rejected():
    """Malicious analysis IDs must be rejected (H2 fix)."""
    for bad in ["../../../etc/passwd", "..%2F..%2Fetc", "AN-../settings", "AN-20250101-000001/../../x"]:
        assert get_categorized_data(bad) is None, f"Should reject {bad!r}"


def test_introspection_rejected():
    """Introspection queries are blocked (schema disclosure); __typename is allowed."""
    body, ok = gql.execute_query('{ __schema { types { name } } }')
    assert not ok and "introspection is disabled" in body["errors"][0]
    body, ok = gql.execute_query('{ __type(name: "Query") { name } }')
    assert not ok
    body, ok = gql.execute_query('{ __typename }')
    assert ok and body["data"] == {"__typename": "Query"}


def test_new_analysis_id_format_accepted():
    aid = "AN-20260101-120000-0a1b2c"
    store_analysis_data(aid, _sample_categorized())
    _analysis_store.clear()
    assert get_categorized_data(aid) is not None
    assert aid in list_available_analyses()
    assert get_categorized_data("AN-20260101-120000-0A1B2C") is None


def test_memory_cache_bounded_on_disk_warm_path(monkeypatch):
    monkeypatch.setattr(gql._analysis_store, "maxsize", 3)
    ids = [f"AN-20250101-00000{i}" for i in range(6)]
    for aid in ids:
        store_analysis_data(aid, _sample_categorized())
    _analysis_store.clear()
    for aid in ids:  # every read warms the cache from disk
        assert get_categorized_data(aid) is not None
    assert len(_analysis_store) == 3
    assert _analysis_store.keys() == ids[-3:]


def test_report_cached_per_analysis(monkeypatch):
    aid = "AN-20250101-000010"
    store_analysis_data(aid, _sample_categorized())
    calls = []
    real = gql.build_failure_graphs

    def spy(*a, **k):
        calls.append(a[1:])
        return real(*a, **k)

    monkeypatch.setattr(gql, "build_failure_graphs", spy)
    for _ in range(3):
        assert gql.get_failure_report(aid) is not None
    assert len(calls) == 1
    gql.get_failure_report(aid, 4.0, 1)
    assert len(calls) == 2
    # Re-storing the analysis invalidates its cached reports
    store_analysis_data(aid, _sample_categorized())
    gql.get_failure_report(aid)
    assert len(calls) == 3


def test_corrupt_analysis_file_logged(caplog):
    aid = "AN-20250101-000011"
    _analyses_dir().mkdir(parents=True, exist_ok=True)
    (_analyses_dir() / f"{aid}.json").write_text("{not json")
    assert get_categorized_data(aid) is None
    assert "corrupt" in caplog.text
    (_analyses_dir() / f"{aid}.json").write_text('{"a": 1}')
    assert get_categorized_data(aid) is None
    assert "unexpected shape" in caplog.text


def test_persist_failure_logged(monkeypatch, caplog):
    def fail(*a, **k):
        raise OSError("read-only fs")
    monkeypatch.setattr(rm_config, "atomic_write_json", fail)
    store_analysis_data("AN-20250101-000012", _sample_categorized())
    assert "Failed to persist analysis data" in caplog.text
    # still served from memory
    assert get_categorized_data("AN-20250101-000012") is not None


def test_forget_analyses():
    aid = "AN-20250101-000013"
    store_analysis_data(aid, _sample_categorized())
    gql.get_failure_report(aid)
    gql.forget_analyses([aid])
    gql.forget_analyses([])
    assert aid not in _analysis_store


def test_failure_graph_query_and_missing():
    aid = "AN-20250101-000014"
    store_analysis_data(aid, _sample_categorized())
    q = '{ failureGraph(analysisId: "%s", minCooccurrence: 1) { graphMetrics { numCategories } cascadeChains { chain occurrenceCount } } }'
    body, ok = gql.execute_query(q % aid)
    assert ok and body["data"]["failureGraph"]["graphMetrics"]["numCategories"] == 4
    body, ok = gql.execute_query(q % "AN-20250101-999999")
    assert ok and body["data"]["failureGraph"] is None
    body, ok = gql.execute_query('{ cascadeChains(analysisId: "AN-20250101-999999") { chain } keystoneCategories(analysisId: "bad") { node } }')
    assert ok and body["data"] == {"cascadeChains": [], "keystoneCategories": []}


def test_too_few_events_returns_empty():
    aid = "AN-20250101-000015"
    store_analysis_data(aid, _sample_categorized()[:2])
    assert gql.get_failure_report(aid) is None
    body, ok = gql.execute_query('{ failureGraph(analysisId: "%s") { graphMetrics { numCategories } } }' % aid)
    assert ok and body["data"]["failureGraph"] is None
