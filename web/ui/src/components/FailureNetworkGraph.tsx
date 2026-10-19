'use client';

import React, { useMemo, useState } from 'react';
import { Share2 } from 'lucide-react';
import type { GraphReport } from '@/lib/types';

type GraphJson = NonNullable<GraphReport['graph_json']>;

const SIZE = 560;
const MAX_CASCADES = 25; // the strongest cascades carry the story; more is clutter

export interface NodePosition { id: string; x: number; y: number; r: number; community: number; pagerank: number; degree: number }

/** Place nodes on a circle, grouped by community and ordered by PageRank, sized by PageRank. */
export function layoutNetwork(graph: GraphJson, size = SIZE): NodePosition[] {
    const nodes = [...graph.nodes].sort((a, b) => a.community - b.community || b.pagerank - a.pagerank);
    const maxPr = Math.max(...nodes.map(n => n.pagerank), 1e-9);
    const c = size / 2;
    const ring = c - 70; // leave room for labels outside the ring
    return nodes.map((n, i) => {
        const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
        return {
            id: n.id, community: n.community, pagerank: n.pagerank, degree: n.degree,
            x: c + ring * Math.cos(angle), y: c + ring * Math.sin(angle),
            r: 7 + 15 * Math.sqrt(n.pagerank / maxPr),
        };
    });
}

/** Quadratic curve bent to the left of travel, so A→B and B→A cascades take opposite sides. */
function curve(a: NodePosition, b: NodePosition): string {
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const bend = Math.min(60, d * 0.2);
    const qx = (a.x + b.x) / 2 - (dy / d) * bend, qy = (a.y + b.y) / 2 + (dx / d) * bend;
    // Start and stop at the circles' edges so arrowheads stay visible.
    const sx = qx - a.x, sy = qy - a.y, sl = Math.hypot(sx, sy) || 1;
    const ex = b.x - qx, ey = b.y - qy, el = Math.hypot(ex, ey) || 1;
    return `M${a.x + (sx / sl) * a.r},${a.y + (sy / sl) * a.r} Q${qx},${qy} ${b.x - (ex / el) * (b.r + 3)},${b.y - (ey / el) * (b.r + 3)}`;
}

export default function FailureNetworkGraph({ graphReport, palette }: { graphReport: GraphReport; palette: string[] }) {
    const graph = graphReport.graph_json;
    const [showCooc, setShowCooc] = useState(true);
    const [showCascades, setShowCascades] = useState(true);
    const [hovered, setHovered] = useState<string | null>(null);
    const [selected, setSelected] = useState<string | null>(null);

    const positions = useMemo(() => (graph ? layoutNetwork(graph) : []), [graph]);
    const byId = useMemo(() => new Map(positions.map(p => [p.id, p])), [positions]);
    const cascades = useMemo(
        () => (graph ? [...graph.cascade_edges].sort((a, b) => b.confidence - a.confidence).slice(0, MAX_CASCADES) : []),
        [graph],
    );
    const keystones = useMemo(() => new Set(graphReport.keystone_categories.map(k => k.name)), [graphReport]);
    const bridges = useMemo(
        () => new Set(graphReport.keystone_categories.filter(k => k.is_bridge).map(k => k.name)),
        [graphReport],
    );

    if (!graph || graph.nodes.length === 0) return null;

    const focus = hovered ?? selected;
    const touches = (e: { source: string; target: string }) => !focus || e.source === focus || e.target === focus;
    const neighbours = new Set<string>();
    if (focus) for (const e of [...graph.edges, ...cascades]) {
        if (e.source === focus) neighbours.add(e.target);
        if (e.target === focus) neighbours.add(e.source);
    }
    const color = (community: number) => (community < 0 ? '#64748b' : palette[community % palette.length]);
    const maxCoocWeight = Math.max(...graph.edges.map(e => e.weight), 1);
    const detail = selected ? byId.get(selected) : undefined;
    const outgoing = selected ? cascades.filter(e => e.source === selected) : [];
    const incoming = selected ? cascades.filter(e => e.target === selected) : [];

    return (
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                    <Share2 className="w-4 h-4 text-indigo-400" />
                    <span>Failure Network</span>
                    <span className="text-[10px] text-slate-500 font-normal">
                        {graph.nodes.length} categories · {graphReport.num_communities} communities · click a category for details
                    </span>
                </h3>
                <div className="flex items-center space-x-4 text-xs text-slate-400">
                    <label className="flex items-center space-x-1.5 cursor-pointer">
                        <input type="checkbox" checked={showCooc} onChange={e => setShowCooc(e.target.checked)} />
                        <span>Co-occurrence</span>
                    </label>
                    <label className="flex items-center space-x-1.5 cursor-pointer">
                        <input type="checkbox" checked={showCascades} onChange={e => setShowCascades(e.target.checked)} />
                        <span>Cascades (top {Math.min(MAX_CASCADES, graph.cascade_edges.length)})</span>
                    </label>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full lg:col-span-2 max-h-[560px]" role="img"
                    aria-label={`Failure network of ${graph.nodes.length} categories`}>
                    <defs>
                        <marker id="rm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M0,0 L10,5 L0,10 z" fill="#f59e0b" />
                        </marker>
                    </defs>

                    {showCooc && graph.edges.map(e => {
                        const a = byId.get(e.source), b = byId.get(e.target);
                        if (!a || !b) return null;
                        return (
                            <line key={`c-${e.source}-${e.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                                stroke="#94a3b8" strokeOpacity={touches(e) ? 0.15 + 0.5 * (e.weight / maxCoocWeight) : 0.04}
                                strokeWidth={1 + 4 * (e.weight / maxCoocWeight)} />
                        );
                    })}

                    {showCascades && cascades.map(e => {
                        const a = byId.get(e.source), b = byId.get(e.target);
                        if (!a || !b || a === b) return null;
                        return (
                            <path key={`k-${e.source}-${e.target}`} d={curve(a, b)} fill="none" stroke="#f59e0b"
                                strokeOpacity={touches(e) ? 0.35 + 0.6 * e.confidence : 0.05}
                                strokeWidth={1 + 3 * e.confidence} markerEnd="url(#rm-arrow)">
                                <title>{`${e.source} → ${e.target}: ${(e.confidence * 100).toFixed(0)}% confidence, ~${e.avg_latency.toFixed(1)}h`}</title>
                            </path>
                        );
                    })}

                    {positions.map(p => {
                        const dim = focus && focus !== p.id && !neighbours.has(p.id);
                        const right = p.x >= SIZE / 2;
                        return (
                            <g key={p.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.3 : 1}
                                className="cursor-pointer outline-none" tabIndex={0} role="button"
                                aria-label={`${p.id}, PageRank ${p.pagerank.toFixed(3)}${keystones.has(p.id) ? ', keystone' : ''}${bridges.has(p.id) ? ', bridge' : ''}`}
                                onMouseEnter={() => setHovered(p.id)} onMouseLeave={() => setHovered(null)}
                                onFocus={() => setHovered(p.id)} onBlur={() => setHovered(null)}
                                onClick={() => setSelected(s => (s === p.id ? null : p.id))}
                                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(s => (s === p.id ? null : p.id)); } }}>
                                {keystones.has(p.id) && <circle r={p.r + 5} fill="none" stroke="#a5b4fc" strokeWidth={2} />}
                                {bridges.has(p.id) && <circle r={p.r + 9} fill="none" stroke="#a5b4fc" strokeWidth={1.5} strokeDasharray="3 3" />}
                                <circle r={p.r} fill={color(p.community)} fillOpacity={0.85}
                                    stroke={selected === p.id || hovered === p.id ? '#fff' : '#0f172a'} strokeWidth={selected === p.id || hovered === p.id ? 3 : 1.5} />
                                <text x={right ? p.r + 12 : -(p.r + 12)} y={4} textAnchor={right ? 'start' : 'end'}
                                    className="fill-slate-300" fontSize={12}>{p.id}</text>
                            </g>
                        );
                    })}
                </svg>

                <div className="space-y-4 text-xs">
                    {detail ? (
                        <div className="space-y-3" aria-live="polite">
                            <div>
                                <p className="text-sm font-semibold text-white">{detail.id}</p>
                                <p className="text-slate-500">
                                    {keystones.has(detail.id) ? 'Keystone' : 'Category'}
                                    {bridges.has(detail.id) ? ' · bridge' : ''}
                                    {detail.community >= 0 ? ` · community ${detail.community}` : ''}
                                </p>
                            </div>
                            <dl className="grid grid-cols-2 gap-2">
                                <dt className="text-slate-500">PageRank</dt><dd className="font-mono text-slate-200">{detail.pagerank.toFixed(3)}</dd>
                                <dt className="text-slate-500">Weighted degree</dt><dd className="font-mono text-slate-200">{detail.degree}</dd>
                            </dl>
                            <CascadeList title="Triggers" edges={outgoing} pick={e => e.target} />
                            <CascadeList title="Triggered by" edges={incoming} pick={e => e.source} />
                        </div>
                    ) : (
                        <p className="text-slate-500 leading-relaxed">
                            Larger circles carry more failure traffic (PageRank). Colours group categories that fail together.
                            Amber arrows are cascades: one failure type followed by another within the cascade window.
                        </p>
                    )}
                    <ul className="space-y-1.5 text-slate-400 pt-3 border-t border-slate-800">
                        <li className="flex items-center space-x-2"><svg width="22" height="22" aria-hidden="true"><circle cx="11" cy="11" r="6" fill="#64748b" /><circle cx="11" cy="11" r="9" fill="none" stroke="#a5b4fc" strokeWidth="2" /></svg><span>Keystone (top 20% PageRank)</span></li>
                        <li className="flex items-center space-x-2"><svg width="22" height="22" aria-hidden="true"><circle cx="11" cy="11" r="6" fill="#64748b" /><circle cx="11" cy="11" r="10" fill="none" stroke="#a5b4fc" strokeWidth="1.5" strokeDasharray="3 3" /></svg><span>Bridge (top 20% betweenness)</span></li>
                        <li className="flex items-center space-x-2"><svg width="22" height="22" aria-hidden="true"><line x1="2" y1="11" x2="20" y2="11" stroke="#94a3b8" strokeWidth="3" strokeOpacity="0.6" /></svg><span>Co-occurrence (thicker = more often)</span></li>
                        <li className="flex items-center space-x-2"><svg width="22" height="22" aria-hidden="true"><line x1="2" y1="11" x2="16" y2="11" stroke="#f59e0b" strokeWidth="2.5" /><path d="M14,7 L20,11 L14,15 z" fill="#f59e0b" /></svg><span>Cascade (thicker = higher confidence)</span></li>
                    </ul>
                </div>
            </div>
        </div>
    );
}

function CascadeList({ title, edges, pick }: {
    title: string;
    edges: GraphJson['cascade_edges'];
    pick: (e: GraphJson['cascade_edges'][number]) => string;
}) {
    if (edges.length === 0) return null;
    return (
        <div>
            <p className="text-[10px] uppercase tracking-widest text-amber-400 font-bold mb-1">{title}</p>
            <ul className="space-y-1">
                {edges.map(e => (
                    <li key={`${e.source}-${e.target}`} className="flex justify-between text-slate-300">
                        <span>{pick(e)}</span>
                        <span className="font-mono text-slate-500">{(e.confidence * 100).toFixed(0)}% · {e.avg_latency.toFixed(1)}h</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
