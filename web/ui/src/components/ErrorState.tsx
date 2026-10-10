'use client';

import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { ApiError, formatError } from '@/lib/api';

interface ErrorStateProps {
    title: string;
    error: unknown;
    onRetry?: () => void;
}

/** Visible error panel shown when an API request fails (distinct from empty states). */
export default function ErrorState({ title, error, onRetry }: ErrorStateProps) {
    const status = error instanceof ApiError && error.status > 0 ? error.status : null;
    return (
        <div role="alert" className="p-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-start space-x-4">
            <AlertTriangle className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
                <h4 className="text-sm font-semibold text-rose-200">
                    {title}
                    {status !== null && <span className="ml-2 font-mono text-xs text-rose-400">HTTP {status}</span>}
                </h4>
                <p className="mt-1 text-sm text-rose-300 break-words">
                    {error instanceof ApiError ? error.detail : formatError(error)}
                </p>
                {onRetry && (
                    <button
                        onClick={onRetry}
                        className="mt-3 inline-flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white transition-colors"
                    >
                        <RefreshCw className="w-3 h-3" />
                        <span>Retry</span>
                    </button>
                )}
            </div>
        </div>
    );
}
