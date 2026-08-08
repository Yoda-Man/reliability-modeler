"""
GraphQL schema for the Reliability Modeler.

Exposes failure graph data through a flexible GraphQL API built on Graphene.
Clients can query exactly the graph data they need — centrality scores,
cascade chains, community clusters, and raw graph structures for visualization.
"""

from __future__ import annotations

import graphene
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
        analysis_id=graphene.String(required=True, description="Analysis ID from /analyze"),
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

# In-memory store for categorized data keyed by analysis_id.
# In production this would be a database; for internal use, in-memory is fine.
_analysis_store: dict = {}


def store_analysis_data(analysis_id: str, categorized_list: list):
    """Store categorized failure data for later GraphQL queries."""
    _analysis_store[analysis_id] = categorized_list
    # Prune old entries (keep last 100)
    if len(_analysis_store) > 100:
        oldest = sorted(_analysis_store.keys())[0]
        del _analysis_store[oldest]


def _get_categorized_data(info, analysis_id: str) -> Optional[list]:
    """Retrieve stored categorized data for an analysis run."""
    return _analysis_store.get(analysis_id)


schema = graphene.Schema(query=Query)
