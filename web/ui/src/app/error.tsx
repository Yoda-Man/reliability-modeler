'use client'; // Error boundaries must be Client Components

import { useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';

export default function RouteError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-[#020617] text-slate-200 flex items-center justify-center p-8">
      <div role="alert" className="max-w-md w-full p-8 rounded-2xl bg-slate-900/60 border border-rose-500/20 text-center space-y-4">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Something went wrong</h2>
        <p className="text-sm text-slate-400">
          The interface hit an unexpected error.
          {error.digest && <span className="block mt-1 font-mono text-xs text-slate-500">Reference: {error.digest}</span>}
        </p>
        <button
          onClick={() => retry()}
          className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
