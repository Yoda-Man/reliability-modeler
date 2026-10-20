'use client';

import React from 'react';
import { AlertTriangle, Bug, ExternalLink } from 'lucide-react';
import type { AnalysisWarning, IgnoredSummary, TopIssue } from '@/lib/types';

function shortDate(iso: string): string {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function TopIssues({ issues }: { issues?: TopIssue[] }) {
    if (!issues?.length) return null;
    return (
        <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl">
            <h3 className="text-sm font-semibold text-white flex items-center space-x-2">
                <Bug className="w-4 h-4 text-rose-400" />
                <span>Top Issues</span>
            </h3>
            <p className="text-[10px] text-slate-500 mt-1 mb-4">Fix these first — each row is one bug in Sentry.</p>
            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="text-[10px] text-slate-500 uppercase tracking-widest text-left">
                            <th className="font-bold pb-2 pr-3">#</th>
                            <th className="font-bold pb-2 pr-3">Issue</th>
                            <th className="font-bold pb-2 pr-3">Project</th>
                            <th className="font-bold pb-2 pr-3">Category</th>
                            <th className="font-bold pb-2 pr-3">Events</th>
                            <th className="font-bold pb-2 pr-3">Last seen</th>
                            <th className="pb-2"><span className="sr-only">Link</span></th>
                        </tr>
                    </thead>
                    <tbody>
                        {issues.map((issue, i) => {
                            const pct = Math.round(issue.share * 100);
                            const where = issue.culprit || issue.location;
                            return (
                                <tr key={issue.group_id} className="border-t border-slate-800/60 align-top">
                                    <td className="py-2 pr-3 font-mono text-slate-500">{i + 1}</td>
                                    <td className="py-2 pr-3 max-w-xs">
                                        <div className="flex items-center gap-2">
                                            <span className="text-slate-200 truncate" title={issue.title}>{issue.title}</span>
                                            {issue.burst && (
                                                <span className="shrink-0 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[9px] font-bold uppercase tracking-wider"
                                                    title="Most of this issue's events arrived within 24 hours">burst</span>
                                            )}
                                        </div>
                                        {where && <p className="text-[10px] text-slate-500 font-mono truncate" title={where}>{where}</p>}
                                    </td>
                                    <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">{issue.project}</td>
                                    <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">{issue.category}</td>
                                    <td className="py-2 pr-3 min-w-[9rem]">
                                        <div className="flex items-center gap-2">
                                            <div className="flex-1 h-2 bg-slate-800/60 rounded overflow-hidden">
                                                <div className="h-full bg-rose-500/70 rounded" style={{ width: `${pct}%` }} />
                                            </div>
                                            <span className="font-mono text-slate-300 whitespace-nowrap">{issue.count} · {pct}%</span>
                                        </div>
                                    </td>
                                    <td className="py-2 pr-3 text-slate-400 whitespace-nowrap" title={issue.last_seen}>{shortDate(issue.last_seen)}</td>
                                    <td className="py-2 whitespace-nowrap">
                                        {issue.sentry_url && (
                                            <a href={issue.sentry_url} target="_blank" rel="noopener noreferrer"
                                                className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300">
                                                Sentry <ExternalLink className="w-3 h-3" aria-hidden="true" />
                                            </a>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

/** Amber notices for `warnings`. `skipTruncated` avoids a second truncated note when the Dashboard already shows one. */
export function AnalysisWarnings({ warnings, ignored, skipTruncated }: { warnings?: AnalysisWarning[]; ignored?: IgnoredSummary; skipTruncated: boolean }) {
    const shown = (warnings ?? []).filter(w => !(skipTruncated && w.code === 'truncated'));
    return (
        <>
            {shown.map((w, i) => (
                <div key={`${w.code}-${i}`} role="note" className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start space-x-3">
                    <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                    <div className="text-sm text-amber-200">
                        <p>{w.message}</p>
                        {w.code === 'noise_ignored' && ignored && ignored.count > 0 && (
                            <details className="mt-1 text-xs text-amber-200/80">
                                <summary className="cursor-pointer">{ignored.count} event(s) ignored by the taxonomy</summary>
                                <ul className="mt-1 space-y-0.5">
                                    {ignored.top_titles.map(t => <li key={t.title}>{t.count} × {t.title}</li>)}
                                </ul>
                            </details>
                        )}
                    </div>
                </div>
            ))}
        </>
    );
}
