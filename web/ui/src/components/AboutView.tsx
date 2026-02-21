'use client';

import React from 'react';
import { Github, Globe, Heart, ShieldCheck, Mail, Linkedin } from 'lucide-react';

export default function AboutView() {
    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700 pb-20">
            <div className="p-12 rounded-[2.5rem] bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800 shadow-2xl relative overflow-hidden">
                {/* Decorative elements */}
                <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl -mr-32 -mt-32" />
                <div className="absolute bottom-0 left-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl -ml-32 -mb-32" />

                <div className="relative z-10 flex flex-col items-center text-center">
                    <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-blue-600 to-emerald-500 flex items-center justify-center shadow-2xl mb-8 group transition-transform hover:scale-105">
                        <ShieldCheck className="text-white w-12 h-12" />
                    </div>

                    <h2 className="text-4xl font-extrabold text-white mb-4 tracking-tight">
                        Reliability <span className="text-blue-500">Modeler</span>
                    </h2>
                    <p className="text-slate-400 text-lg max-w-xl mx-auto mb-10 leading-relaxed">
                        A free, open-source engine built to empower software teams with data-driven stability metrics and predictive engineering.
                    </p>

                    <div className="flex items-center space-x-6 mb-12">
                        <SocialLink href="https://github.com/Yoda-Man/" icon={<Github size={20} />} label="GitHub" />
                        <div className="h-4 w-[1px] bg-slate-800" />
                        <SocialLink href="http://www.workforceanalytics.co.za/" icon={<Globe size={20} />} label="Website" />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full text-left">
                        <AboutCard
                            title="The Vision"
                            text="To make advanced software reliability growth modeling (SRGM) accessible to every engineering team globally."
                        />
                        <AboutCard
                            title="The Ethics"
                            text="Zero telemetry. Zero cookies. 100% self-hosted privacy by design."
                        />
                        <AboutCard
                            title="The Stack"
                            text="Built with FastAPI, Next.js 14, and Scipy. Orchestrated via Docker for zero-friction setup."
                        />
                    </div>

                    <div className="mt-16 pt-8 border-t border-slate-900 w-full flex flex-col items-center">
                        <div className="flex items-center space-x-2 text-slate-500 text-sm mb-4">
                            <span>Made with</span>
                            <Heart size={14} className="text-rose-500 fill-rose-500" />
                            <span>for the Engineering Community</span>
                        </div>
                        <p className="text-[10px] text-slate-600 font-bold uppercase tracking-[0.3em]">
                            © 2026 Yoda-Man • Released under MIT License
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

function SocialLink({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
    return (
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-2 text-slate-400 hover:text-white transition-colors group"
        >
            <span className="p-2 rounded-lg bg-slate-900 border border-slate-800 group-hover:bg-slate-800 transition-colors">
                {icon}
            </span>
            <span className="text-sm font-semibold">{label}</span>
        </a>
    );
}

function AboutCard({ title, text }: { title: string; text: string }) {
    return (
        <div className="p-6 rounded-2xl bg-slate-950/50 border border-slate-900">
            <h4 className="text-xs font-bold text-blue-500 uppercase tracking-widest mb-3">{title}</h4>
            <p className="text-xs text-slate-400 leading-relaxed">{text}</p>
        </div>
    );
}
