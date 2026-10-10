'use client'; // Replaces the root layout when it errors, so it must render <html> and <body>.

import { useEffect } from 'react';
import './globals.css';

export default function GlobalError({
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
    <html lang="en">
      <body className="font-sans antialiased min-h-screen bg-[#020617] text-slate-200 flex items-center justify-center p-8">
        <div role="alert" className="max-w-md w-full p-8 rounded-2xl bg-slate-900/60 border border-rose-500/20 text-center space-y-4">
          <h2 className="text-xl font-bold text-white">Reliability Modeler failed to load</h2>
          <p className="text-sm text-slate-400">
            An unexpected error occurred.
            {error.digest && <span className="block mt-1 font-mono text-xs text-slate-500">Reference: {error.digest}</span>}
          </p>
          <button
            onClick={() => retry()}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
