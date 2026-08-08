'use client';

import React, { useState, useMemo } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell, ScatterChart, Scatter,
    ZAxis, ComposedChart
} from 'recharts';
import {
    Activity, TrendingDown, AlertTriangle, CheckCircle, Download,
    Maximize2, HelpCircle, Clock, Target, Zap, Network, ChevronDown,
    ChevronUp, FileText
} from 'lucide-react';

// ── Types ───────────────────────────────────────────────────────────────────

interface GraphReport {
    keystone_categories: Array<{ name: string; pagerank: number; is_bridge: boolean }>;
    top_cascade: { chain: string; confidence: number } | null;
    num_communities: number;
    graph_density: number;
    graph_json?: {
        nodes: Array<{ id: string; pagerank: number; degree: number; community: number }>;
        edges: Array<{ source: string; target: string; weight: number; jaccard: number }>;
        cascade_edges: Array<{ source: string; target: string; weight: number; confidence: number; avg_latency: number }>;
    };
}

interface AnalysisResults {
    id: string;
    summary: {
        total_failures: number;
        duration_hours: number;
        start_time: string;
    };
    models: Array<{
        id: string;
        name: string;
        aic: number;
        total_expected_failures: number | null;
        parameters: Record<string, number>;
    }>;
    plots: Record<string, string>;
    categorized_failures: Array<any>;
    graph_insights?: string[];
    graph_report?: GraphReport | null;
}

// ── Color Palette ───────────────────────────────────────────────────────────

const CATEGORY_COLORS = [
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#14b8a6',
    '#6366f1', '#d946ef', '#0ea5e9',
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildCategoryCounts(categorized: any[]) {
    const counts: Record<string, number> = {};
    for (const row of categorized) {
        const cats = (row[2] || '').split(',').map((c: string) => c.trim()).filter(Boolean);
        for (const c of cats) {
            counts[c] = (counts[c] || 0) + 1;
        }
    }
    return Object.entries(counts)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value);
}

function buildTimeSeries(categorized: any[]) {
    // Group failures by hour bucket
    const buckets: Record<number, Record<string, number>> = {};
    const allCats = new Set<string>();
    for (const row of categorized) {
        const hour = Math.floor(parseFloat(row[1]) || 0);
        const cats = (row[2] || '').split(',').map((c: string) => c.trim()).filter(Boolean);
        if (!buckets[hour]) buckets[hour] = {};
        for (const c of cats) {
            allCats.add(c);
            buckets[hour][c] = (buckets[hour][c] || 0) + 1;
        }
    }
    const sortedHours = Object.keys(buckets).map(Number).sort((a, b) => a - b);
    return sortedHours.map(h => ({ hour: h, ...buckets[h] }));
}

function computeMTBFOverTime(categorized: any[], windowSize: number = 10) {
    const points: Array<{ hour: number; mtbf: number; failures: number }> = [];
    for (let i = windowSize; i < categorized.length; i += Math.max(1, Math.floor(windowSize / 2))) {
        const slice = categorized.slice(Math.max(0, i - windowSize), i);
        if (slice.length < 2) continue;
        const times = slice.map((r: any) => parseFloat(r[1])).sort((a: number, b: number) => a - b);
        let totalGap = 0;
        for (let j = 1; j < times.length; j++) totalGap += times[j] - times[j - 1];
        const mtbf = totalGap / (times.length - 1);
        points.push({ hour: parseFloat(categorized[i][1]), mtbf: parseFloat(mtbf.toFixed(2)), failures: i });
    }
    return points;
}

// ── Sub-components ──────────────────────────────────────────────────────────

function KPICard({ title, value, icon, description, tooltip, trend }: {
    title: string; value: string; icon: React.ReactNode; description: string; tooltip: string;
    trend?: 'up' | 'down' | 'stable';
}) {
    const [showTooltip, setShowTooltip] = useState(false);
    const trendColor = trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-rose-400' : 'text-slate-400';
    return (
        <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl hover:border-slate-700 transition-all group relative">
            <div className="flex items-center justify-between mb-3">
                <div className="p-2 rounded-lg bg-slate-800/50">{icon}</div>
                <div className="relative" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
                    <HelpCircle className="w-3 h-3 text-slate-600 hover:text-slate-400 cursor-help" />
                    {showTooltip && (
                        <div className="absolute bottom-full right-0 mb-2 w-48 p-3 rounded-xl bg-slate-950 border border-slate-800 text-[10px] text-slate-400 leading-relaxed shadow-2xl z-50">
                            {tooltip}
                        </div>
                    )}
                </div>
            </div>
            <div className="space-y-1">
                <h4 className="text-2xl font-bold text-white tracking-tight">{value}</h4>
                <p className="text-sm font-medium text-slate-300">{title}</p>
                <p className="text-xs text-slate-500">{description}</p>
            </div>
        </div>
    );
}

function GraphInsightCard({ graphReport }: { graphReport: GraphReport | null | undefined }) {
    const [expanded, setExpanded] = useState(false);
    if (!graphReport || !graphReport.keystone_categories || graphReport.keystone_categories.length === 0) {
        return (
            <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                <div className="flex items-center space-x-2 mb-2">
                    <Network className="w-4 h-4 text-slate-500" />
                    <h3 className="text-sm font-semibold text-slate-400">Fault Network Intelligence</h3>
                </div>
                <p className="text-xs text-slate-500">Install networkx on the API server to unlock graph-powered insights.</p>
            </div>
        );
    }

    return (
        <div className="p-6 rounded-2xl bg-gradient-to-br from-indigo-600/5 to-purple-600/10 border border-indigo-500/20 backdrop-blur-xl">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                    <Network className="w-4 h-4 text-indigo-400" />
                    <h3 className="text-sm font-semibold text-white">Fault Network Intelligence</h3>
                </div>
                <button onClick={() => setExpanded(!expanded)} className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center space-x-1">
                    <span>{expanded ? 'Collapse' : 'Details'}</span>
                    {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
            </div>

            {/* Keystone categories */}
            <div className="grid grid-cols-2 gap-3 mb-3">
                {graphReport.keystone_categories.slice(0, 4).map(cat => (
                    <div key={cat.name} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/30">
                        <div className="flex items-center space-x-2 min-w-0">
                            <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
                            <span className="text-xs font-medium text-slate-200 truncate">{cat.name}</span>
                        </div>
                        <span className="text-[10px] font-mono text-indigo-400 ml-2 shrink-0">
                            PR {cat.pagerank.toFixed(3)}
                            {cat.is_bridge ? ' 🔗' : ''}
                        </span>
                    </div>
                ))}
            </div>

            {/* Top cascade */}
            {graphReport.top_cascade && (
                <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/10 mb-3">
                    <p className="text-[10px] text-amber-400 uppercase tracking-widest font-bold mb-1">Top Cascade</p>
                    <p className="text-xs text-slate-300 font-mono">{graphReport.top_cascade.chain}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                        Confidence: {(graphReport.top_cascade.confidence * 100).toFixed(1)}%
                    </p>
                </div>
            )}

            {/* Expanded details */}
            {expanded && graphReport.graph_json && (
                <div className="mt-3 pt-3 border-t border-slate-800 space-y-2">
                    <p className="text-[10px] text-slate-500">
                        {graphReport.graph_json.nodes.length} categories · {graphReport.graph_json.edges.length} co-occurrence edges · {graphReport.graph_json.cascade_edges.length} cascade edges
                    </p>
                    <p className="text-[10px] text-slate-500">
                        {graphReport.num_communities} communities · density {graphReport.graph_density.toFixed(3)}
                    </p>
                </div>
            )}
        </div>
    );
}

function RiskBubbleChart({ categorized, graphReport }: { categorized: any[]; graphReport?: GraphReport | null }) {
    const data = useMemo(() => {
        const counts = buildCategoryCounts(categorized);
        const pagerankMap: Record<string, number> = {};
        if (graphReport?.keystone_categories) {
            for (const kc of graphReport.keystone_categories) {
                pagerankMap[kc.name] = kc.pagerank;
            }
        }
        return counts.slice(0, 8).map(c => ({
            name: c.name,
            failures: c.value,
            centrality: pagerankMap[c.name] || 0.01,
            impact: Math.round(c.value * (pagerankMap[c.name] || 0.05) * 100),
        }));
    }, [categorized, graphReport]);

    if (data.length === 0) return null;

    return (
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center space-x-2">
                <Target className="w-4 h-4 text-rose-400" />
                <span>Risk Landscape</span>
                <span className="text-[10px] text-slate-500 font-normal ml-2">size = failure count, x = centrality</span>
            </h3>
            <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis type="number" dataKey="centrality" name="Centrality" tick={{ fontSize: 10, fill: '#64748b' }}
                            label={{ value: '← Less Central | More Central →', position: 'bottom', offset: -5, style: { fontSize: 9, fill: '#475569' } }} />
                        <YAxis type="number" dataKey="failures" name="Failures" tick={{ fontSize: 10, fill: '#64748b' }}
                            label={{ value: 'Failure Count', angle: -90, position: 'left', style: { fontSize: 9, fill: '#475569' } }} />
                        <ZAxis type="number" dataKey="impact" range={[30, 200]} />
                        <Tooltip cursor={{ strokeDasharray: '3 3' }}
                            contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }}
                            formatter={(value: any, name: string) => [value, name === 'centrality' ? 'Centrality' : name === 'failures' ? 'Failures' : name]} />
                        <Scatter data={data} fill="#6366f1">
                            {data.map((entry, index) => (
                                <Cell key={entry.name} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} fillOpacity={0.7} />
                            ))}
                        </Scatter>
                    </ScatterChart>
                </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
                {data.slice(0, 6).map((d, i) => (
                    <span key={d.name} className="flex items-center space-x-1 text-[10px] text-slate-400">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: CATEGORY_COLORS[i] }} />
                        <span>{d.name}</span>
                    </span>
                ))}
            </div>
        </div>
    );
}

function MTBFTrendChart({ categorized, windowSize = 20 }: { categorized: any[]; windowSize?: number }) {
    const data = useMemo(() => computeMTBFOverTime(categorized, windowSize), [categorized, windowSize]);
    if (data.length < 2) {
        return (
            <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl flex items-center justify-center h-64">
                <p className="text-xs text-slate-500">Need more data for MTBF trend (min 20 failures).</p>
            </div>
        );
    }
    return (
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
            <h3 className="text-sm font-semibold text-white mb-4 flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                <span>MTBF Trend</span>
                <span className="text-[10px] text-slate-500 font-normal">rolling window of {windowSize} failures</span>
            </h3>
            <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'Hours', position: 'bottom', style: { fontSize: 9, fill: '#475569' } }} />
                        <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'MTBF (h)', angle: -90, position: 'left', style: { fontSize: 9, fill: '#475569' } }} />
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }} />
                        <Area yAxisId="left" type="monotone" dataKey="mtbf" stroke="#10b981" fill="#10b981" fillOpacity={0.15} strokeWidth={2} name="MTBF (hours)" />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

// ── Main Dashboard ──────────────────────────────────────────────────────────

export default function Dashboard({
    data, futureHours, onFutureHoursChange
}: {
    data: AnalysisResults;
    futureHours: number;
    onFutureHoursChange: (h: number) => void;
}) {
    const [showPNGPlots, setShowPNGPlots] = useState(true);
    const bestModel = data.models.reduce((prev, curr) => prev.aic < curr.aic ? prev : curr);
    const categoryData = useMemo(() => buildCategoryCounts(data.categorized_failures), [data.categorized_failures]);
    const timeSeriesData = useMemo(() => buildTimeSeries(data.categorized_failures), [data.categorized_failures]);
    const mtbf = data.summary.duration_hours / (data.summary.total_failures || 1);
    const residuals = bestModel.total_expected_failures
        ? Math.max(0, Math.round(bestModel.total_expected_failures - data.summary.total_failures))
        : null;

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* ── Top Bar: Forecast Slider + Actions ─────────────────────── */}
            <div className="p-6 rounded-2xl bg-gradient-to-r from-blue-600/10 to-indigo-600/5 border border-blue-500/20 backdrop-blur-xl flex flex-col md:flex-row items-center justify-between gap-6">
                <div className="flex items-center space-x-4">
                    <div className="p-3 rounded-xl bg-blue-500/20"><Clock className="w-6 h-6 text-blue-400" /></div>
                    <div>
                        <h3 className="text-white font-bold tracking-tight">Prediction Playground</h3>
                        <p className="text-xs text-slate-400">Project system stability {futureHours}h into the future.</p>
                    </div>
                </div>
                <div className="flex-1 max-w-md w-full px-4">
                    <div className="flex justify-between mb-2">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Horizon: {futureHours} Hours</span>
                    </div>
                    <input type="range" min="100" max="5000" step="100" value={futureHours}
                        onChange={(e) => onFutureHoursChange(parseInt(e.target.value))}
                        className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500" />
                </div>
                <div className="flex space-x-2">
                    <button onClick={() => setShowPNGPlots(!showPNGPlots)}
                        className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 text-xs hover:text-white transition-all">
                        {showPNGPlots ? 'Interactive' : 'Plots'}
                    </button>
                    <button onClick={() => window.print()}
                        className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-white text-slate-900 font-bold text-xs hover:bg-slate-200 transition-all shadow-lg">
                        <FileText className="w-4 h-4" />
                        <span>Print Report</span>
                    </button>
                </div>
            </div>

            {/* ── KPI Row ────────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                <KPICard title="Total Failures" value={data.summary.total_failures.toString()}
                    icon={<AlertTriangle className="text-amber-500 w-4 h-4" />}
                    description="Incidents logged" tooltip="Raw count of unique failure events in the dataset." />
                <KPICard title="MTBF" value={mtbf.toFixed(1) + 'h'}
                    icon={<Activity className="text-blue-500 w-4 h-4" />}
                    description="Mean time between failures" tooltip="Average hours between failures. Higher = more reliable." />
                <KPICard title="Predicted Residuals" value={residuals !== null ? residuals.toString() : 'N/A'}
                    icon={<TrendingDown className="text-rose-500 w-4 h-4" />}
                    description="Failures remaining" tooltip="Statistical estimate of undiscovered faults." />
                <KPICard title="Best Model" value={bestModel.name.split('-')[0]}
                    icon={<CheckCircle className="text-emerald-500 w-4 h-4" />}
                    description={`AIC: ${bestModel.aic.toFixed(1)}`} tooltip="AIC measures fit quality. Lower is better." />
                <KPICard title="Failure Rate" value={(data.summary.total_failures / Math.max(1, data.summary.duration_hours)).toFixed(2) + '/h'}
                    icon={<Zap className="text-purple-500 w-4 h-4" />}
                    description="Failures per hour" tooltip="Overall failure intensity across the observation period." />
            </div>

            {/* ── Main Charts Row ────────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Reliability Growth — PNG fallback or Recharts area */}
                <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold text-white">Reliability Growth Projection</h3>
                        <button className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition-colors">
                            <Maximize2 className="w-3.5 h-3.5" />
                        </button>
                    </div>
                    {data.plots.reliability ? (
                        <img src={`data:image/png;base64,${data.plots.reliability}`} alt="Reliability growth"
                            className="w-full h-auto rounded-lg" />
                    ) : (
                        <div className="h-64 flex items-center justify-center">
                            <p className="text-xs text-slate-500">Chart unavailable.</p>
                        </div>
                    )}
                </div>

                {/* Model Comparison + Graph Insights */}
                <div className="space-y-4">
                    <div className="p-5 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                        <h3 className="text-sm font-semibold text-white mb-3">Model Comparison</h3>
                        {data.models.map(model => (
                            <div key={model.id} className="flex items-center justify-between p-2.5 rounded-lg mb-2 bg-slate-800/20 border border-slate-700/20">
                                <div className="flex items-center space-x-2">
                                    <span className="text-xs font-medium text-slate-300">{model.name}</span>
                                    {model.id === bestModel.id && (
                                        <span className="text-[9px] font-bold text-emerald-500 uppercase bg-emerald-500/10 px-1.5 py-0.5 rounded">Best</span>
                                    )}
                                </div>
                                <div className="text-right">
                                    <span className="text-xs font-mono text-white block">AIC {model.aic.toFixed(1)}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                    <GraphInsightCard graphReport={data.graph_report} />
                </div>
            </div>

            {/* ── Category Charts Row ─────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Category Breakdown — Recharts interactive bar */}
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <h3 className="text-sm font-semibold text-white mb-4">Failure Categories</h3>
                    <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={categoryData.slice(0, 10)} layout="vertical" margin={{ top: 0, right: 20, bottom: 0, left: 80 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} />
                                <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} width={80} />
                                <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }} />
                                <Bar dataKey="value" name="Failures" radius={[0, 4, 4, 0]}>
                                    {categoryData.slice(0, 10).map((_, i) => (
                                        <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} fillOpacity={0.8} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Intensity / Category plot PNG */}
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <h3 className="text-sm font-semibold text-white mb-4">Failure Intensity & Categories</h3>
                    {data.plots.intensity ? (
                        <img src={`data:image/png;base64,${data.plots.intensity}`} alt="Intensity plot"
                            className="w-full h-auto rounded-lg" />
                    ) : (
                        <div className="h-64 flex items-center justify-center">
                            <p className="text-xs text-slate-500">Intensity chart unavailable.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* ── MTBF Trend + Risk Bubble ────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <MTBFTrendChart categorized={data.categorized_failures} windowSize={Math.max(10, Math.floor(data.summary.total_failures / 20))} />
                <RiskBubbleChart categorized={data.categorized_failures} graphReport={data.graph_report} />
            </div>

            {/* ── Category PNG + Recent Failures ──────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {data.plots.categories && (
                    <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                        <h3 className="text-sm font-semibold text-white mb-4">Fault Taxonomy (Detailed)</h3>
                        <img src={`data:image/png;base64,${data.plots.categories}`} alt="Category breakdown"
                            className="w-full h-auto rounded-lg" />
                    </div>
                )}
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl overflow-hidden">
                    <h3 className="text-sm font-semibold text-white mb-4">Recent Failure Events</h3>
                    <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
                        {data.categorized_failures.slice(0, 50).map((fail, i) => (
                            <div key={i} className="flex items-center p-2.5 rounded-lg bg-slate-800/20 border border-slate-700/20 text-xs hover:bg-slate-800/40 transition-colors">
                                <span className="text-slate-500 mr-3 font-mono text-[10px] w-12">{parseFloat(fail[1]).toFixed(2)}h</span>
                                <span className="px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-400 mr-3 font-medium truncate max-w-[90px] text-[10px]">{fail[2]}</span>
                                <span className="text-slate-300 truncate flex-1 text-[11px]">{fail[3]}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
