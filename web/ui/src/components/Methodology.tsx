'use client';

import React from 'react';
import { BookOpen, Target, Shield, Info } from 'lucide-react';

export default function MethodologyView() {
    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700">
            <h2 className="text-3xl font-bold text-white mb-6 tracking-tight">Analytical Methodology</h2>
            <p className="text-slate-400 mb-12 text-lg leading-relaxed">
                The Reliability Modeler employs Software Reliability Growth Models (SRGMs) to characterize
                the fault-removal process and predict future system behavior.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl">
                    <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center mb-4">
                        <Shield className="text-blue-500" />
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-3">Goel-Okumoto (GO)</h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                        A non-homogeneous Poisson process (NHPP) model that assumes failures occur at a rate
                        that decreases exponentially as faults are removed. Ideal for systems with stable
                        testing environments.
                    </p>
                </div>

                <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl">
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center mb-4">
                        <Target className="text-emerald-500" />
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-3">Musa-Okumoto (MO)</h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                        Also known as the Logarithmic Poisson Execution Time model. It assumes that earlier
                        faults contribute more to the failure rate than later ones, often providing a
                        more realistic "pessimistic" bound.
                    </p>
                </div>
            </div>

            <div className="space-y-6">
                <h4 className="text-lg font-semibold text-white flex items-center">
                    <Info className="w-5 h-5 mr-3 text-blue-400" />
                    Interpretation Guide
                </h4>
                <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800">
                    <ul className="space-y-4">
                        <li className="flex items-start">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 mr-3 shrink-0" />
                            <p className="text-sm text-slate-400">
                                <strong className="text-slate-200">AIC (Akaike Information Criterion):</strong> Lower values indicate a better statistical fit while penalizing over-complexity.
                            </p>
                        </li>
                        <li className="flex items-start">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 mr-3 shrink-0" />
                            <p className="text-sm text-slate-400">
                                <strong className="text-slate-200">Intensity:</strong> Represents the failure frequency. A downward trend indicates increasing system maturity.
                            </p>
                        </li>
                        <li className="flex items-start">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 mr-3 shrink-0" />
                            <p className="text-sm text-slate-400">
                                <strong className="text-slate-200">Residuals:</strong> The estimated number of faults remaining in the system before it reaches theoretical zero-failure state.
                            </p>
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    );
}
