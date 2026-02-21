'use client';

import React from 'react';
import { Book, CheckCircle2, FileJson, Info, Layout, PlayCircle, Settings, Terminal } from 'lucide-react';

export default function UserManualView() {
    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700 pb-20">
            <div className="flex items-center space-x-4 mb-8">
                <div className="w-12 h-12 rounded-2xl bg-blue-600/10 flex items-center justify-center">
                    <Book className="text-blue-500 w-6 h-6" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">System User Manual</h2>
                    <p className="text-slate-400 text-sm">Everything you need to master the Reliability engine.</p>
                </div>
            </div>

            <div className="space-y-10">
                <ManualSection
                    icon={<PlayCircle className="text-blue-500" />}
                    title="Getting Started"
                    description="Run your first analysis in seconds."
                >
                    <ol className="space-y-4">
                        <li className="flex items-start bg-slate-900/40 p-4 rounded-xl border border-slate-800">
                            <span className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs font-bold mr-4 shrink-0">1</span>
                            <p className="text-sm text-slate-300 leading-relaxed">Navigate to the <strong>Dashboard</strong> and locate the upload zone.</p>
                        </li>
                        <li className="flex items-start bg-slate-900/40 p-4 rounded-xl border border-slate-800">
                            <span className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs font-bold mr-4 shrink-0">2</span>
                            <p className="text-sm text-slate-300 leading-relaxed">Drag your failure CSV file. Ensure it contains a <strong>Timestamp</strong> and <strong>Description</strong>.</p>
                        </li>
                        <li className="flex items-start bg-slate-900/40 p-4 rounded-xl border border-slate-800">
                            <span className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs font-bold mr-4 shrink-0">3</span>
                            <p className="text-sm text-slate-300 leading-relaxed">The engine will auto-categorize your faults and fit the <strong>GO/MO</strong> models instantly.</p>
                        </li>
                    </ol>
                </ManualSection>

                <ManualSection
                    icon={<Layout className="text-emerald-500" />}
                    title="Dashboard Components"
                    description="Understanding the management KPIs."
                >
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <InfoCard title="MTBF" text="Mean Time Between Failures. Higher values indicate a more stable release." />
                        <InfoCard title="Residuals" text="The estimated number of hidden bugs still lurking in the code." />
                        <InfoCard title="AIC" text="A mathematical score for fit quality. The engine recommends the model with the lowest AIC." />
                        <InfoCard title="Intensity" text="The frequency of failures. A downward trend is required for a 'GO' release decision." />
                    </div>
                </ManualSection>

                <ManualSection
                    icon={<Settings className="text-rose-500" />}
                    title="Advanced Configuration"
                    description="Control the engine's cognitive and mathematical behavior."
                >
                    <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800 space-y-6">
                        <div>
                            <h4 className="text-white font-medium mb-2 flex items-center">
                                <Terminal className="w-4 h-4 mr-2 text-slate-500" />
                                Fault Taxonomy Editor
                            </h4>
                            <p className="text-xs text-slate-400 leading-relaxed">
                                In the <strong>Configurations</strong> tab, use the live editor to map keywords to categories.
                                Format: <code className="text-blue-400">CategoryName [keyword1, keyword2]</code>.
                                The engine re-tags your entire dataset on every run.
                            </p>
                        </div>
                        <div>
                            <h4 className="text-white font-medium mb-2 flex items-center">
                                <Settings className="w-4 h-4 mr-2 text-slate-500" />
                                Engine Solvers
                            </h4>
                            <p className="text-xs text-slate-400 leading-relaxed">
                                For complex datasets, switch to the <strong>Nelder-Mead</strong> algorithm for more robust convergence,
                                or <strong>L-BFGS-B</strong> for high-speed multi-variate optimization.
                            </p>
                        </div>
                    </div>
                </ManualSection>

                <section className="pt-8 flex justify-center border-t border-slate-800">
                    <div className="flex items-center space-x-2 text-xs text-slate-500 font-bold uppercase tracking-widest">
                        <CheckCircle2 className="w-4 h-4 text-blue-500" />
                        <span>Certification Ready • V2.0.0</span>
                    </div>
                </section>
            </div>
        </div>
    );
}

function ManualSection({ icon, title, description, children }: { icon: React.ReactNode, title: string, description: string, children: React.ReactNode }) {
    return (
        <section>
            <div className="flex items-center space-x-3 mb-2">
                {icon}
                <h3 className="text-xl font-semibold text-white tracking-tight">{title}</h3>
            </div>
            <p className="text-sm text-slate-500 mb-6">{description}</p>
            {children}
        </section>
    );
}

function InfoCard({ title, text }: { title: string, text: string }) {
    return (
        <div className="p-4 rounded-xl bg-slate-900/30 border border-slate-800/50">
            <h4 className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-1">{title}</h4>
            <p className="text-xs text-slate-400 leading-relaxed">{text}</p>
        </div>
    );
}
