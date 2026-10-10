import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#020617] text-slate-200 flex items-center justify-center p-8">
      <div className="max-w-md w-full p-8 rounded-2xl bg-slate-900/60 border border-slate-800 text-center space-y-4">
        <p className="font-mono text-sm text-blue-400">404</p>
        <h2 className="text-xl font-bold text-white">Page not found</h2>
        <p className="text-sm text-slate-400">The page you requested does not exist.</p>
        <Link
          href="/"
          className="inline-block px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
        >
          Back to Reliability Modeler
        </Link>
      </div>
    </div>
  );
}
