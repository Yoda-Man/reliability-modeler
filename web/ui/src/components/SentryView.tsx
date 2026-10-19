'use client';

import React, { useEffect, useState } from 'react';
import { Bug, Loader2, Search, AlertCircle, CheckCircle2 } from 'lucide-react';
import { apiJson, formatError } from '@/lib/api';
import type { SentryOrganization, SentryProject } from '@/lib/types';
import SentryConnection from '@/components/SentryConnection';

interface SentryViewProps {
    onAnalyze: (org: string, project: string, days: number, futureHours: number) => Promise<void>;
    isLoading: boolean;
}

export default function SentryView({ onAnalyze, isLoading }: SentryViewProps) {
    const [org, setOrg] = useState('');
    const [project, setProject] = useState('');
    // Kept as raw strings so the fields can be cleared while typing; parsed on submit.
    const [days, setDays] = useState('30');
    const [futureHours, setFutureHours] = useState('1000');
    const [analyzeAll, setAnalyzeAll] = useState(false);
    const [error, setError] = useState('');
    const [connected, setConnected] = useState(false);
    const [orgs, setOrgs] = useState<SentryOrganization[]>([]);
    const [projectsFor, setProjectsFor] = useState<{ org: string; list: SentryProject[] }>({ org: '', list: [] });
    const [listError, setListError] = useState('');

    // Fill the pickers with every organization the token can see, then the chosen org's projects.
    useEffect(() => {
        if (!connected) return;
        let live = true;
        apiJson<{ organizations: SentryOrganization[] }>('/ingest/sentry/organizations', {}, 'Failed to list organizations')
            .then(d => { if (live) { setOrgs(d.organizations); setListError(''); } })
            .catch(err => { if (live) setListError(formatError(err)); });
        return () => { live = false; };
    }, [connected]);

    const orgSlug = org.trim();
    const knownOrg = connected && orgs.some(o => o.slug === orgSlug);
    useEffect(() => {
        if (!knownOrg) return;
        let live = true;
        apiJson<{ projects: SentryProject[] }>(`/ingest/sentry/projects?org=${encodeURIComponent(orgSlug)}`, {}, 'Failed to list projects')
            .then(d => { if (live) setProjectsFor({ org: orgSlug, list: d.projects }); })
            .catch(err => { if (live) setListError(formatError(err)); });
        return () => { live = false; };
    }, [knownOrg, orgSlug]);
    const visibleOrgs = connected ? orgs : [];
    const projects = knownOrg && projectsFor.org === orgSlug ? projectsFor.list : [];

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
        const daysNum = Number(days.trim());
        if (!days.trim() || !Number.isInteger(daysNum) || daysNum < 1 || daysNum > 90) {
            setError('Days must be a whole number between 1 and 90.');
            return;
        }
        const hoursNum = Number(futureHours.trim());
        if (!futureHours.trim() || !Number.isFinite(hoursNum) || hoursNum < 1 || hoursNum > 100000) {
            setError('Forecast horizon must be between 1 and 100000 hours.');
            return;
        }
        try {
            await onAnalyze(org.trim(), analyzeAll ? 'all' : project.trim(), daysNum, hoursNum);
        } catch (err) {
            setError(formatError(err) || 'Failed to pull data from Sentry.');
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

            <div className="mb-6">
                <SentryConnection onStatus={setConnected} />
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl space-y-5">
                    <div>
                        <label htmlFor="sentry-org" className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Organization
                        </label>
                        <input
                            id="sentry-org"
                            type="text"
                            list="sentry-org-options"
                            autoComplete="off"
                            value={org}
                            onChange={(e) => setOrg(e.target.value)}
                            placeholder={visibleOrgs.length ? 'Choose or type an organization slug' : 'e.g. my-company'}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors"
                        />
                        <datalist id="sentry-org-options">
                            {visibleOrgs.map(o => <option key={o.slug} value={o.slug} label={o.name} />)}
                        </datalist>
                        {visibleOrgs.length > 0 && (
                            <p className="mt-1 text-xs text-slate-500">{visibleOrgs.length} organizations available. Click the field to pick one.</p>
                        )}
                        {listError && <p className="mt-1 text-xs text-amber-400">{listError}</p>}
                    </div>

                    <div>
                        <label htmlFor="sentry-project" className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Project
                        </label>
                        <input
                            id="sentry-project"
                            type="text"
                            list="sentry-project-options"
                            autoComplete="off"
                            value={project}
                            onChange={(e) => setProject(e.target.value)}
                            placeholder={analyzeAll ? 'All projects selected' : projects.length ? 'Choose or type a project slug' : 'e.g. web-app'}
                            disabled={analyzeAll}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                        <datalist id="sentry-project-options">
                            {projects.map(p => <option key={p.slug} value={p.slug} label={p.name} />)}
                        </datalist>
                        {projects.length > 0 && !analyzeAll && (
                            <p className="mt-1 text-xs text-slate-500">{projects.length} projects in {orgSlug}.</p>
                        )}
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
                        <label htmlFor="sentry-days" className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Look-back Window (days)
                        </label>
                        <input
                            id="sentry-days"
                            type="number"
                            min={1}
                            max={90}
                            value={days}
                            onChange={(e) => setDays(e.target.value)}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors"
                        />
                    </div>

                    <div>
                        <label htmlFor="sentry-future-hours" className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
                            Forecast Horizon (hours)
                        </label>
                        <input
                            id="sentry-future-hours"
                            type="number"
                            min={1}
                            max={100000}
                            value={futureHours}
                            onChange={(e) => setFutureHours(e.target.value)}
                            className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500 transition-colors"
                        />
                        <p className="mt-1 text-xs text-slate-500">How far ahead the reliability models project.</p>
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
                <div role="alert" className="mt-4 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-start space-x-3">
                    <AlertCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-rose-300">{error}</p>
                </div>
            )}

            <div className="mt-6 p-5 rounded-2xl bg-slate-900/30 border border-slate-800/50 space-y-3">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Setup Requirements</h3>
                <ul className="space-y-2 text-sm text-slate-500">
                    <li className="flex items-start space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span>Connect a Sentry personal or integration token above (scopes <code className="text-slate-300">event:read</code>, <code className="text-slate-300">project:read</code>, <code className="text-slate-300">org:read</code>), or set <code className="text-slate-300">SENTRY_AUTH_TOKEN</code> on the API server.</span>
                    </li>
                    <li className="flex items-start space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                        <span>sentry.io organizations in any region (US or EU) are found automatically. For self-hosted Sentry, set <code className="text-slate-300">SENTRY_BASE_URL</code> on the API server.</span>
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
