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
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

import numpy as np

from .data import UNCATEGORIZED

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
    degree: int = 0                 # weighted degree (sum of co-occurrence edge weights)
    neighbors: int = 0              # number of distinct categories it is linked to
    is_keystone: bool = False       # top 20% by PageRank
    is_bridge: bool = False         # top 20% by betweenness


@dataclass
class CascadeChain:
    """A directional failure cascade: trigger → intermediary → ... → victim."""
    chain: List[str]
    occurrence_count: int           # distinct trigger events from which this sequence recurred
    avg_latency_hours: float        # mean time from the trigger to the last failure in the chain
    confidence: float               # occurrence_count / number of events containing the trigger


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
    weight: int                     # co-occurrence (or temporal-proximity) count
    normalized_weight: float        # 0-1: Jaccard similarity, or share of all proximity pairs


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
            cats = [UNCATEGORIZED]
        events.append((time_h, cats, desc))
    events.sort(key=lambda e: e[0])

    all_categories = sorted(set(c for _, cats, _ in events for c in cats))
    if len(all_categories) < 2:
        logger.warning("Need at least 2 distinct categories for graph analysis")
        return None

    # ── 1. Co-occurrence Graph (undirected, weighted) ─────────────────────
    G_cooc = nx.Graph()
    cooc_counter: Counter = Counter()
    cat_freq: Counter = Counter()   # number of events containing each category

    for _, cats, _ in events:
        cat_set = set(cats)
        cat_freq.update(cat_set)
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
        # A proximity count is a number of event *pairs*, which can far exceed
        # either category's event count, so Jaccard does not apply. Normalise
        # by the total number of proximity pairs instead (stays within 0-1).
        total_pairs = sum(cooc_counter.values()) or 1

        def normalized(_c1: str, _c2: str, count: int) -> float:
            return count / total_pairs
    else:
        def normalized(c1: str, c2: str, count: int) -> float:
            # Jaccard: events containing both / events containing either
            return count / max(1, cat_freq[c1] + cat_freq[c2] - count)

    norm_weights: Dict[Tuple[str, str], float] = {
        pair: round(normalized(pair[0], pair[1], count), 4) for pair, count in cooc_counter.items()
    }
    for (c1, c2), count in cooc_counter.items():
        if count >= min_cooccurrence:
            G_cooc.add_edge(c1, c2, weight=count, jaccard=norm_weights[(c1, c2)])

    # Ensure all categories are present as nodes (even isolates)
    for cat in all_categories:
        if cat not in G_cooc:
            G_cooc.add_node(cat)

    # ── 2. Cascade Graph (directed, weighted) ─────────────────────────────
    G_cascade = nx.DiGraph()
    cascade_counter: Counter = Counter()
    cascade_latency_sum: Dict[Tuple[str, str], float] = defaultdict(float)

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
                        cascade_latency_sum[(src, dst)] += gap

    total_cascades = sum(cascade_counter.values()) or 1
    for (src, dst), count in cascade_counter.items():
        if count >= 2:  # need at least 2 occurrences to be considered a pattern
            avg_lat = cascade_latency_sum[(src, dst)] / count
            confidence = count / total_cascades
            G_cascade.add_edge(src, dst, weight=count, avg_latency=round(float(avg_lat), 2),
                               confidence=round(confidence, 4))

    for cat in all_categories:
        if cat not in G_cascade:
            G_cascade.add_node(cat)

    # ── 3. Analytics ──────────────────────────────────────────────────────
    cascade_chains = _extract_cascade_chains(events, G_cascade, cascade_window_hours)
    return _compute_graph_analytics(G_cooc, G_cascade, all_categories,
                                    cascade_chains, cooc_counter, norm_weights)


def _compute_graph_analytics(
    G_cooc: "nx.Graph",
    G_cascade: "nx.DiGraph",
    all_categories: List[str],
    cascade_chains: List[CascadeChain],
    cooc_counter: Counter,
    norm_weights: Dict[Tuple[str, str], float],
) -> FailureGraphReport:

    # ── Centrality ────────────────────────────────────────────────────────
    try:
        pagerank = nx.pagerank(G_cooc, weight='weight')
    except Exception:
        logger.warning("PageRank failed on %d-node co-occurrence graph; using uniform scores",
                       G_cooc.number_of_nodes(), exc_info=True)
        pagerank = {c: 1.0 / max(1, len(all_categories)) for c in all_categories}

    try:
        betweenness = nx.betweenness_centrality(G_cooc, weight='weight', normalized=True)
    except Exception:
        logger.warning("Betweenness centrality failed on %d-node co-occurrence graph; using zeros",
                       G_cooc.number_of_nodes(), exc_info=True)
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
            neighbors=G_cooc.degree(cat) if cat in G_cooc else 0,
            is_keystone=bool(pagerank.get(cat, 0) >= pr_threshold),
            is_bridge=bool(betweenness.get(cat, 0) >= bw_threshold),
        ))
    centrality.sort(key=lambda x: x.pagerank, reverse=True)

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
    except Exception:
        logger.warning("Louvain community detection failed on %d-node graph; no communities reported",
                       G_cooc.number_of_nodes(), exc_info=True)

    # ── Co-occurrence Edges ───────────────────────────────────────────────
    cooc_edges = []
    for (c1, c2), count in cooc_counter.most_common(30):
        cooc_edges.append(CooccurrenceEdge(
            source=c1, target=c2, weight=count,
            normalized_weight=norm_weights[(c1, c2)],
        ))
    # Sort by normalized weight
    cooc_edges.sort(key=lambda e: e.normalized_weight, reverse=True)

    # ── Graph Metrics ─────────────────────────────────────────────────────
    try:
        diameter = nx.diameter(G_cooc) if nx.is_connected(G_cooc) else None
    except Exception:
        logger.warning("Diameter computation failed; reporting None", exc_info=True)
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
    events: List[Tuple[float, List[str], str]],
    G_cascade: "nx.DiGraph",
    cascade_window_hours: float,
    max_depth: int = 3,
    lookahead: int = 20,
    top_n: int = 10,
) -> List[CascadeChain]:
    """Count how often each cascade *sequence* recurs along the event timeline.

    A chain ``A -> B -> C`` occurs at trigger event ``i`` when ``i`` contains
    ``A`` and there are later events ``j`` (containing ``B``) and ``k``
    (containing ``C``) with ``0 < t_j - t_i <= window`` and
    ``0 < t_k - t_j <= window``. Only steps that are recurring cascade edges in
    ``G_cascade`` are followed, and categories never repeat within a chain.

    ``occurrence_count`` is the number of *distinct trigger events* at which
    the sequence occurs, so a pattern seen on five separate occasions counts
    five, regardless of how many overlapping continuations each occasion has.
    ``avg_latency_hours`` is the mean, over those occurrences, of the earliest
    time from trigger to the chain's final failure. ``confidence`` is
    ``occurrence_count`` divided by the number of events that contain the
    trigger category, i.e. how often the trigger is followed by this cascade.
    """
    if G_cascade.number_of_edges() == 0:
        return []

    times = [e[0] for e in events]
    trigger_totals: Counter = Counter()
    # chain -> [occurrence count, sum of latencies]; running totals keep memory
    # proportional to the number of distinct chains, not to events x chains.
    occurrences: Dict[Tuple[str, ...], List[float]] = defaultdict(lambda: [0, 0.0])

    for i, (t_i, cats_i, _) in enumerate(events):
        for start in set(cats_i):
            trigger_totals[start] += 1
            if not G_cascade.has_node(start) or G_cascade.out_degree(start) == 0:
                continue
            # frontier: chain tuple -> sorted event indices where it can end
            frontier: Dict[Tuple[str, ...], List[int]] = {(start,): [i]}
            found: Dict[Tuple[str, ...], float] = {}
            for _depth in range(1, max_depth):
                next_frontier: Dict[Tuple[str, ...], Set[int]] = defaultdict(set)
                for chain, end_indices in frontier.items():
                    last = chain[-1]
                    successors = set(G_cascade.successors(last)) - set(chain)
                    if not successors:
                        continue
                    for k in end_indices:
                        t_k = times[k]
                        for j in range(k + 1, min(k + 1 + lookahead, len(events))):
                            gap = times[j] - t_k
                            if gap > cascade_window_hours:
                                break
                            if gap <= 0:
                                continue
                            for dst in successors.intersection(events[j][1]):
                                next_frontier[chain + (dst,)].add(j)
                frontier = {c: sorted(idx) for c, idx in next_frontier.items()}
                for chain, end_indices in frontier.items():
                    found[chain] = times[end_indices[0]] - t_i
                if not frontier:
                    break
            for chain, latency in found.items():
                acc = occurrences[chain]
                acc[0] += 1
                acc[1] += latency

    ranked = sorted(
        occurrences.items(),
        key=lambda kv: (-kv[1][0], -len(kv[0]), kv[1][1] / kv[1][0], kv[0]),
    )[:top_n]
    return [
        CascadeChain(
            chain=list(chain),
            occurrence_count=int(count),
            avg_latency_hours=round(float(lat_sum / count), 2),
            confidence=round(count / max(1, trigger_totals[chain[0]]), 4),
        )
        for chain, (count, lat_sum) in ranked
    ]


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
            noun = "category" if c.neighbors == 1 else "categories"
            lines.append(f"  • {c.node}{tag} — PageRank {c.pagerank:.4f}, "
                         f"connected to {c.neighbors} other {noun}")
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
