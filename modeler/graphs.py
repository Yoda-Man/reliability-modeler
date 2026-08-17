"""
Failure Graph Analytics — NetworkX-powered structural insights.

Provides management with unrivaled fault intelligence through graph theory:
  - Co-occurrence graphs: which failure categories happen together
  - Cascade graphs: which failures predictably trigger others
  - Centrality rankings: which categories are keystones / bridges
  - Community detection: natural fault clusters in the system
  - Cascade chain extraction: the most common failure sequences

All graphs are built from the same categorized failure data used by the rest
of the pipeline. Import this module and call build_failure_graphs() to get
a complete FailureGraphReport.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set

import numpy as np

logger = logging.getLogger(__name__)

# ── Try importing networkx — it's required for graph analytics ───────────────
try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False
    logger.warning("networkx not installed — graph analytics disabled. Install with: pip install networkx")


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CentralityScore:
    """PageRank / betweenness score for a single node."""
    node: str
    pagerank: float = 0.0
    betweenness: float = 0.0
    degree: int = 0
    is_keystone: bool = False       # top 20% by PageRank
    is_bridge: bool = False         # top 20% by betweenness


@dataclass
class CascadeChain:
    """A directional failure cascade: trigger → intermediary → ... → victim."""
    chain: List[str]
    occurrence_count: int
    avg_latency_hours: float
    confidence: float               # occurrence_count / total_cascades


@dataclass
class CommunityCluster:
    """A community of related failure categories detected by Louvain."""
    cluster_id: int
    members: List[str]
    size: int
    internal_density: float         # edges inside / possible edges inside


@dataclass
class CooccurrenceEdge:
    """A weighted edge between two failure categories."""
    source: str
    target: str
    weight: int                     # co-occurrence count
    normalized_weight: float        # Jaccard similarity
    temporal_proximity_hours: float # median time between co-occurrences


@dataclass
class GraphMetrics:
    """Top-level metrics about the failure graph."""
    num_categories: int
    num_cooccurrence_edges: int
    num_cascade_edges: int
    num_communities: int
    graph_density: float
    avg_clustering_coefficient: float
    is_connected: bool
    diameter: Optional[int]         # None if disconnected


@dataclass
class FailureGraphReport:
    """Complete graph analysis report."""
    metrics: GraphMetrics
    centrality: List[CentralityScore]           # all categories ranked by PageRank
    cascade_chains: List[CascadeChain]          # top 10 failure cascades
    communities: List[CommunityCluster]         # Louvain communities
    cooccurrence_edges: List[CooccurrenceEdge]  # top 20 co-occurrence edges
    # Raw graph data for visualization (node-link JSON)
    graph_json: Optional[Dict] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Graph Builders
# ═══════════════════════════════════════════════════════════════════════════════

def build_failure_graphs(
    categorized_list: List[Tuple],
    cascade_window_hours: float = 2.0,
    min_cooccurrence: int = 3,
) -> Optional[FailureGraphReport]:
    """
    Build all failure graphs from categorized failure data.

    Args:
        categorized_list: List of (dt_iso, time_hours, categories_str, description) tuples
        cascade_window_hours: Maximum time gap to consider a cascade edge (default 2h)
        min_cooccurrence: Minimum co-occurrence count for an edge to be included

    Returns:
        FailureGraphReport with all analytics, or None if networkx is unavailable
    """
    if not _HAS_NETWORKX:
        return None
    if len(categorized_list) < 5:
        logger.warning("Too few failures for meaningful graph analysis (need ≥5)")
        return None

    # ── Parse events ─────────────────────────────────────────────────────
    events: List[Tuple[float, List[str], str]] = []
    for row in categorized_list:
        time_h = float(row[1])
        cats = [c.strip() for c in str(row[2]).split(",") if c.strip()]
        desc = str(row[3]) if len(row) > 3 else ""
        if not cats:
            cats = ["Uncategorized"]
        events.append((time_h, cats, desc))

    all_categories = sorted(set(c for _, cats, _ in events for c in cats))
    if len(all_categories) < 2:
        logger.warning("Need at least 2 distinct categories for graph analysis")
        return None

    # ── 1. Co-occurrence Graph (undirected, weighted) ─────────────────────
    G_cooc = nx.Graph()
    cooc_counter: Counter = Counter()
    cat_sets: List[Set[str]] = []

    for _, cats, _ in events:
        cat_set = set(cats)
        cat_sets.append(cat_set)
        for i, c1 in enumerate(sorted(cat_set)):
            for c2 in sorted(cat_set)[i + 1:]:
                pair = tuple(sorted([c1, c2]))
                cooc_counter[pair] += 1

    # If single-label data produces zero co-occurrence edges, fall back to
    # temporal-proximity edges: categories that appear close in time are linked.
    if len(cooc_counter) == 0:
        logger.info("No co-occurring categories found (single-label data). "
                     "Building temporal-proximity graph instead.")
        temporal_proximity: Counter = Counter()
        proximity_window = cascade_window_hours * 4  # wider window for proximity
        for i in range(len(events) - 1):
            ti, cats_i, _ = events[i]
            for j in range(i + 1, min(i + 50, len(events))):
                tj, cats_j, _ = events[j]
                if tj - ti > proximity_window:
                    break
                for c1 in cats_i:
                    for c2 in cats_j:
                        if c1 != c2:
                            pair = tuple(sorted([c1, c2]))
                            temporal_proximity[pair] += 1
        cooc_counter = temporal_proximity
        logger.info(f"Built {len(cooc_counter)} temporal-proximity edges "
                     f"({proximity_window:.0f}h window)")

    for (c1, c2), count in cooc_counter.items():
        if count >= min_cooccurrence:
            set_a = sum(1 for s in cat_sets if c1 in s)
            set_b = sum(1 for s in cat_sets if c2 in s)
            jaccard = count / max(1, set_a + set_b - count)
            G_cooc.add_edge(c1, c2, weight=count, jaccard=round(jaccard, 4))

    # Ensure all categories are present as nodes (even isolates)
    for cat in all_categories:
        if cat not in G_cooc:
            G_cooc.add_node(cat)

    # ── 2. Cascade Graph (directed, weighted) ─────────────────────────────
    G_cascade = nx.DiGraph()
    cascade_counter: Counter = Counter()
    cascade_latencies: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    for i in range(len(events) - 1):
        ti, cats_i, _ = events[i]
        for j in range(i + 1, min(i + 20, len(events))):  # look ahead up to 20 events
            tj, cats_j, _ = events[j]
            gap = tj - ti
            if gap > cascade_window_hours:
                break
            if gap <= 0:
                continue
            for src in cats_i:
                for dst in cats_j:
                    if src != dst:
                        cascade_counter[(src, dst)] += 1
                        cascade_latencies[(src, dst)].append(gap)

    total_cascades = sum(cascade_counter.values()) or 1
    for (src, dst), count in cascade_counter.items():
        if count >= 2:  # need at least 2 occurrences to be considered a pattern
            avg_lat = np.mean(cascade_latencies[(src, dst)])
            confidence = count / total_cascades
            G_cascade.add_edge(src, dst, weight=count, avg_latency=round(float(avg_lat), 2),
                               confidence=round(confidence, 4))

    for cat in all_categories:
        if cat not in G_cascade:
            G_cascade.add_node(cat)

    # ── 3. Analytics ──────────────────────────────────────────────────────
    return _compute_graph_analytics(G_cooc, G_cascade, all_categories,
                                    cascade_counter, cascade_latencies,
                                    cooc_counter, cat_sets, total_cascades)


def _compute_graph_analytics(
    G_cooc: "nx.Graph",
    G_cascade: "nx.DiGraph",
    all_categories: List[str],
    cascade_counter: Counter,
    cascade_latencies: Dict,
    cooc_counter: Counter,
    cat_sets: List[Set[str]],
    total_cascades: int,
) -> FailureGraphReport:

    # ── Centrality ────────────────────────────────────────────────────────
    try:
        pagerank = nx.pagerank(G_cooc, weight='weight')
    except Exception:
        pagerank = {c: 1.0 / max(1, len(all_categories)) for c in all_categories}

    try:
        betweenness = nx.betweenness_centrality(G_cooc, weight='weight', normalized=True)
    except Exception:
        betweenness = {c: 0.0 for c in all_categories}

    pr_threshold = np.percentile(list(pagerank.values()), 80) if pagerank else 0
    bw_threshold = np.percentile(list(betweenness.values()), 80) if betweenness else 0

    centrality = []
    for cat in all_categories:
        deg = G_cooc.degree(cat, weight='weight') if cat in G_cooc else 0
        centrality.append(CentralityScore(
            node=cat,
            pagerank=round(pagerank.get(cat, 0), 6),
            betweenness=round(betweenness.get(cat, 0), 6),
            degree=int(deg),
            is_keystone=bool(pagerank.get(cat, 0) >= pr_threshold),
            is_bridge=bool(betweenness.get(cat, 0) >= bw_threshold),
        ))
    centrality.sort(key=lambda x: x.pagerank, reverse=True)

    # ── Cascade Chains (depth-3 paths from cascade graph) ─────────────────
    cascade_chains = _extract_cascade_chains(G_cascade, cascade_counter,
                                              cascade_latencies, total_cascades)

    # ── Community Detection (Louvain) ─────────────────────────────────────
    communities = []
    try:
        from networkx.algorithms.community import louvain_communities
        raw_communities = louvain_communities(G_cooc, weight='weight', seed=42)
        for cid, members in enumerate(raw_communities):
            members_list = sorted(members)
            if len(members_list) < 1:
                continue
            # Internal density: actual edges inside / possible edges inside
            sub = G_cooc.subgraph(members_list)
            possible = len(members_list) * (len(members_list) - 1) / 2
            actual = sub.number_of_edges()
            density = actual / max(1, possible)
            communities.append(CommunityCluster(
                cluster_id=cid,
                members=members_list,
                size=len(members_list),
                internal_density=round(density, 4),
            ))
        communities.sort(key=lambda c: c.size, reverse=True)
    except Exception as e:
        logger.debug(f"Community detection skipped: {e}")

    # ── Co-occurrence Edges ───────────────────────────────────────────────
    cooc_edges = []
    for (c1, c2), count in cooc_counter.most_common(30):
        set_a = sum(1 for s in cat_sets if c1 in s)
        set_b = sum(1 for s in cat_sets if c2 in s)
        jaccard = count / max(1, set_a + set_b - count)
        cooc_edges.append(CooccurrenceEdge(
            source=c1, target=c2, weight=count,
            normalized_weight=round(jaccard, 4),
            temporal_proximity_hours=0.0,  # not computed at edge level
        ))
    # Sort by Jaccard similarity
    cooc_edges.sort(key=lambda e: e.normalized_weight, reverse=True)

    # ── Graph Metrics ─────────────────────────────────────────────────────
    try:
        diameter = nx.diameter(G_cooc) if nx.is_connected(G_cooc) else None
    except Exception:
        diameter = None

    metrics = GraphMetrics(
        num_categories=len(all_categories),
        num_cooccurrence_edges=G_cooc.number_of_edges(),
        num_cascade_edges=G_cascade.number_of_edges(),
        num_communities=len(communities),
        graph_density=round(nx.density(G_cooc), 4),
        avg_clustering_coefficient=round(nx.average_clustering(G_cooc, weight='weight'), 4),
        is_connected=nx.is_connected(G_cooc),
        diameter=diameter,
    )

    # ── Graph JSON for Visualization ──────────────────────────────────────
    graph_json = {
        "nodes": [{"id": c, "pagerank": pagerank.get(c, 0),
                    "degree": int(G_cooc.degree(c, weight='weight')),
                    "community": next((cm.cluster_id for cm in communities if c in cm.members), -1)}
                  for c in all_categories],
        "edges": [{"source": u, "target": v, "weight": d["weight"], "jaccard": d["jaccard"]}
                  for u, v, d in G_cooc.edges(data=True)],
        "cascade_edges": [{"source": u, "target": v, "weight": d["weight"],
                            "confidence": d["confidence"], "avg_latency": d["avg_latency"]}
                          for u, v, d in G_cascade.edges(data=True)],
    }

    return FailureGraphReport(
        metrics=metrics,
        centrality=centrality,
        cascade_chains=cascade_chains,
        communities=communities,
        cooccurrence_edges=cooc_edges[:20],
        graph_json=graph_json,
    )


def _extract_cascade_chains(
    G_cascade: "nx.DiGraph",
    cascade_counter: Counter,
    cascade_latencies: Dict,
    total_cascades: int,
    max_depth: int = 3,
) -> List[CascadeChain]:
    """Extract the most common failure cascade chains from the directed graph."""
    chains: Dict[Tuple[str, ...], List[float]] = defaultdict(list)

    # BFS from each node to find paths
    for src in G_cascade.nodes():
        _dfs_paths(G_cascade, src, [], set(), max_depth, cascade_counter,
                    cascade_latencies, chains)

    result = []
    for chain_tuple, latencies in sorted(chains.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        chain_list = list(chain_tuple)
        occ = len(latencies)
        result.append(CascadeChain(
            chain=chain_list,
            occurrence_count=occ,
            avg_latency_hours=round(float(np.mean(latencies)), 2),
            confidence=round(occ / max(1, total_cascades), 4),
        ))
    return result


def _dfs_paths(
    G: "nx.DiGraph",
    node: str,
    path: List[str],
    visited: Set[str],
    max_depth: int,
    cascade_counter: Counter,
    cascade_latencies: Dict,
    chains: Dict[Tuple[str, ...], List[float]],
):
    """Depth-first search to collect cascade paths."""
    if len(path) >= max_depth:
        return
    if node in visited:
        return

    new_path = path + [node]
    new_visited = visited | {node}

    if len(new_path) >= 2:
        # Record this path as a cascade chain
        chain_key = tuple(new_path)
        # Sum the latencies along the edges
        total_lat = 0.0
        valid = True
        for i in range(len(new_path) - 1):
            edge = (new_path[i], new_path[i + 1])
            lats = cascade_latencies.get(edge, [])
            if lats:
                total_lat += np.mean(lats)
            else:
                valid = False
                break
        if valid:
            chains[chain_key].append(total_lat)

    for successor in G.successors(node):
        _dfs_paths(G, successor, new_path, new_visited, max_depth,
                    cascade_counter, cascade_latencies, chains)


# ═══════════════════════════════════════════════════════════════════════════════
# Insight Summary Generator
# ═══════════════════════════════════════════════════════════════════════════════

def generate_graph_insights(report: FailureGraphReport) -> List[str]:
    """
    Generate plain-English management insights from a graph report.
    Returns a list of bullet-point strings ready for human consumption.
    """
    if report is None:
        return ["⚠️  Graph analytics unavailable — install networkx: pip install networkx"]

    lines = []
    lines.append("=== Failure Graph Intelligence ===\n")

    # Keystone categories
    keystones = [c for c in report.centrality if c.is_keystone]
    if keystones:
        lines.append("🔑 Keystone Failure Categories (highest systemic impact):")
        for c in keystones[:5]:
            tag = " [BRIDGE]" if c.is_bridge else ""
            lines.append(f"  • {c.node}{tag} — PageRank {c.pagerank:.4f}, "
                         f"connected to {c.degree} other categories")
        lines.append("   → Fixing these will have the greatest ripple effect.\n")

    # Cascade chains
    if report.cascade_chains:
        lines.append("🔗 Most Common Failure Cascades (failures that trigger others):")
        for cc in report.cascade_chains[:5]:
            arrow = " → ".join(cc.chain)
            lines.append(f"  • {arrow}")
            lines.append(f"    Occurs {cc.occurrence_count}×, avg latency {cc.avg_latency_hours:.1f}h, "
                         f"confidence {cc.confidence*100:.1f}%")
        lines.append("   → These patterns reveal which fixes prevent downstream incidents.\n")

    # Communities
    non_singleton = [c for c in report.communities if c.size > 1]
    if non_singleton:
        lines.append("🧩 Natural Fault Clusters (failures that belong together):")
        for cm in non_singleton[:5]:
            members_str = ", ".join(cm.members)
            lines.append(f"  • Cluster {cm.cluster_id} ({cm.size} categories, "
                         f"density {cm.internal_density:.2f}): {members_str}")
        lines.append("   → Each cluster may point to a shared root cause or architectural weakness.\n")
    elif report.communities:
        lines.append("🧩 Fault Categories are largely independent (no strong clusters detected).\n")

    # Graph health
    m = report.metrics
    connectivity = "connected" if m.is_connected else "disconnected"
    diam_str = f"diameter={m.diameter}" if m.diameter else "N/A (disconnected)"
    lines.append("📊 Graph Health Metrics:")
    lines.append(f"  • {m.num_categories} categories, {m.num_cooccurrence_edges} co-occurrence edges, "
                 f"{m.num_cascade_edges} cascade edges")
    lines.append(f"  • Graph is {connectivity}, {diam_str}, "
                 f"density={m.graph_density:.4f}, clustering={m.avg_clustering_coefficient:.4f}")
    lines.append(f"  • {m.num_communities} natural communities detected")

    return lines
