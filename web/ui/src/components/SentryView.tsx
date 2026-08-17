'use client';

import React, { useState } from 'react';
import { Bug, Loader2, Search, AlertCircle, CheckCircle2 } from 'lucide-react';
import { apiFetch } from '@/app/apiClient';

interface SentryViewProps {
    onAnalyze: (org: string, project: string, days: number) => Promise<void>;
    isLoading: boolean;
}

export default function SentryView({ onAnalyze, isLoading }: SentryViewProps) {
    const [org, setOrg] = useState('');
    const [project, setProject] = useState('');
    const [days, setDays] = useState(30);
    const [analyzeAll, setAnalyzeAll] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        if (!org.trim()) {
            setError('Organization is required.');
            return;
        }
        if (!analyzeAll && !project.trim()) {
            setError('Enter a project slug or enable "Analyze all projects".');
            return;
        }
        if (days < 1 || days > 365) {
            setError('Days must be between 1 and 365.');
            return;
        }
        try {
            await onAnalyze(org.trim(), analyzeAll ? 'all' : project.trim(), days);
        } catch (err: any) {
            setError(err.message || 'Failed to pull data from Sentry.');
        }
    };

    return (
        <div className="max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="mb-8">
                <h2 className="text-3xl font-bold text-white mb-2 tracking-tight flex items-center space-x-3">
                    <Bug className="w-7 h-7 text-purple-400" />
                    <span>Sentry Integration</span>
                </h2>
                <p className="text-slate-400 text-sm leading-relaxed">
                    Pull raw failure events directly from Sentry and run the full reliability analysis —
                    no CSV export needed. Events are categorized using your existing taxonomy.
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl space-y-5">
                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Organization Slug
                        </label>
                        <input
                            type="text"
                            value={org}
                            onChange={(e) => setOrg(e.target.value)}
                            placeholder="e.g. my-company"
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Project Slug
                        </label>
                        <input
                            type="text"
                            value={project}
                            onChange={(e) => setProject(e.target.value)}
                            placeholder={analyzeAll ? 'All projects selected' : 'e.g. web-app'}
                            disabled={analyzeAll}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                    </div>

                    <label className="flex items-center space-x-3 p-4 rounded-xl bg-purple-600/5 border border-purple-500/20 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={analyzeAll}
                            onChange={(e) => setAnalyzeAll(e.target.checked)}
                            className="w-4 h-4 rounded border-slate-700 accent-purple-500"
                        />
                        <div>
                            <span className="text-sm font-semibold text-white">Analyze all projects</span>
                            <p className="text-xs text-slate-500">Aggregate every project in the org into one system-wide reliability model.</p>
                        </div>
                    </label>

                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Look-back Window (days)
                        </label>
                        <input
                            type="number"
                            min={1}
                            max={365}
                            value={days}
                            onChange={(e) => setDays(parseInt(e.target.value) || 30)}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full flex items-center justify-center space-x-2 px-6 py-3.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-purple-500/20"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span>Pulling from Sentry & analyzing...</span>
                            </>
                        ) : (
                            <>
                                <Search className="w-4 h-4" />
                                <span>Pull & Analyze</span>
                            </>
                        )}
                    </button>
                </div>
            </form>

            {error && (
                <div className="mt-4 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-start space-x-3">
                    <AlertCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-rose-300">{error}</p>
                </div>
            )}

            <div className="mt-6 p-5 rounded-2xl bg-slate-900/30 border border-slate-800/50 space-y-3">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Setup Requirements</h3>
                <ul className="space-y-2 text-sm text-slate-500">
                    <li className="flex items-start space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span>The API server must have <code className="text-slate-300">SENTRY_AUTH_TOKEN</code> set (org token with <code className="text-slate-300">event:read</code> scope).</span>
                    </li>
                    <li className="flex items-start space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span>For self-hosted Sentry, set <code className="text-slate-300">SENTRY_BASE_URL</code> on the API server.</span>
                    </li>
                    <li className="flex items-start space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span>Events are counted as individual occurrences (not unique issues) for accurate MTBF modeling.</span>
                    </li>
                </ul>
            </div>
        </div>
    );
}
