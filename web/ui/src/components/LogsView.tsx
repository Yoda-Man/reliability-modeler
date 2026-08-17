'use client';

import React, { useState, useEffect } from 'react';
import { History, FileText, Calendar, Search, Loader2, ChevronLeft, ChevronRight } from 'lucide-react';
import { apiFetch } from '@/app/apiClient';

const PAGE_SIZE = 50;

interface LogEntry {
    id: string;
    date: string;
    file: string;
    status: string;
    summary: {
        total_failures: number;
        duration_hours: number;
    };
}

interface LogsResponse {
    total: number;
    logs: LogEntry[];
}

export default function LogsView() {
    const [data, setData] = useState<LogsResponse>({ total: 0, logs: [] });
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [offset, setOffset] = useState(0);

    const fetchLogs = async (newOffset: number = 0) => {
        setIsLoading(true);
        try {
            const response = await apiFetch(`/logs?limit=${PAGE_SIZE}&offset=${newOffset}`);
            if (response.ok) {
                const json: LogsResponse = await response.json();
                setData(json);
                setOffset(newOffset);
            }
        } catch (error) {
            console.error('Failed to fetch logs:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs(0);
    }, []);

    const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
    const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

    const filteredLogs = data.logs.filter(log =>
        log.file.toLowerCase().includes(searchQuery.toLowerCase()) ||
        log.id.toLowerCase().includes(searchQuery.toLowerCase())
    );

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-slate-400">Loading analysis archives...</p>
            </div>
        );
    }

    return (
        <div className="max-w-5xl animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
                <div>
                    <h2 className="text-3xl font-bold text-white mb-2 tracking-tight">Analysis Archive</h2>
                    <p className="text-slate-400 text-sm">
                        {data.total > 0
                            ? `${data.total} total analyses · showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.total)}`
                            : 'Review and compare past reliability assessments.'}
                    </p>
                </div>

                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search reports..."
                        className="pl-10 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-300 focus:outline-none focus:border-blue-500 transition-colors w-full md:w-64"
                    />
                </div>
            </div>

            <div className="rounded-2xl bg-slate-900/50 border border-slate-800 backdrop-blur-xl overflow-hidden min-h-[400px]">
                {filteredLogs.length > 0 ? (
                    <table className="w-full text-left">
                        <thead>
                            <tr className="border-b border-slate-800 bg-slate-950/30">
                                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-widest">ID</th>
                                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-widest">Date</th>
                                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-widest">Filename</th>
                                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-widest">Failures</th>
                                <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-widest">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                            {filteredLogs.map((log) => (
                                <tr key={log.id} className="hover:bg-slate-800/20 transition-colors group">
                                    <td className="px-6 py-4 font-mono text-xs text-blue-400">{log.id}</td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center text-sm text-slate-300">
                                            <Calendar className="w-3 h-3 mr-2 text-slate-500" />
                                            {log.date}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center text-sm text-slate-300">
                                            <FileText className="w-3 h-3 mr-2 text-slate-500" />
                                            {log.file}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-xs text-slate-500 font-medium">
                                        {log.summary.total_failures} events
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className={`
                      px-2 py-0.5 rounded-full text-[10px] font-bold uppercase
                      ${log.status === 'Completed' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-700/30 text-slate-500'}
                    `}>
                                            {log.status}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="flex flex-col items-center justify-center p-20 text-center">
                        <History className="w-16 h-16 text-slate-800 mb-6" />
                        <h4 className="text-white font-semibold mb-2 text-lg">No Analysis History Found</h4>
                        <p className="text-sm text-slate-500 max-w-sm mx-auto">
                            Run your first reliability analysis to see reports archived here. This view automatically syncs with the engine's output.
                        </p>
                    </div>
                )}
            </div>

            {/* Pagination Controls */}
            {data.total > PAGE_SIZE && (
                <div className="flex items-center justify-between mt-4 px-2">
                    <span className="text-xs text-slate-500">
                        Page {currentPage} of {totalPages}
                    </span>
                    <div className="flex space-x-2">
                        <button
                            onClick={() => fetchLogs(Math.max(0, offset - PAGE_SIZE))}
                            disabled={offset === 0}
                            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                            onClick={() => fetchLogs(offset + PAGE_SIZE)}
                            disabled={offset + PAGE_SIZE >= data.total}
                            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
