'use client';

import React from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell
} from 'recharts';
import {
    Activity,
    TrendingDown,
    AlertTriangle,
    CheckCircle,
    Download,
    Maximize2,
    HelpCircle,
    Clock,
    FileJson
} from 'lucide-react';

interface AnalysisResults {
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
}

export default function Dashboard({
    data,
    futureHours,
    onFutureHoursChange
}: {
    data: AnalysisResults,
    futureHours: number,
    onFutureHoursChange: (h: number) => void
}) {
    const bestModel = data.models.reduce((prev, curr) => prev.aic < curr.aic ? prev : curr);

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Prediction Playground */}
            <div className="p-6 rounded-2xl bg-gradient-to-r from-blue-600/10 to-indigo-600/5 border border-blue-500/20 backdrop-blur-xl mb-8 flex flex-col md:flex-row items-center justify-between gap-6">
                <div className="flex items-center space-x-4">
                    <div className="p-3 rounded-xl bg-blue-500/20">
                        <Clock className="w-6 h-6 text-blue-400" />
                    </div>
                    <div>
                        <h3 className="text-white font-bold tracking-tight">Prediction Playground</h3>
                        <p className="text-xs text-slate-400">Project system stability into the future.</p>
                    </div>
                </div>

                <div className="flex-1 max-w-md w-full px-4">
                    <div className="flex justify-between mb-2">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Horizon: {futureHours} Hours</span>
                    </div>
                    <input
                        type="range"
                        min="100"
                        max="5000"
                        step="100"
                        value={futureHours}
                        onChange={(e) => onFutureHoursChange(parseInt(e.target.value))}
                        className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                    />
                </div>

                <button
                    onClick={() => window.print()}
                    className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-white text-slate-900 font-bold text-xs hover:bg-slate-200 transition-all shadow-lg shadow-white/5"
                >
                    <Download className="w-4 h-4" />
                    <span>Executive Report</span>
                </button>
            </div>

            {/* KPI Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <KPICard
                    title="Total Failures"
                    value={data.summary.total_failures.toString()}
                    icon={<AlertTriangle className="text-amber-500" />}
                    description="Total incidents logged"
                    tooltip="The raw count of unique failure events identified in your dataset."
                />
                <KPICard
                    title="MTBF"
                    value={(data.summary.duration_hours / (data.summary.total_failures || 1)).toFixed(2) + "h"}
                    icon={<Activity className="text-blue-500" />}
                    description="Mean Time Between Failures"
                    tooltip="The average time elapsed between failure events. Higher values indicate higher reliability."
                />
                <KPICard
                    title="Predicted Residuals"
                    value={bestModel.total_expected_failures ? (bestModel.total_expected_failures - data.summary.total_failures).toFixed(0) : "N/A"}
                    icon={<TrendingDown className="text-rose-500" />}
                    description="Likely failures remaining"
                    tooltip="Statistical estimate of faults remaining in the system based on current growth trends."
                />
                <KPICard
                    title="Best Fit Model"
                    value={bestModel.name}
                    icon={<CheckCircle className="text-emerald-500" />}
                    description={`AIC: ${bestModel.aic.toFixed(2)}`}
                    tooltip="Akaike Information Criterion (AIC) measures fit quality. Lower is better."
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Growth Plot */}
                <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-semibold text-white">Reliability Growth Projection</h3>
                        <div className="flex space-x-2">
                            <button className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition-colors">
                                <Maximize2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    <div className="aspect-[16/9] w-full bg-slate-950/50 rounded-xl overflow-hidden flex items-center justify-center">
                        {data.plots.reliability ? (
                            <img
                                src={`data:image/png;base64,${data.plots.reliability}`}
                                alt="Reliability Plot"
                                className="w-full h-full object-contain"
                            />
                        ) : (
                            <p className="text-slate-500">Visualization pending...</p>
                        )}
                    </div>
                </div>

                {/* Model Comparison */}
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <h3 className="text-lg font-semibold text-white mb-6">Strategic Modeling</h3>
                    <div className="space-y-4">
                        {data.models.map(model => (
                            <div key={model.id} className="p-4 rounded-xl bg-slate-800/30 border border-slate-700/30 transition-all hover:bg-slate-800/50">
                                <div className="flex justify-between items-center mb-2">
                                    <span className="text-sm font-medium text-slate-300">{model.name}</span>
                                    <span className={model.id === bestModel.id ? "text-xs font-bold text-emerald-500 uppercase tracking-wider" : "hidden"}>
                                        Recommended
                                    </span>
                                </div>
                                <div className="flex items-end justify-between">
                                    <div>
                                        <span className="text-xs text-slate-500 block mb-1">AIC Score</span>
                                        <span className="text-lg font-mono text-white">{model.aic.toFixed(3)}</span>
                                    </div>
                                    <div className="text-right">
                                        <span className="text-xs text-slate-500 block mb-1">Pred. Total</span>
                                        <span className="text-lg font-mono text-white">{model.total_expected_failures?.toFixed(1) || "∞"}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="mt-8 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                        <h4 className="text-sm font-semibold text-blue-400 mb-2 flex items-center">
                            <Activity className="w-4 h-4 mr-2" />
                            Management Insight
                        </h4>
                        <p className="text-xs text-blue-200/70 leading-relaxed">
                            Based on software reliability growth models, your system is trending towards stability.
                            The {bestModel.name} model provides the highest statistical confidence.
                        </p>
                    </div>
                </div>
            </div>

            {/* Category Analysis */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
                    <h3 className="text-lg font-semibold text-white mb-6">Fault Taxonomy</h3>
                    <div className="aspect-square max-h-[300px] w-full flex items-center justify-center">
                        {data.plots.categories ? (
                            <img
                                src={`data:image/png;base64,${data.plots.categories}`}
                                alt="Category Plot"
                                className="w-full h-full object-contain"
                            />
                        ) : (
                            <p className="text-slate-500">Taxonomy plot pending...</p>
                        )}
                    </div>
                </div>

                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl overflow-hidden">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-semibold text-white">Recent Artifacts</h3>
                        <button className="text-xs font-medium text-blue-400 hover:text-blue-300">View All</button>
                    </div>
                    <div className="space-y-3 max-h-[320px] overflow-y-auto pr-2 custom-scrollbar">
                        {data.categorized_failures.map((fail, i) => (
                            <div key={i} className="flex items-center p-3 rounded-lg bg-slate-800/20 border border-slate-700/20 text-xs transition-colors hover:bg-slate-800/40">
                                <span className="text-slate-500 mr-4 font-mono">{fail[1].toFixed(2)}h</span>
                                <span className="px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-400 mr-4 font-medium truncate max-w-[100px]">
                                    {fail[2]}
                                </span>
                                <span className="text-slate-300 truncate flex-1">{fail[3]}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

function KPICard({ title, value, icon, description, tooltip }: { title: string; value: string; icon: React.ReactNode; description: string; tooltip: string }) {
    const [showTooltip, setShowTooltip] = React.useState(false);

    return (
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl hover:border-slate-700 transition-all group relative">
            <div className="flex items-center justify-between mb-4">
                <div className="p-2 rounded-lg bg-slate-800/50 group-hover:bg-slate-800 transition-colors">
                    {icon}
                </div>
                <div
                    className="relative"
                    onMouseEnter={() => setShowTooltip(true)}
                    onMouseLeave={() => setShowTooltip(false)}
                >
                    <HelpCircle className="w-3 h-3 text-slate-600 hover:text-slate-400 cursor-help" />
                    {showTooltip && (
                        <div className="absolute bottom-full right-0 mb-2 w-48 p-3 rounded-xl bg-slate-950 border border-slate-800 text-[10px] text-slate-400 leading-relaxed shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-200">
                            {tooltip}
                        </div>
                    )}
                </div>
            </div>
            <div className="space-y-1">
                <h4 className="text-3xl font-bold text-white tracking-tight">{value}</h4>
                <p className="text-sm font-medium text-slate-300">{title}</p>
                <p className="text-xs text-slate-500 pt-1">{description}</p>
            </div>
        </div>
    );
}
