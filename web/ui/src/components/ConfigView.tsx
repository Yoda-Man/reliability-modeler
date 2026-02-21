'use client';

import React, { useState, useEffect } from 'react';
import { Settings, Sliders, Hash, Tag, FileCode, Save, Loader2, CheckCircle2, FlaskConical, Target } from 'lucide-react';

interface ConfigSettings {
    multi_label: boolean;
    data_scrubbing: boolean;
    taxonomy_content: string;
    optimization_method: string;
    tolerance: number;
}

export default function ConfigView() {
    const [settings, setSettings] = useState<ConfigSettings>({
        multi_label: false,
        data_scrubbing: true,
        taxonomy_content: '',
        optimization_method: 'L-BFGS-B',
        tolerance: 1e-10
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);

    useEffect(() => {
        fetchConfig();
    }, []);

    const fetchConfig = async () => {
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/config`);
            if (response.ok) {
                const data = await response.json();
                setSettings(data);
            }
        } catch (error) {
            console.error('Failed to fetch config:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSave = async () => {
        setIsSaving(true);
        setSaveSuccess(false);
        try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            if (response.ok) {
                setSaveSuccess(true);
                setTimeout(() => setSaveSuccess(false), 3000);
            }
        } catch (error) {
            console.error('Failed to save config:', error);
            alert('Failed to save configuration.');
        } finally {
            setIsSaving(false);
        }
    };

    const toggleMultiLabel = () => setSettings(s => ({ ...s, multi_label: !s.multi_label }));
    const toggleScrubbing = () => setSettings(s => ({ ...s, data_scrubbing: !s.data_scrubbing }));

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-slate-400">Loading configurations...</p>
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
                    onClick={handleSave}
                    disabled={isSaving}
                    className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : saveSuccess ? <CheckCircle2 className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                    <span>{isSaving ? 'Saving...' : saveSuccess ? 'Saved' : 'Save Changes'}</span>
                </button>
            </div>

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
                        <textarea
                            value={settings.taxonomy_content}
                            onChange={(e) => setSettings({ ...settings, taxonomy_content: e.target.value })}
                            className="w-full h-64 bg-slate-950 rounded-xl p-6 border border-slate-800 font-mono text-xs text-blue-400 focus:outline-none focus:border-blue-500 transition-colors resize-none custom-scrollbar"
                            spellCheck={false}
                            placeholder="# Example:&#10;Hardware [cpu, ram, disk]"
                        />
                    </div>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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

                    <button
                        onClick={toggleScrubbing}
                        className={`p-6 rounded-2xl border transition-all text-left flex flex-col items-start ${settings.data_scrubbing
                                ? "bg-emerald-600/10 border-emerald-500/50"
                                : "bg-slate-900/50 border-slate-800 hover:border-slate-700"
                            }`}
                    >
                        <Hash className={`w-5 h-5 mb-4 ${settings.data_scrubbing ? "text-emerald-500" : "text-slate-400"}`} />
                        <h4 className="text-white font-semibold mb-2">Auto Data Scrubbing</h4>
                        <p className="text-xs text-slate-400 leading-relaxed">
                            Automatically filters out malformed timestamps or duplicate entries during ingestion.
                        </p>
                        <div className="mt-4 flex items-center space-x-2 text-emerald-500 font-bold text-[10px] uppercase">
                            <div className={`w-8 h-4 rounded-full relative transition-colors ${settings.data_scrubbing ? "bg-emerald-600" : "bg-slate-700"}`}>
                                <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${settings.data_scrubbing ? "left-4.5" : "left-0.5"}`} />
                            </div>
                            <span className="text-[10px] font-bold uppercase text-slate-500">
                                {settings.data_scrubbing ? "Enabled" : "Disabled"}
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
                                onChange={(e) => setSettings({ ...settings, tolerance: parseFloat(e.target.value) })}
                                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-blue-500 transition-colors"
                            />
                            <p className="text-[10px] text-slate-500">The precision threshold for convergence (Default: 1e-10).</p>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );
}
