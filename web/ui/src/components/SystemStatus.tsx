'use client';

import React, { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { classifyHealth, type HealthSummary, type SystemState } from '@/lib/health';
import type { HealthResponse } from '@/lib/types';

const POLL_INTERVAL_MS = 30_000;

const DOT: Record<SystemState, string> = {
    checking: 'bg-slate-500',
    ok: 'bg-emerald-500 animate-pulse',
    degraded: 'bg-amber-400',
    error: 'bg-rose-500',
    unreachable: 'bg-rose-500',
};

/** Live API health badge; polls /api/health every 30 seconds. */
export default function SystemStatus() {
    const [summary, setSummary] = useState<HealthSummary>({ state: 'checking', label: 'Checking...' });

    useEffect(() => {
        let cancelled = false;
        const check = async () => {
            let next: HealthSummary;
            try {
                const res = await apiFetch('/health', { timeout: 10_000, cache: 'no-store' });
                let body: Partial<HealthResponse> | null = null;
                try {
                    body = (await res.json()) as Partial<HealthResponse>;
                } catch {
                    body = null;
                }
                next = classifyHealth(res.status, body);
            } catch {
                next = classifyHealth(null, null);
            }
            if (!cancelled) setSummary(next);
        };
        void check();
        const id = setInterval(() => void check(), POLL_INTERVAL_MS);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, []);

    return (
        <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800" role="status" aria-live="polite">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2 font-bold">System Status</p>
            <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${DOT[summary.state]}`} />
                <span className="text-xs text-slate-300 font-medium tracking-wide">{summary.label}</span>
                {summary.version && <span className="text-[10px] text-slate-600 font-mono ml-auto">v{summary.version}</span>}
            </div>
            {summary.detail && <p className="mt-1 text-[10px] text-slate-500">{summary.detail}</p>}
        </div>
    );
}
