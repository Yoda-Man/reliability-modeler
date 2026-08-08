'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Minus, Loader2, Calendar, BarChart3 } from 'lucide-react';

interface TrendRun {
    id: string;
    date: string;
    file: string;
    total_failures: number;
    duration_hours: number;
    mtbf_hours: number;
    failure_rate_per_hour: number;
}

interface TrendsResponse {
    runs: TrendRun[];
    trend: string;
    mtbf_change_pct: number;
    rate_change_pct: number;
    num_runs: number;
}

export default function TrendsView() {
    const [data, setData] = useState<TrendsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        fetchTrends();
    }, []);

    const fetchTrends = async () => {
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/trends`);
            if (response.ok) {
                setData(await response.json());
            }
        } catch (error) {
            console.error('Failed to fetch trends:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const chartData = useMemo(() => {
        if (!data?.runs) return [];
        return data.runs.map((r, i) => ({
            index: i + 1,
            label: r.date?.slice(0, 16) || `Run ${i + 1}`,
            mtbf: r.mtbf_hours,
            failureRate: r.failure_rate_per_hour,
            totalFailures: r.total_failures,
            file: r.file,
        }));
    }, [data]);

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-slate-400">Loading trend data...</p>
            </div>
        );
    }

    if (!data || data.num_runs < 2) {
        return (
            <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700">
                <h2 className="text-3xl font-bold text-white mb-6 tracking-tight">Reliability Trends</h2>
                <div className="p-12 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl text-center">
                    <BarChart3 className="w-16 h-16 text-slate-800 mx-auto mb-6" />
                    <h4 className="text-white font-semibold mb-2 text-lg">Insufficient Data</h4>
                    <p className="text-sm text-slate-500 max-w-sm mx-auto">
                        Run at least 2 analyses to see MTBF and failure rate trends over time.
                        Each analysis is automatically archived in the Logs.
                    </p>
                </div>
            </div>
        );
    }

    const trendIcon = data.trend === 'improving'
        ? <TrendingUp className="w-5 h-5 text-emerald-400" />
        : data.trend === 'degrading'
            ? <TrendingDown className="w-5 h-5 text-rose-400" />
            : <Minus className="w-5 h-5 text-amber-400" />;

    const trendLabel = data.trend === 'improving' ? 'Improving' : data.trend === 'degrading' ? 'Degrading' : 'Stable';
    const trendColor = data.trend === 'improving' ? 'text-emerald-400' : data.trend === 'degrading' ? 'text-rose-400' : 'text-amber-400';

    return (
        <div className="max-w-6xl animate-in fade-in slide-in-from-bottom-4 duration-700 space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white mb-2 tracking-tight">Reliability Trends</h2>
                    <p className="text-slate-400 text-sm">Cross-run comparison of {data.num_runs} archived analyses.</p>
                </div>
                <div className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-900/50 border border-slate-800">
                    {trendIcon}
                    <span className={`text-sm font-semibold ${trendColor}`}>
                        MTBF {trendLabel} ({data.mtbf_change_pct > 0 ? '+' : ''}{data.mtbf_change_pct}%)
                    </span>
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
                                formatter={(value: any) => [typeof value === 'number' ? value.toFixed(4) : value, 'MTBF']} />
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
                                formatter={(value: any) => [typeof value === 'number' ? value.toFixed(4) : value, 'Rate']} />
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
                        {data.runs.map((run) => (
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
