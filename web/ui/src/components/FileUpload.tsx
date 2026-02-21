'use client';

import React, { useState } from 'react';
import { Upload, X, FileText, AlertCircle, Info, Play } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface FileUploadProps {
    onFileUpload: (file: File) => void;
    onSampleData?: () => void;
    isLoading: boolean;
}

export default function FileUpload({ onFileUpload, onSampleData, isLoading }: FileUploadProps) {
    const [dragActive, setDragActive] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    const handleDrag = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const file = e.dataTransfer.files[0];
            if (file.name.endsWith('.csv')) {
                setSelectedFile(file);
                onFileUpload(file);
            }
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            setSelectedFile(file);
            onFileUpload(file);
        }
    };

    return (
        <div className="w-full max-w-2xl mx-auto">
            <div
                className={cn(
                    "relative group cursor-pointer transition-all duration-300 border-2 border-dashed rounded-2xl p-12 text-center",
                    dragActive
                        ? "border-blue-500 bg-blue-500/10 scale-[1.02]"
                        : "border-slate-700 bg-slate-900/50 hover:bg-slate-800/50 hover:border-slate-600",
                    isLoading && "opacity-50 cursor-not-allowed pointer-events-none"
                )}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
            >
                <input
                    type="file"
                    id="file-upload"
                    className="hidden"
                    accept=".csv"
                    onChange={handleChange}
                    disabled={isLoading}
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                    <div className="flex flex-col items-center">
                        <div className={cn(
                            "w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-6 transition-transform group-hover:scale-110",
                            dragActive && "bg-blue-600 animate-pulse"
                        )}>
                            <Upload className={cn("w-8 h-8 text-slate-400", dragActive && "text-white")} />
                        </div>

                        <h3 className="text-xl font-semibold text-white mb-2">
                            {selectedFile ? selectedFile.name : "Upload Research Data"}
                        </h3>
                        <p className="text-slate-400 text-sm max-w-xs transition-opacity group-hover:opacity-80">
                            Drag and drop your mission critical CSV error logs here, or click to browse.
                        </p>

                        {isLoading && (
                            <div className="mt-6 flex items-center text-blue-400">
                                <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mr-2" />
                                Processing Analysis...
                            </div>
                        )}
                    </div>

                    {onSampleData && !isLoading && (
                        <div className="mt-6 flex flex-col items-center">
                            <div className="flex items-center space-x-2 text-slate-500 text-xs mb-3">
                                <div className="h-[1px] w-8 bg-slate-800" />
                                <span>OR</span>
                                <div className="h-[1px] w-8 bg-slate-800" />
                            </div>
                            <button
                                onClick={onSampleData}
                                className="flex items-center space-x-2 px-6 py-2 rounded-xl bg-blue-600/10 border border-blue-500/20 text-blue-400 hover:bg-blue-600/20 hover:border-blue-500/40 transition-all text-sm font-semibold group"
                            >
                                <Play size={14} className="fill-blue-400 group-hover:scale-110 transition-transform" />
                                <span>Try with Sample Data</span>
                            </button>
                        </div>
                    )}
                </label>
            </div>

            <div className="mt-8 grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-start space-x-3">
                    <div className="p-2 rounded-lg bg-emerald-500/10">
                        <AlertCircle className="w-5 h-5 text-emerald-500" />
                    </div>
                    <div>
                        <h4 className="text-sm font-medium text-white mb-1">Optimized Analysis</h4>
                        <p className="text-xs text-slate-500">Automatically detects failure trends and categories.</p>
                    </div>
                </div>
                <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-start space-x-3">
                    <div className="p-2 rounded-lg bg-blue-500/10">
                        <FileText className="w-5 h-5 text-blue-500" />
                    </div>
                    <div>
                        <h4 className="text-sm font-medium text-white mb-1">Management Ready</h4>
                        <p className="text-xs text-slate-500">Generates executive summaries and KPI dashboards.</p>
                    </div>
                </div>
            </div>

            {/* CSV Format Guide */}
            <div className="mt-12 p-6 rounded-2xl bg-slate-900/20 border border-slate-800/50">
                <h4 className="text-sm font-semibold text-slate-300 mb-4 flex items-center">
                    <Info className="w-4 h-4 mr-2 text-blue-400" />
                    CSV Data Format Guide
                </h4>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-[11px] font-mono text-slate-500 border-collapse">
                        <thead>
                            <tr className="text-slate-400 border-b border-slate-800">
                                <th className="pb-2 pr-4">Timestamp / Time</th>
                                <th className="pb-2 px-4">Description</th>
                                <th className="pb-2 pl-4">Category (Optional)</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                            <tr>
                                <td className="py-2 pr-4 text-emerald-500/80">2026-01-01 10:00:00</td>
                                <td className="py-2 px-4 italic">System crash due to overflow</td>
                                <td className="py-2 pl-4">Software</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 text-emerald-500/80">14.5 (Hours)</td>
                                <td className="py-2 px-4 italic">Memory leak detected</td>
                                <td className="py-2 pl-4">Memory</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <div className="mt-4 flex space-x-4">
                    <div className="flex-1">
                        <p className="text-[10px] text-slate-500 leading-relaxed">
                            <span className="text-blue-400 font-bold uppercase mr-1">Note:</span>
                            The engine supports both ISO timestamps and relative hours since start (T=0).
                            Column order is flexible as the engine maps headers automatically.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
