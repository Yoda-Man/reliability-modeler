"""
GraphQL schema for the Reliability Modeler.

Exposes failure graph data through a flexible GraphQL API built on Graphene.
Clients can query exactly the graph data they need — centrality scores,
cascade chains, community clusters, and raw graph structures for visualization.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import graphene
from graphql import GraphQLError, parse, validate
from graphql.error import GraphQLSyntaxError
from graphql.language import FieldNode
from graphql.validation import ValidationRule, specified_rules
from graphene.validation import depth_limit_validator

from modeler import config as rm_config
from modeler.graphs import FailureGraphReport, build_failure_graphs

logger = logging.getLogger(__name__)


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
    occurrence_count = graphene.Int(description="Number of distinct trigger events at which this cascade sequence recurred")
    avg_latency_hours = graphene.Float(description="Average time from first to last failure in the chain")
    confidence = graphene.Float(description="Occurrence count / number of events containing the trigger category")


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
    normalized_weight = graphene.Float(description="0-1: Jaccard similarity, or (single-label data) share of all temporal-proximity pairs")


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

# ═══════════════════════════════════════════════════════════════════════════════
# Limits & errors
# ═══════════════════════════════════════════════════════════════════════════════

CASCADE_WINDOW_RANGE = (1.0, 720.0)
MIN_COOCCURRENCE_RANGE = (1, 1000)
LIMIT_RANGE = (1, 100)
MAX_QUERY_DEPTH = 8
MEMORY_CACHE_SIZE = 100       # freshly stored analyses kept in memory (entry cap)
MEMORY_CACHE_MAX_EVENTS = 500_000  # ... and total events across them (size cap)
REPORT_CACHE_SIZE = 64        # built graph reports kept in memory
CROSS_ANALYSIS_CAP = 50       # most recent analyses examined by keystoneCategoriesAcross
MAX_GRAPH_FIELDS = 10         # graph-building root fields (incl. aliases) allowed per request
GRAPH_FIELDS = frozenset({"failureGraph", "keystoneCategories", "cascadeChains", "keystoneCategoriesAcross"})


class GraphQLUserError(Exception):
    """An error whose message is safe to return to the client verbatim."""


def _check_range(name: str, value, bounds) -> None:
    lo, hi = bounds
    if value is None or not (lo <= value <= hi):
        raise GraphQLUserError(f"{name} must be between {lo:g} and {hi:g}")


# ═══════════════════════════════════════════════════════════════════════════════
# Query
# ═══════════════════════════════════════════════════════════════════════════════

class Query(graphene.ObjectType):
    """Root GraphQL query for the Reliability Modeler."""

    failure_graph = graphene.Field(
        FailureGraphReportType,
        analysis_id=graphene.String(required=True, description="Analysis ID from /ingest/sentry"),
        cascade_window_hours=graphene.Float(default_value=2.0, description="1..720"),
        min_cooccurrence=graphene.Int(default_value=3, description="1..1000"),
        description="Get the full failure graph report for a specific analysis run",
    )

    keystone_categories = graphene.List(
        CentralityScoreType,
        analysis_id=graphene.String(required=True),
        limit=graphene.Int(default_value=10, description="1..100"),
        description="Get the most central (keystone) failure categories",
    )

    cascade_chains = graphene.List(
        CascadeChainType,
        analysis_id=graphene.String(required=True),
        limit=graphene.Int(default_value=10, description="1..100"),
        description="Get the most common failure cascade chains",
    )

    available_analyses = graphene.List(
        graphene.String,
        description="List all analysis IDs available for graph querying (memory + disk)",
    )

    keystone_categories_across = graphene.List(
        KeystoneFrequencyType,
        limit=graphene.Int(default_value=10, description="1..100"),
        description="Categories most consistently keystone across ALL analyses",
    )

    def resolve_available_analyses(self, info):
        return list_available_analyses()

    def resolve_keystone_categories_across(self, info, limit=10):
        _check_range("limit", limit, LIMIT_RANGE)
        freq: Dict[str, Dict[str, float]] = {}
        examined = 0

        # Cap to the most recent analyses to bound cost
        for aid in list_available_analyses()[-CROSS_ANALYSIS_CAP:]:
            report = get_failure_report(aid)
            if report is None:
                continue
            examined += 1
            for c in report.centrality:
                if c.is_keystone:
                    d = freq.setdefault(c.node, {"count": 0, "pagerank_sum": 0.0})
                    d["count"] += 1
                    d["pagerank_sum"] += c.pagerank

        result = [
            {
                "node": node,
                "keystone_count": int(d["count"]),
                "avg_pagerank": round(d["pagerank_sum"] / max(1, d["count"]), 6),
                "total_analyses": examined,
            }
            for node, d in freq.items()
        ]
        result.sort(key=lambda x: (-x["keystone_count"], -x["avg_pagerank"]))
        return result[:limit]

    def resolve_failure_graph(self, info, analysis_id, cascade_window_hours=2.0, min_cooccurrence=3):
        _check_range("cascadeWindowHours", cascade_window_hours, CASCADE_WINDOW_RANGE)
        _check_range("minCooccurrence", min_cooccurrence, MIN_COOCCURRENCE_RANGE)
        report = get_failure_report(analysis_id, cascade_window_hours, min_cooccurrence)
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
        _check_range("limit", limit, LIMIT_RANGE)
        report = get_failure_report(analysis_id)
        return report.centrality[:limit] if report else []

    def resolve_cascade_chains(self, info, analysis_id, limit=10):
        _check_range("limit", limit, LIMIT_RANGE)
        report = get_failure_report(analysis_id)
        return report.cascade_chains[:limit] if report else []


# ═══════════════════════════════════════════════════════════════════════════════
# Storage helpers
# ═══════════════════════════════════════════════════════════════════════════════

# Analysis IDs: "AN-YYYYMMDD-HHMMSS" (<= 2.8) or "AN-YYYYMMDD-HHMMSS-<6 hex>" (>= 2.9)
ANALYSIS_ID_RE = re.compile(r'^AN-\d{8}-\d{6}(-[0-9a-f]{6})?$')


class _LRU:
    """Tiny thread-safe bounded LRU mapping.

    Bounded by entry count (``maxsize``) and, when ``weigh`` is given, by the
    total weight of the values (``max_weight``), evicting least recently used
    entries first. A single value heavier than ``max_weight`` is not kept.
    """

    def __init__(self, maxsize: int, weigh=None, max_weight: Optional[int] = None):
        self.maxsize = maxsize
        self.weigh = weigh
        self.max_weight = max_weight
        self._data: "OrderedDict[Any, Any]" = OrderedDict()
        self._weights: Dict[Any, int] = {}
        self._total = 0
        self._lock = threading.Lock()

    def _pop(self, key) -> None:
        del self._data[key]
        self._total -= self._weights.pop(key, 0)

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key, value) -> None:
        with self._lock:
            if key in self._data:
                self._pop(key)
            weight = self.weigh(value) if self.weigh else 0
            if self.max_weight is not None and weight > self.max_weight:
                return
            self._data[key] = value
            self._weights[key] = weight
            self._total += weight
            while len(self._data) > self.maxsize or (
                    self.max_weight is not None and self._total > self.max_weight):
                self._pop(next(iter(self._data)))

    def discard_where(self, predicate) -> None:
        with self._lock:
            for k in [k for k in self._data if predicate(k)]:
                self._pop(k)

    def keys(self) -> List[Any]:
        with self._lock:
            return list(self._data.keys())

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._weights.clear()
            self._total = 0

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


# Freshly stored categorized data keyed by analysis_id, bounded by total event
# count. Everything is also persisted to OUTPUT_DIR/analyses/{id}.json so GraphQL
# can query historical analyses across restarts; disk reads are NOT cached here
# (the built reports are, in _report_cache).
_analysis_store = _LRU(MEMORY_CACHE_SIZE, weigh=len, max_weight=MEMORY_CACHE_MAX_EVENTS)
# Built graph reports keyed by (analysis_id, cascade_window_hours, min_cooccurrence).
_report_cache = _LRU(REPORT_CACHE_SIZE)


def _analysis_path(analysis_id: str):
    return rm_config.analyses_dir() / f"{analysis_id}.json"


def _report_key(analysis_id: str, cascade_window_hours: float = 2.0, min_cooccurrence: int = 3):
    return (analysis_id, float(cascade_window_hours), int(min_cooccurrence))


def store_analysis_data(analysis_id: str, categorized_list: list,
                        report: Optional[FailureGraphReport] = None) -> None:
    """Store categorized failure data (memory + disk) for later GraphQL queries.

    ``report``, if given, is the already-built report for the default
    parameters and primes the report cache.
    """
    _analysis_store.put(analysis_id, categorized_list)
    _report_cache.discard_where(lambda k: k[0] == analysis_id)
    if report is not None:
        _report_cache.put(_report_key(analysis_id), report)
    try:
        rm_config.atomic_write_json(_analysis_path(analysis_id), [list(r) for r in categorized_list])
    except (OSError, TypeError, ValueError):
        logger.warning("Failed to persist analysis data for %s", analysis_id, exc_info=True)


def forget_analyses(analysis_ids) -> None:
    """Drop analyses (e.g. after retention pruning) from the in-memory caches."""
    ids = set(analysis_ids)
    if not ids:
        return
    _analysis_store.discard_where(lambda k: k in ids)
    _report_cache.discard_where(lambda k: k[0] in ids)


def clear_caches() -> None:
    _analysis_store.clear()
    _report_cache.clear()


def get_categorized_data(analysis_id: str) -> Optional[list]:
    """Retrieve stored categorized data — memory first, then disk fallback."""
    # Validate the analysis ID format to prevent path traversal
    if not isinstance(analysis_id, str) or not ANALYSIS_ID_RE.match(analysis_id):
        return None
    cached = _analysis_store.get(analysis_id)
    if cached is not None:
        return cached
    disk_path = _analysis_path(analysis_id)
    if not disk_path.is_file():
        return None
    try:
        with open(disk_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Analysis file %s is unreadable or corrupt; ignoring it", disk_path, exc_info=True)
        return None
    if not isinstance(data, list):
        logger.warning("Analysis file %s has unexpected shape (%s); ignoring it", disk_path, type(data).__name__)
        return None
    return data


def get_failure_report(
    analysis_id: str,
    cascade_window_hours: float = 2.0,
    min_cooccurrence: int = 3,
    categorized: Optional[list] = None,
) -> Optional[FailureGraphReport]:
    """Return the graph report for an analysis, building it at most once per parameter set."""
    key = _report_key(analysis_id, cascade_window_hours, min_cooccurrence)
    cached = _report_cache.get(key)
    if cached is not None:
        return cached
    if categorized is None:
        categorized = get_categorized_data(analysis_id)
    if not categorized:
        return None
    report = build_failure_graphs(categorized, cascade_window_hours, min_cooccurrence)
    if report is not None:
        _report_cache.put(key, report)
    return report


def list_available_analyses() -> List[str]:
    """Return all analysis IDs available for GraphQL querying (memory + disk)."""
    ids = set(_analysis_store.keys())
    adir = rm_config.analyses_dir()
    if adir.exists():
        for f in adir.glob("*.json"):
            if ANALYSIS_ID_RE.match(f.stem):
                ids.add(f.stem)
    return sorted(ids)


schema = graphene.Schema(query=Query)


# ═══════════════════════════════════════════════════════════════════════════════
# Execution
# ═══════════════════════════════════════════════════════════════════════════════

class NoIntrospection(ValidationRule):
    """Reject schema introspection (__schema, __type) while allowing __typename."""

    def enter_field(self, node: FieldNode, *_args):
        name = node.name.value
        if name.startswith("__") and name != "__typename":
            self.report_error(GraphQLError(f"Cannot query '{name}': introspection is disabled.", node))


class GraphFieldLimit(ValidationRule):
    """Cap graph-building root fields per document (aliases count separately),
    so one request cannot fan out into many graph builds."""

    def __init__(self, context):
        super().__init__(context)
        self.count = 0

    def enter_field(self, node: FieldNode, *_args):
        parent = self.context.get_parent_type()
        if parent is None or parent.name != "Query" or node.name.value not in GRAPH_FIELDS:
            return
        self.count += 1
        if self.count == MAX_GRAPH_FIELDS + 1:
            self.report_error(GraphQLError(
                f"Too many graph fields in one request (max {MAX_GRAPH_FIELDS} of "
                f"{', '.join(sorted(GRAPH_FIELDS))}, aliases included).", node))


_EXTRA_RULES = (NoIntrospection, depth_limit_validator(max_depth=MAX_QUERY_DEPTH), GraphFieldLimit)


def _sanitize_error(err: GraphQLError) -> str:
    original = getattr(err, "original_error", None)
    if original is None or isinstance(original, GraphQLUserError):
        return err.message
    logger.error("GraphQL resolver error at %s: %r", err.path, original,
                 exc_info=(type(original), original, original.__traceback__))
    return "Internal error while resolving field" + (f" '{err.path[-1]}'" if err.path else "")


def execute_query(query: str, variables: Optional[dict] = None,
                  operation_name: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    """Parse, validate (incl. depth + introspection rules) and execute a query.

    Returns (response_body, ok). ``ok`` is False for syntax/validation errors,
    which the API maps to HTTP 400. Resolver errors are sanitized: messages
    from GraphQLUserError are returned verbatim, anything else is logged and
    replaced with a generic message.
    """
    try:
        document = parse(query)
    except GraphQLSyntaxError as e:
        return {"data": None, "errors": [e.message]}, False
    validation_errors = validate(schema.graphql_schema, document, [*specified_rules, *_EXTRA_RULES])
    if validation_errors:
        return {"data": None, "errors": [e.message for e in validation_errors]}, False
    result = schema.execute(query, variable_values=variables, operation_name=operation_name)
    body: Dict[str, Any] = {"data": result.data}
    if result.errors:
        body["errors"] = [_sanitize_error(e) for e in result.errors]
    return body, True
