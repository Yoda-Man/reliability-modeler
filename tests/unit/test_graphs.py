"""
Unit tests for the graph analytics module.
"""
import pytest
import sys
import os

# Skip if networkx not installed
networkx = pytest.importorskip("networkx")

from modeler.graphs import (
    build_failure_graphs,
    generate_graph_insights,
    FailureGraphReport,
    CentralityScore,
    CascadeChain,
    CommunityCluster,
)


def _make_categorized_list(single_label: bool = False) -> list:
    """Build a realistic categorized failure list for testing."""
    events = [
        ("2025-01-01T08:00:00", 0.0, "Database, Network", "DB connection timeout"),
        ("2025-01-01T08:05:00", 0.083, "Network", "Gateway timeout 504"),
        ("2025-01-01T08:10:00", 0.167, "Database", "SQL deadlock on orders"),
        ("2025-01-01T08:15:00", 0.25, "Memory, Database", "OOM in DB connection pool"),
        ("2025-01-01T08:20:00", 0.333, "Authentication", "JWT token expired"),
        ("2025-01-01T08:25:00", 0.417, "Authentication, Security", "XSS attempt via auth"),
        ("2025-01-01T08:30:00", 0.5, "Memory", "Heap usage 95%"),
        ("2025-01-01T08:35:00", 0.583, "Database, Network", "Query timeout via gateway"),
        ("2025-01-01T08:40:00", 0.667, "Security", "Injection blocked"),
        ("2025-01-01T08:45:00", 0.75, "Authentication", "Login brute force"),
        ("2025-01-01T08:50:00", 0.833, "Database, Concurrency", "Deadlock in tx"),
        ("2025-01-01T08:55:00", 0.917, "Network", "DNS resolution failed"),
        ("2025-01-01T09:00:00", 1.0, "Memory, Concurrency", "Thread pool exhaustion"),
        ("2025-01-01T09:05:00", 1.083, "Database", "Connection pool empty"),
        ("2025-01-01T09:10:00", 1.167, "Authentication, Network", "LDAP timeout"),
    ]
    if single_label:
        return [(e[0], e[1], e[2].split(", ")[0], e[3]) for e in events]
    return events


class TestBuildFailureGraphs:
    """Test graph construction from categorized data."""

    def test_builds_report_with_multi_label_data(self):
        data = _make_categorized_list(single_label=False)
        report = build_failure_graphs(data, cascade_window_hours=1.0, min_cooccurrence=1)
        assert report is not None
        assert isinstance(report, FailureGraphReport)
        assert report.metrics.num_categories >= 3
        assert report.metrics.num_cooccurrence_edges > 0  # multi-label produces co-occurrences
        assert len(report.centrality) == report.metrics.num_categories
        assert report.graph_json is not None
        assert "nodes" in report.graph_json
        assert "edges" in report.graph_json

    def test_builds_report_with_single_label_data(self):
        """Single-label data should use temporal-proximity fallback."""
        data = _make_categorized_list(single_label=True)
        report = build_failure_graphs(data, cascade_window_hours=1.0, min_cooccurrence=1)
        assert report is not None
        # Temporal proximity should create some edges
        assert report.metrics.num_cooccurrence_edges > 0

    def test_centrality_is_sorted_by_pagerank(self):
        data = _make_categorized_list()
        report = build_failure_graphs(data)
        assert report is not None
        pr_values = [c.pagerank for c in report.centrality]
        assert pr_values == sorted(pr_values, reverse=True)

    def test_keystone_detection(self):
        data = _make_categorized_list()
        report = build_failure_graphs(data)
        assert report is not None
        keystones = [c for c in report.centrality if c.is_keystone]
        assert len(keystones) >= 1, "Should detect at least one keystone category"

    def test_cascade_chains_exist(self):
        data = _make_categorized_list()
        report = build_failure_graphs(data, cascade_window_hours=2.0)
        assert report is not None
        # With 15 events in 1h, cascades should be found
        assert len(report.cascade_chains) >= 1

    def test_graph_json_is_valid(self):
        data = _make_categorized_list()
        report = build_failure_graphs(data)
        assert report is not None
        gj = report.graph_json
        assert len(gj["nodes"]) == report.metrics.num_categories
        # Each node should have an id and pagerank
        for node in gj["nodes"]:
            assert "id" in node
            assert "pagerank" in node

    def test_returns_none_for_too_few_events(self):
        data = [("2025-01-01T08:00:00", 0.0, "Database", "err")]
        report = build_failure_graphs(data)
        assert report is None


class TestGraphInsights:
    """Test the insight text generator."""

    def test_generates_insights(self):
        data = _make_categorized_list()
        report = build_failure_graphs(data)
        assert report is not None
        insights = generate_graph_insights(report)
        assert len(insights) > 0
        # Should contain keystone section
        assert any("Keystone" in line for line in insights)
        # Should contain cascade section
        assert any("Cascad" in line for line in insights)

    def test_handles_none_report(self):
        insights = generate_graph_insights(None)
        assert len(insights) == 1
        assert "networkx" in insights[0].lower()


class TestCascadeChainCounting:
    """Chains must count how often the same category sequence recurs."""

    @staticmethod
    def _repeated(n_reps=5, gap=10.0, noise=False):
        rows = []
        for r in range(n_reps):
            base = r * gap
            rows.append(("t", base, "Database", "db"))
            rows.append(("t", base + 0.5, "Network", "net"))
            rows.append(("t", base + 1.0, "Memory", "mem"))
            if noise:
                rows.append(("t", base + 5.0, "Security" if r % 2 else "Parsing", "x"))
        return rows

    def _chains(self, rows, window=2.0):
        report = build_failure_graphs(rows, cascade_window_hours=window, min_cooccurrence=1)
        assert report is not None
        return {tuple(c.chain): c for c in report.cascade_chains}

    def test_repeated_three_step_pattern_counted(self):
        chains = self._chains(self._repeated(5))
        abc = chains[("Database", "Network", "Memory")]
        assert abc.occurrence_count == 5
        assert abc.confidence == 1.0
        assert abc.avg_latency_hours == 1.0
        assert chains[("Database", "Network")].occurrence_count == 5
        assert chains[("Database", "Network")].avg_latency_hours == 0.5
        assert chains[("Network", "Memory")].occurrence_count == 5

    def test_counts_greater_than_one_with_noise(self):
        chains = self._chains(self._repeated(6, noise=True))
        top = max(chains.values(), key=lambda c: c.occurrence_count)
        assert top.occurrence_count == 6
        # noise events are outside the window, so they never join a chain
        assert not any("Security" in k or "Parsing" in k for k in chains)

    def test_ranked_by_occurrence(self):
        rows = self._repeated(4)
        # an extra, rarer Database -> Memory pattern (twice) outside the others
        rows += [("t", 100.0, "Database", ""), ("t", 100.2, "Memory", ""),
                 ("t", 110.0, "Database", ""), ("t", 110.2, "Memory", "")]
        report = build_failure_graphs(rows, cascade_window_hours=2.0, min_cooccurrence=1)
        counts = [c.occurrence_count for c in report.cascade_chains]
        assert counts == sorted(counts, reverse=True)
        dm = next(c for c in report.cascade_chains if c.chain == ["Database", "Memory"])
        # 4 occurrences inside the A->B->C pattern (Memory within 2h of Database) + 2 extra
        assert dm.occurrence_count == 6
        assert dm.confidence == 1.0

    def test_confidence_reflects_trigger_frequency(self):
        rows = self._repeated(3)
        # Database occurring alone three more times lowers the chain's confidence
        rows += [("t", 200.0 + i * 10, "Database", "") for i in range(3)]
        chains = self._chains(rows)
        assert chains[("Database", "Network", "Memory")].occurrence_count == 3
        assert chains[("Database", "Network", "Memory")].confidence == 0.5

    def test_no_cascade_edges_means_no_chains(self):
        rows = [("t", i * 10.0, ["Database", "Network"][i % 2], "") for i in range(6)]
        report = build_failure_graphs(rows, cascade_window_hours=1.0, min_cooccurrence=1)
        assert report is not None and report.cascade_chains == []

    def test_unsorted_input_handled(self):
        rows = list(reversed(self._repeated(3)))
        chains = self._chains(rows)
        assert chains[("Database", "Network", "Memory")].occurrence_count == 3

    def test_insights_render_counts(self):
        report = build_failure_graphs(self._repeated(5), cascade_window_hours=2.0, min_cooccurrence=1)
        text = "\n".join(generate_graph_insights(report))
        assert "Occurs 5" in text


class TestGraphEdgeCases:
    def test_single_category_returns_none(self):
        rows = [("t", float(i), "Database", "") for i in range(6)]
        assert build_failure_graphs(rows) is None

    def test_empty_categories_become_uncategorized(self):
        rows = [("t", float(i), "" if i % 2 else "Database", "") for i in range(6)]
        report = build_failure_graphs(rows, min_cooccurrence=1)
        assert "Uncategorized" in {c.node for c in report.centrality}

    def test_networkx_failures_logged(self, monkeypatch, caplog):
        import modeler.graphs as g

        def boom(*a, **k):
            raise RuntimeError("nx broke")
        monkeypatch.setattr(g.nx, "pagerank", boom)
        monkeypatch.setattr(g.nx, "betweenness_centrality", boom)
        monkeypatch.setattr(g.nx, "diameter", boom)
        import networkx.algorithms.community as comm
        monkeypatch.setattr(comm, "louvain_communities", boom)
        report = build_failure_graphs(_make_categorized_list(), min_cooccurrence=1)
        assert report is not None
        assert report.communities == []
        for what in ("PageRank failed", "Betweenness centrality failed", "Louvain", "Diameter"):
            assert what in caplog.text

    def test_networkx_missing(self, monkeypatch):
        import modeler.graphs as g
        monkeypatch.setattr(g, "_HAS_NETWORKX", False)
        assert build_failure_graphs(_make_categorized_list()) is None
