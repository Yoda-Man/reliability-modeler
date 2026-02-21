'use client';

import React from 'react';
import { Shield, Lock, Eye, FileText, Database, Share2 } from 'lucide-react';

export default function PrivacyPolicy() {
    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700 pb-20">
            <div className="flex items-center space-x-4 mb-8">
                <div className="w-12 h-12 rounded-2xl bg-blue-600/10 flex items-center justify-center">
                    <Shield className="text-blue-500 w-6 h-6" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Privacy Policy</h2>
                    <p className="text-slate-400 text-sm">Last updated: February 21, 2026</p>
                </div>
            </div>

            <div className="space-y-12">
                <section>
                    <div className="flex items-center space-x-3 mb-4 text-white font-semibold text-xl">
                        <Lock className="w-5 h-5 text-emerald-500" />
                        <h3>Data Sovereignty</h3>
                    </div>
                    <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl">
                        <p className="text-slate-300 leading-relaxed">
                            The Reliability Modeler is designed as a self-hosted, containerized application.
                            <span className="text-emerald-500 font-bold px-1">All data processed remains within your Docker environment.</span>
                            None of your uploaded CSV files, error descriptions, or analysis results are ever transmitted to external servers or third parties.
                        </p>
                    </div>
                </section>

                <section>
                    <div className="flex items-center space-x-3 mb-4 text-white font-semibold text-xl">
                        <Database className="w-5 h-5 text-blue-500" />
                        <h3>Data Retention</h3>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800">
                            <h4 className="text-white font-medium mb-2 flex items-center">
                                <FileText className="w-4 h-4 mr-2 text-slate-500" />
                                Uploaded Files
                            </h4>
                            <p className="text-xs text-slate-400 leading-relaxed">
                                CSV files are processed in-memory and temporarily stored in `/app/temp_uploads` during analysis. They are automatically deleted immediately after processing is complete.
                            </p>
                        </div>
                        <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800">
                            <h4 className="text-white font-medium mb-2 flex items-center">
                                <Eye className="w-4 h-4 mr-2 text-slate-500" />
                                Analysis Logs
                            </h4>
                            <p className="text-xs text-slate-400 leading-relaxed">
                                Summaries of your analysis are stored in `/app/output/logs` to power the "Log Archives" feature. You have full control over these files via the host filesystem.
                            </p>
                        </div>
                    </div>
                </section>

                <section>
                    <div className="flex items-center space-x-3 mb-4 text-white font-semibold text-xl">
                        <Share2 className="w-5 h-5 text-rose-500" />
                        <h3>Third-Party Analytics</h3>
                    </div>
                    <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl border-l-rose-500/50">
                        <p className="text-slate-300 leading-relaxed italic">
                            "We believe that engineering data is your most sensitive asset."
                        </p>
                        <p className="mt-4 text-sm text-slate-400 leading-relaxed">
                            The application contains zero telemetry, zero tracking cookies, and zero third-party analytics scripts (e.g., Google Analytics). Your usage patterns are private to you.
                        </p>
                    </div>
                </section>

                <footer className="pt-8 border-t border-slate-800">
                    <p className="text-xs text-slate-500 text-center uppercase tracking-[0.2em] font-bold">
                        Guaranteed Confidential • Locally Orchestrated • User Owned
                    </p>
                </footer>
            </div>
        </div>
    );
}
