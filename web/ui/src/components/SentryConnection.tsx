'use client';

import React, { useEffect, useState } from 'react';
import { KeyRound, Loader2, PlugZap, ShieldCheck } from 'lucide-react';
import { apiJson, formatError } from '@/lib/api';
import type { SentryStatus } from '@/lib/types';

const TOKEN_LABEL: Record<string, string> = {
    personal: 'personal token',
    integration: 'integration token',
    organization: 'organization token',
};

/** Connect Sentry by pasting a token in the UI. The API checks it with Sentry, stores it privately and never returns it. */
export default function SentryConnection({ onStatus }: { onStatus: (configured: boolean) => void }) {
    const [status, setStatus] = useState<SentryStatus | null>(null);
    const [token, setToken] = useState('');
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

    useEffect(() => {
        let live = true;
        apiJson<SentryStatus>('/config/sentry', {}, 'Failed to read Sentry connection')
            .then(s => { if (live) { setStatus(s); onStatus(s.configured); } })
            .catch(err => { if (live) setMessage({ kind: 'error', text: formatError(err) }); });
        return () => { live = false; };
    }, [onStatus]);

    const submit = async (value: string) => {
        setBusy(true);
        setMessage(null);
        try {
            const s = await apiJson<SentryStatus>('/config/sentry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: value }),
            }, value ? 'Failed to save Sentry token' : 'Failed to remove Sentry token');
            setStatus(s);
            onStatus(s.configured);
            setToken('');
            setMessage({
                kind: 'ok',
                text: value ? `Connected. Your token can see ${s.organizations ?? 0} organization(s).` : 'Token removed.',
            });
        } catch (err) {
            setMessage({ kind: 'error', text: formatError(err) });
        } finally {
            setBusy(false);
        }
    };

    const connected = status?.configured;
    const fromEnv = status?.source === 'environment';

    return (
        <section aria-labelledby="sentry-connection-title"
            className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/50 backdrop-blur-xl space-y-4">
            <div className="flex items-center justify-between gap-3">
                <h3 id="sentry-connection-title" className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center space-x-2">
                    <PlugZap className="w-4 h-4 text-purple-400" />
                    <span>Sentry Connection</span>
                </h3>
                {status && (
                    <span className={`text-xs font-semibold flex items-center space-x-1.5 ${connected ? 'text-emerald-400' : 'text-amber-400'}`}>
                        <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                        <span>{connected ? 'Connected' : 'Not connected'}</span>
                    </span>
                )}
            </div>

            {connected && (
                <p className="text-sm text-slate-400 flex items-center space-x-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>
                        Using a {TOKEN_LABEL[status.token_type] ?? 'token'}{' '}
                        {fromEnv ? <>set on the server (<code className="text-slate-300">SENTRY_AUTH_TOKEN</code>). Change it there.</> : 'saved in this app.'}
                    </span>
                </p>
            )}

            {status && !fromEnv && (
                <form onSubmit={e => { e.preventDefault(); if (token.trim()) void submit(token.trim()); }} className="space-y-3">
                    <label htmlFor="sentry-token" className="block text-xs text-slate-400">
                        {connected ? 'Replace token' : 'Sentry auth token'}
                    </label>
                    <div className="flex gap-2">
                        <input id="sentry-token" type="password" autoComplete="off" spellCheck={false}
                            value={token} onChange={e => setToken(e.target.value)} placeholder="sntryu_…"
                            className="flex-1 px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-600 focus:outline-none focus:border-purple-500" />
                        <button type="submit" disabled={busy || !token.trim()}
                            className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
                            <span>{connected ? 'Replace' : 'Connect'}</span>
                        </button>
                        {connected && (
                            <button type="button" disabled={busy} onClick={() => void submit('')}
                                className="px-4 py-2.5 rounded-xl border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 text-sm disabled:opacity-50">
                                Remove
                            </button>
                        )}
                    </div>
                    {!connected && (
                        <p className="text-xs text-slate-500 leading-relaxed">
                            In Sentry: avatar → <b>User Settings → Personal Tokens → Create New Token</b> with{' '}
                            <code className="text-slate-300">event:read</code>, <code className="text-slate-300">project:read</code> and{' '}
                            <code className="text-slate-300">org:read</code>. The token is checked with Sentry, stored privately on the server and never shown again.
                            Organization tokens (<code className="text-slate-300">sntrys_</code>) can&apos;t read events.
                        </p>
                    )}
                </form>
            )}

            {message && (
                <p role={message.kind === 'error' ? 'alert' : 'status'}
                    className={`text-sm ${message.kind === 'error' ? 'text-rose-300' : 'text-emerald-300'}`}>
                    {message.text}
                </p>
            )}
        </section>
    );
}
