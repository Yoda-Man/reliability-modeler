'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Sliders, Tag, FileCode, Save, Loader2, CheckCircle2, FlaskConical, Target, AlertCircle } from 'lucide-react';
import { apiJson, formatError } from '@/lib/api';
import type { ConfigResponse, EngineSettings } from '@/lib/types';
import ErrorState from './ErrorState';

interface ConfigFormState extends EngineSettings {
    taxonomy_content: string;
}

const DEFAULTS: ConfigFormState = {
    multi_label: false,
    taxonomy_content: '',
    optimization_method: 'L-BFGS-B',
    tolerance: 1e-6,
};

type SaveStatus = { kind: 'idle' } | { kind: 'success' } | { kind: 'error'; message: string };

export default function ConfigView() {
    const [settings, setSettings] = useState<ConfigFormState>(DEFAULTS);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState<unknown>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<SaveStatus>({ kind: 'idle' });
    const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const [reloadKey, setReloadKey] = useState(0);

    useEffect(() => {
        let cancelled = false;
        apiJson<ConfigResponse>('/config', {}, 'Failed to load configuration')
            .then(data => {
                if (cancelled) return;
                setSettings({
                    multi_label: data.settings?.multi_label ?? DEFAULTS.multi_label,
                    optimization_method: data.settings?.optimization_method ?? DEFAULTS.optimization_method,
                    tolerance: data.settings?.tolerance ?? DEFAULTS.tolerance,
                    taxonomy_content: data.content ?? '',
                });
                setLoadError(null);
            })
            .catch((err: unknown) => {
                if (!cancelled) setLoadError(err);
            })
            .finally(() => {
                if (!cancelled) setIsLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [reloadKey]);

    useEffect(() => () => {
        if (successTimer.current) clearTimeout(successTimer.current);
    }, []);

    const retryLoad = () => {
        setIsLoading(true);
        setReloadKey(k => k + 1);
    };

    const handleSave = async () => {
        setIsSaving(true);
        setSaveStatus({ kind: 'idle' });
        if (successTimer.current) clearTimeout(successTimer.current);
        try {
            const payload: ConfigResponse = {
                content: settings.taxonomy_content,
                settings: {
                    multi_label: settings.multi_label,
                    optimization_method: settings.optimization_method,
                    tolerance: settings.tolerance,
                },
            };
            await apiJson<{ status: string }>('/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            }, 'Failed to save configuration');
            setSaveStatus({ kind: 'success' });
            successTimer.current = setTimeout(() => setSaveStatus({ kind: 'idle' }), 3000);
        } catch (err) {
            setSaveStatus({ kind: 'error', message: formatError(err) });
        } finally {
            setIsSaving(false);
        }
    };

    const toggleMultiLabel = () => setSettings(s => ({ ...s, multi_label: !s.multi_label }));
    const saveSuccess = saveStatus.kind === 'success';

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-slate-400">Loading configurations...</p>
            </div>
        );
    }

    if (loadError) {
        return (
            <div className="max-w-4xl animate-in fade-in duration-500 space-y-6">
                <h2 className="text-3xl font-bold text-white tracking-tight">System Configurations</h2>
                <ErrorState title="Could not load configuration" error={loadError} onRetry={retryLoad} />
            </div>
        );
    }

    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-3xl font-bold text-white mb-2 tracking-tight">System Configurations</h2>
                    <p className="text-slate-400 text-sm">Fine-tune the mathematical core and classification engine.</p>
                </div>
                <button
                    onClick={() => void handleSave()}
                    disabled={isSaving}
                    className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : saveSuccess ? <CheckCircle2 className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                    <span>{isSaving ? 'Saving...' : saveSuccess ? 'Saved' : 'Save Changes'}</span>
                </button>
            </div>

            {saveStatus.kind === 'error' && (
                <div role="alert" className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-start space-x-3">
                    <AlertCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-rose-300">{saveStatus.message}</p>
                </div>
            )}
            {saveSuccess && (
                <div role="status" className="mb-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-start space-x-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-emerald-300">Configuration saved.</p>
                </div>
            )}

            <div className="space-y-8">
                <section>
                    <div className="flex items-center space-x-3 mb-6">
                        <Tag className="w-5 h-5 text-blue-500" />
                        <h3 className="text-xl font-semibold text-white">Fault Taxonomy</h3>
                    </div>
                    <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl">
                        <p className="text-sm text-slate-400 mb-6 font-medium">
                            Define keyword mappings for automatic failure classification. (Format: <span className="text-blue-400">Category [keyword1, keyword2]</span>)
                        </p>
                        <p className="text-xs text-slate-500 -mt-4 mb-6">
                            To drop noise, add an Ignore line, e.g. <code className="text-blue-400">Ignore [miner.invalid, origin http://5.]</code>: events
                            matching an Ignore line are left out of models, graphs and rankings and counted as noise.
                        </p>
                        <textarea
                            value={settings.taxonomy_content}
                            onChange={(e) => setSettings({ ...settings, taxonomy_content: e.target.value })}
                            className="w-full h-64 bg-slate-950 rounded-xl p-6 border border-slate-800 font-mono text-xs text-blue-400 focus:outline-none focus:border-blue-500 transition-colors resize-none custom-scrollbar"
                            spellCheck={false}
                            placeholder="# Example:&#10;Hardware [cpu, ram, disk]"
                        />
                    </div>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-1 gap-6">
                    <button
                        onClick={toggleMultiLabel}
                        className={`p-6 rounded-2xl border transition-all text-left flex flex-col items-start ${settings.multi_label
                                ? "bg-blue-600/10 border-blue-500/50"
                                : "bg-slate-900/50 border-slate-800 hover:border-slate-700"
                            }`}
                    >
                        <Sliders className={`w-5 h-5 mb-4 ${settings.multi_label ? "text-blue-500" : "text-slate-400"}`} />
                        <h4 className="text-white font-semibold mb-2">Multi-Label Tagging</h4>
                        <p className="text-xs text-slate-400 leading-relaxed">
                            Allow failures to belong to multiple categories simultaneously if keywords overlap.
                        </p>
                        <div className="mt-4 flex items-center space-x-2">
                            <div className={`w-8 h-4 rounded-full relative transition-colors ${settings.multi_label ? "bg-blue-600" : "bg-slate-700"}`}>
                                <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${settings.multi_label ? "left-4.5" : "left-0.5"}`} />
                            </div>
                            <span className="text-[10px] font-bold uppercase text-slate-500">
                                {settings.multi_label ? "Enabled" : "Disabled"}
                            </span>
                        </div>
                    </button>
                </div>

                <section className="pt-8 border-t border-slate-900">
                    <div className="flex items-center space-x-3 mb-6">
                        <FileCode className="w-5 h-5 text-blue-500" />
                        <h3 className="text-xl font-semibold text-white">Advanced Engine Settings</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6 rounded-2xl bg-blue-600/5 border border-blue-500/10 shadow-inner">
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center">
                                <Target className="w-3 h-3 mr-2" />
                                Optimization Algorithm
                            </label>
                            <select
                                value={settings.optimization_method}
                                onChange={(e) => setSettings({ ...settings, optimization_method: e.target.value })}
                                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-blue-500 transition-colors"
                            >
                                <option value="L-BFGS-B">L-BFGS-B (Recommended)</option>
                                <option value="TNC">TNC (Truncated Newton)</option>
                                <option value="SLSQP">SLSQP</option>
                                <option value="Nelder-Mead">Nelder-Mead</option>
                            </select>
                            <p className="text-[10px] text-slate-500">Determines the strategy for finding maximum likelihood estimates.</p>
                        </div>

                        <div className="space-y-2">
                            <label className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center">
                                <FlaskConical className="w-3 h-3 mr-2" />
                                Fitting Tolerance
                            </label>
                            <input
                                type="number"
                                step="1e-12"
                                value={settings.tolerance}
                                onChange={(e) => {
                                    const v = parseFloat(e.target.value);
                                    if (Number.isFinite(v)) setSettings({ ...settings, tolerance: v });
                                }}
                                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-blue-500 transition-colors"
                            />
                            <p className="text-[10px] text-slate-500">The precision threshold for convergence (Default: 1e-6).</p>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );
}
