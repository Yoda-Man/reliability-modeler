"""
GraphQL schema for the Reliability Modeler.

Exposes failure graph data through a flexible GraphQL API built on Graphene.
Clients can query exactly the graph data they need — centrality scores,
cascade chains, community clusters, and raw graph structures for visualization.
"""

from __future__ import annotations

import graphene
import logging
from typing import List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════════════

class CentralityScoreType(graphene.ObjectType):
    node = graphene.String(description="Category name")
    pagerank = graphene.Float(description="PageRank centrality (0-1)")
    betweenness = graphene.Float(description="Betweenness centrality (0-1)")
    degree = graphene.Int(description="Weighted degree in co-occurrence graph")
    is_keystone = graphene.Boolean(description="Top 20% by PageRank")
    is_bridge = graphene.Boolean(description="Top 20% by betweenness")


class CascadeChainType(graphene.ObjectType):
    chain = graphene.List(graphene.String, description="Ordered list of categories in the cascade")
    occurrence_count = graphene.Int(description="How many times this cascade was observed")
    avg_latency_hours = graphene.Float(description="Average time from first to last failure in the chain")
    confidence = graphene.Float(description="Occurrence count / total cascades")


class CommunityClusterType(graphene.ObjectType):
    cluster_id = graphene.Int()
    members = graphene.List(graphene.String)
    size = graphene.Int()
    internal_density = graphene.Float(description="Edges inside / possible edges inside")


class KeystoneFrequencyType(graphene.ObjectType):
    node = graphene.String(description="Category name")
    keystone_count = graphene.Int(description="Number of analyses where this category was keystone")
    avg_pagerank = graphene.Float(description="Average PageRank across all analyses")
    total_analyses = graphene.Int(description="Total analyses examined")


class CooccurrenceEdgeType(graphene.ObjectType):
    source = graphene.String()
    target = graphene.String()
    weight = graphene.Int(description="Co-occurrence count")
    normalized_weight = graphene.Float(description="Jaccard similarity (0-1)")


class GraphMetricsType(graphene.ObjectType):
    num_categories = graphene.Int()
    num_cooccurrence_edges = graphene.Int()
    num_cascade_edges = graphene.Int()
    num_communities = graphene.Int()
    graph_density = graphene.Float()
    avg_clustering_coefficient = graphene.Float()
    is_connected = graphene.Boolean()
    diameter = graphene.Int()


class GraphNodeType(graphene.ObjectType):
    id = graphene.String()
    pagerank = graphene.Float()
    degree = graphene.Int()
    community = graphene.Int()


class GraphEdgeType(graphene.ObjectType):
    source = graphene.String()
    target = graphene.String()
    weight = graphene.Int()
    jaccard = graphene.Float()


class CascadeEdgeType(graphene.ObjectType):
    source = graphene.String()
    target = graphene.String()
    weight = graphene.Int()
    confidence = graphene.Float()
    avg_latency = graphene.Float()


class GraphJSONType(graphene.ObjectType):
    nodes = graphene.List(GraphNodeType)
    edges = graphene.List(GraphEdgeType)
    cascade_edges = graphene.List(CascadeEdgeType)


class FailureGraphReportType(graphene.ObjectType):
    """Complete graph analysis report."""
    graph_metrics = graphene.Field(GraphMetricsType)
    centrality_scores = graphene.List(CentralityScoreType)
    cascade_chains = graphene.List(CascadeChainType)
    communities = graphene.List(CommunityClusterType)
    cooccurrence_edges = graphene.List(CooccurrenceEdgeType)
    graph_json = graphene.Field(GraphJSONType)


# ═══════════════════════════════════════════════════════════════════════════════
# Query
# ═══════════════════════════════════════════════════════════════════════════════

class Query(graphene.ObjectType):
    """Root GraphQL query for the Reliability Modeler."""

    failure_graph = graphene.Field(
        FailureGraphReportType,
        analysis_id=graphene.String(required=True, description="Analysis ID from /ingest/sentry"),
        cascade_window_hours=graphene.Float(default_value=2.0),
        min_cooccurrence=graphene.Int(default_value=3),
        description="Get the full failure graph report for a specific analysis run",
    )

    keystone_categories = graphene.List(
        CentralityScoreType,
        analysis_id=graphene.String(required=True),
        limit=graphene.Int(default_value=10),
        description="Get the most central (keystone) failure categories",
    )

    cascade_chains = graphene.List(
        CascadeChainType,
        analysis_id=graphene.String(required=True),
        limit=graphene.Int(default_value=10),
        description="Get the most common failure cascade chains",
    )

    available_analyses = graphene.List(
        graphene.String,
        description="List all analysis IDs available for graph querying (memory + disk)",
    )

    keystone_categories_across = graphene.List(
        KeystoneFrequencyType,
        limit=graphene.Int(default_value=10),
        description="Categories most consistently keystone across ALL analyses",
    )

    def resolve_available_analyses(self, info):
        return list_available_analyses()

    def resolve_keystone_categories_across(self, info, limit=10):
        from modeler.graphs import build_failure_graphs
        from collections import defaultdict

        freq = defaultdict(lambda: {"count": 0, "pagerank_sum": 0.0})
        examined = 0

        for aid in list_available_analyses():
            categorized = _get_categorized_data(info, aid)
            if not categorized:
                continue
            report = build_failure_graphs(categorized)
            if report is None:
                continue
            examined += 1
            for c in report.centrality:
                if c.is_keystone:
                    freq[c.node]["count"] += 1
                    freq[c.node]["pagerank_sum"] += c.pagerank

        result = []
        for node, d in freq.items():
            result.append({
                "node": node,
                "keystone_count": d["count"],
                "avg_pagerank": round(d["pagerank_sum"] / max(1, d["count"]), 6),
                "total_analyses": examined,
            })

        result.sort(key=lambda x: (-x["keystone_count"], -x["avg_pagerank"]))
        return result[:limit]

    def resolve_failure_graph(self, info, analysis_id, cascade_window_hours=2.0, min_cooccurrence=3):
        from modeler.graphs import build_failure_graphs
        categorized = _get_categorized_data(info, analysis_id)
        if categorized is None:
            return None
        report = build_failure_graphs(categorized, cascade_window_hours, min_cooccurrence)
        if report is None:
            return None
        return {
            "graph_metrics": report.metrics,
            "centrality_scores": report.centrality,
            "cascade_chains": report.cascade_chains,
            "communities": report.communities,
            "cooccurrence_edges": report.cooccurrence_edges,
            "graph_json": report.graph_json,
        }

    def resolve_keystone_categories(self, info, analysis_id, limit=10):
        from modeler.graphs import build_failure_graphs
        categorized = _get_categorized_data(info, analysis_id)
        if categorized is None:
            return []
        report = build_failure_graphs(categorized)
        if report is None:
            return []
        return report.centrality[:limit]

    def resolve_cascade_chains(self, info, analysis_id, limit=10):
        from modeler.graphs import build_failure_graphs
        categorized = _get_categorized_data(info, analysis_id)
        if categorized is None:
            return []
        report = build_failure_graphs(categorized)
        if report is None:
            return []
        return report.cascade_chains[:limit]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

import json
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BASE_DIR.parent.parent
_ANALYSES_DIR = _ROOT_DIR / "output" / "analyses"

# In-memory cache of categorized data keyed by analysis_id.
# Persisted to output/analyses/{id}.json so GraphQL can query historical
# analyses across restarts.
_analysis_store: dict = {}


def store_analysis_data(analysis_id: str, categorized_list: list):
    """Store categorized failure data (memory + disk) for later GraphQL queries."""
    _analysis_store[analysis_id] = categorized_list
    # Prune in-memory cache (keep last 100); disk copy remains
    if len(_analysis_store) > 100:
        oldest = sorted(_analysis_store.keys())[0]
        del _analysis_store[oldest]

    # Persist to disk for historical queries
    try:
        _ANALYSES_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _ANALYSES_DIR / f".{analysis_id}.tmp"
        final = _ANALYSES_DIR / f"{analysis_id}.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(categorized_list, f)
        tmp.replace(final)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to persist analysis data: {e}")


def _get_categorized_data(info, analysis_id: str) -> Optional[list]:
    """Retrieve stored categorized data — memory first, then disk fallback."""
    if analysis_id in _analysis_store:
        return _analysis_store[analysis_id]
    # Disk fallback (survives restart)
    disk_path = _ANALYSES_DIR / f"{analysis_id}.json"
    if disk_path.exists():
        try:
            with open(disk_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _analysis_store[analysis_id] = data  # warm the cache
            return data
        except Exception:
            return None
    return None


def list_available_analyses() -> List[str]:
    """Return all analysis IDs available for GraphQL querying (memory + disk)."""
    ids = set(_analysis_store.keys())
    if _ANALYSES_DIR.exists():
        for f in _ANALYSES_DIR.glob("*.json"):
            ids.add(f.stem)
    return sorted(ids)


schema = graphene.Schema(query=Query)
