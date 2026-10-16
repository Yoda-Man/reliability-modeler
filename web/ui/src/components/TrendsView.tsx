'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Minus, Loader2, BarChart3 } from 'lucide-react';
import { apiJson } from '@/lib/api';
import type { TrendRun, TrendsResponse, TrendDirection } from '@/lib/types';
import ErrorState from './ErrorState';

function formatNumber(value: unknown): string {
    return typeof value === 'number' ? value.toFixed(4) : String(value ?? '');
}

interface TrendView {
    file: string | null;
    runs: TrendRun[];
    trend: TrendDirection;
    mtbf_change_pct?: number;
    num_runs: number;
}

/** The per-source group to show (selected, else the most recent run's), or the whole response when `groups` is absent. */
function pickView(data: TrendsResponse, selected: string | null): TrendView {
    const groups = data.groups ?? [];
    if (groups.length > 0) {
        const latestFile = data.runs[data.runs.length - 1]?.file;
        const g = groups.find(x => x.file === selected) ?? groups.find(x => x.file === latestFile) ?? groups[0];
        return { file: g.file, runs: g.runs, trend: g.trend, mtbf_change_pct: g.mtbf_change_pct, num_runs: g.num_runs ?? g.runs.length };
    }
    return { file: null, runs: data.runs, trend: data.trend, mtbf_change_pct: data.mtbf_change_pct, num_runs: data.num_runs ?? data.runs.length };
}

export default function TrendsView() {
    const [data, setData] = useState<TrendsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<unknown>(null);

    const [reloadKey, setReloadKey] = useState(0);
    const [selectedFile, setSelectedFile] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        apiJson<TrendsResponse>('/trends', {}, 'Failed to load trends')
            .then(json => {
                if (cancelled) return;
                setData(json);
                setError(null);
            })
            .catch((err: unknown) => {
                if (!cancelled) setError(err);
            })
            .finally(() => {
                if (!cancelled) setIsLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [reloadKey]);

    const retry = () => {
        setIsLoading(true);
        setReloadKey(k => k + 1);
    };

    const view = useMemo(() => (data?.runs ? pickView(data, selectedFile) : null), [data, selectedFile]);

    const chartData = useMemo(() => {
        if (!view) return [];
        return view.runs.map((r, i) => ({
            index: i + 1,
            label: r.date?.slice(0, 16) || `Run ${i + 1}`,
            mtbf: r.mtbf_hours,
            failureRate: r.failure_rate_per_hour,
            totalFailures: r.total_failures,
            file: r.file,
        }));
    }, [view]);

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-slate-400">Loading trend data...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-4xl animate-in fade-in duration-500 space-y-6">
                <h2 className="text-3xl font-bold text-white tracking-tight">Reliability Trends</h2>
                <ErrorState title="Could not load trend data" error={error} onRetry={retry} />
            </div>
        );
    }

    const groups = data?.groups ?? [];
    const sourceSelector = groups.length > 1 && view ? (
        <label className="flex items-center space-x-2 text-xs text-slate-400">
            <span>Source</span>
            <select
                aria-label="Source"
                value={view.file ?? ''}
                onChange={(e) => setSelectedFile(e.target.value)}
                className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-300 focus:outline-none focus:border-blue-500"
            >
                {groups.map(g => (
                    <option key={g.file} value={g.file}>{g.file} ({g.num_runs ?? g.runs.length} runs)</option>
                ))}
            </select>
        </label>
    ) : null;

    if (!data || !view || view.num_runs < 2) {
        return (
            <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="flex items-center justify-between mb-6 gap-4">
                    <h2 className="text-3xl font-bold text-white tracking-tight">Reliability Trends</h2>
                    {sourceSelector}
                </div>
                <div className="p-12 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl text-center">
                    <BarChart3 className="w-16 h-16 text-slate-800 mx-auto mb-6" />
                    <h4 className="text-white font-semibold mb-2 text-lg">Insufficient Data</h4>
                    <p className="text-sm text-slate-500 max-w-sm mx-auto">
                        {view?.file
                            ? 'Run at least 2 analyses of this source to see MTBF and failure rate trends over time.'
                            : 'Run at least 2 analyses to see MTBF and failure rate trends over time.'}
                        {' '}Each analysis is automatically archived in the Logs.
                    </p>
                </div>
            </div>
        );
    }

    const trendIcon = view.trend === 'improving'
        ? <TrendingUp className="w-5 h-5 text-emerald-400" />
        : view.trend === 'degrading'
            ? <TrendingDown className="w-5 h-5 text-rose-400" />
            : <Minus className="w-5 h-5 text-amber-400" />;

    const trendLabel = view.trend === 'improving' ? 'Improving' : view.trend === 'degrading' ? 'Degrading' : 'Stable';
    const trendColor = view.trend === 'improving' ? 'text-emerald-400' : view.trend === 'degrading' ? 'text-rose-400' : 'text-amber-400';

    return (
        <div className="max-w-6xl animate-in fade-in slide-in-from-bottom-4 duration-700 space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white mb-2 tracking-tight">Reliability Trends</h2>
                    <p className="text-slate-400 text-sm">
                        Cross-run comparison of {view.num_runs} archived analyses{view.file ? <> of <span className="font-mono text-slate-300">{view.file}</span></> : null}.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                {sourceSelector}
                <div className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-900/50 border border-slate-800">
                    {trendIcon}
                    <span className={`text-sm font-semibold ${trendColor}`}>
                        MTBF {trendLabel} ({(view.mtbf_change_pct ?? 0) > 0 ? '+' : ''}{view.mtbf_change_pct ?? 0}%)
                    </span>
                </div>
                </div>
            </div>

            {/* MTBF Trend Chart */}
            <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center space-x-2">
                    <TrendingUp className="w-4 h-4 text-blue-400" />
                    <span>MTBF Trend (higher is better)</span>
                </h3>
                <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" height={50} />
                            <YAxis tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'MTBF (hours)', angle: -90, position: 'left', style: { fontSize: 9, fill: '#475569' } }} />
                            <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }}
                                formatter={(value) => [formatNumber(value), 'MTBF']} />
                            <Line type="monotone" dataKey="mtbf" stroke="#3b82f6" strokeWidth={2.5} dot={{ r: 4, fill: '#3b82f6' }} name="MTBF (hours)" />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Failure Rate Chart */}
            <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center space-x-2">
                    <TrendingDown className="w-4 h-4 text-rose-400" />
                    <span>Failure Rate Trend (lower is better)</span>
                </h3>
                <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} angle={-30} textAnchor="end" height={50} />
                            <YAxis tick={{ fontSize: 10, fill: '#64748b' }} label={{ value: 'Failures / hour', angle: -90, position: 'left', style: { fontSize: 9, fill: '#475569' } }} />
                            <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }}
                                formatter={(value) => [formatNumber(value), 'Rate']} />
                            <Line type="monotone" dataKey="failureRate" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 4, fill: '#ef4444' }} name="Failure Rate (/h)" />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Run-by-Run Table */}
            <div className="rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl overflow-hidden">
                <table className="w-full text-left">
                    <thead>
                        <tr className="border-b border-slate-800 bg-slate-950/30">
                            <th className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-widest">Date</th>
                            <th className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-widest">File</th>
                            <th className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-widest">Failures</th>
                            <th className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-widest">MTBF</th>
                            <th className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-widest">Rate</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                        {view.runs.map((run) => (
                            <tr key={run.id} className="hover:bg-slate-800/20 transition-colors">
                                <td className="px-6 py-3 text-xs text-slate-300">{run.date}</td>
                                <td className="px-6 py-3 text-xs text-slate-400 font-mono max-w-[200px] truncate">{run.file}</td>
                                <td className="px-6 py-3 text-xs text-slate-300 font-mono">{run.total_failures}</td>
                                <td className="px-6 py-3 text-xs text-slate-300 font-mono">{run.mtbf_hours}h</td>
                                <td className="px-6 py-3 text-xs text-slate-300 font-mono">{run.failure_rate_per_hour}/h</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
