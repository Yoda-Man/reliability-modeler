'use client';
// Keep in sync with mcp_server/README.md

import React, { useState } from 'react';
import { Bot, Check, Copy, KeyRound, PlugZap, Terminal, Wrench } from 'lucide-react';

const SETUP = `python3 -m venv mcp_server/.venv
mcp_server/.venv/bin/pip install -r mcp_server/requirements.txt`;

const CLAUDE = `claude mcp add reliability-modeler --scope user -- \\
  <repo>/mcp_server/.venv/bin/python <repo>/mcp_server/server.py`;

const CODEX = `[mcp_servers.reliability-modeler]
command = "<repo>/mcp_server/.venv/bin/python"
args = ["<repo>/mcp_server/server.py"]`;

const JSON_CONFIG = `{
  "mcpServers": {
    "reliability-modeler": {
      "command": "<repo>/mcp_server/.venv/bin/python",
      "args": ["<repo>/mcp_server/server.py"]
    }
  }
}`;

const TOOLS: [string, string][] = [
    ['list_analyses', 'Past analysis runs, newest first: ID, date, source, total failures and duration.'],
    ['get_trends', 'Whether reliability is improving, stable or degrading across runs.'],
    ['list_sentry_projects', 'Sentry projects available in an organization.'],
    ['run_analysis', 'Pulls 1–90 days of Sentry errors and runs a fresh analysis with a chosen forecast horizon (up to ~4 min).'],
    ['graphql', 'Failure graphs, keystone categories and cascade chains (read-only).'],
];

export default function AgentsView() {
    return (
        <div className="max-w-4xl animate-in fade-in slide-in-from-bottom-4 duration-700 pb-20">
            <div className="flex items-center space-x-4 mb-8">
                <div className="w-12 h-12 rounded-2xl bg-blue-600/10 flex items-center justify-center">
                    <Bot className="text-blue-500 w-6 h-6" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Connect AI Agents</h2>
                    <p className="text-slate-400 text-sm">
                        Feed your failure data to Claude, Codex, Yodaman or any MCP client through the bundled MCP server.
                    </p>
                </div>
            </div>

            <div className="space-y-10">
                <Section icon={<Wrench className="text-emerald-500" />} title="What agents can do"
                    description="Five tools, served over stdio. Agents cannot edit your taxonomy or delete history.">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {TOOLS.map(([name, text]) => (
                            <div key={name} className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
                                <code className="text-blue-400 text-sm font-semibold">{name}</code>
                                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{text}</p>
                            </div>
                        ))}
                    </div>
                </Section>

                <Section icon={<Terminal className="text-blue-500" />} title="1. Install once"
                    description="Run from the root of your reliability-modeler checkout. Keep this stack running.">
                    <CodeBlock code={SETUP} />
                </Section>

                <Section icon={<PlugZap className="text-amber-500" />} title="2. Register with your agent"
                    description="Replace <repo> with the absolute path of your checkout.">
                    <div className="space-y-6">
                        <div>
                            <h4 className="text-sm font-semibold text-white mb-2">Claude Code</h4>
                            <CodeBlock code={CLAUDE} />
                        </div>
                        <div>
                            <h4 className="text-sm font-semibold text-white mb-2">Codex <span className="text-slate-500 font-normal">— add to ~/.codex/config.toml</span></h4>
                            <CodeBlock code={CODEX} />
                        </div>
                        <div>
                            <h4 className="text-sm font-semibold text-white mb-2">Yodaman, Claude Desktop and other MCP clients</h4>
                            <p className="text-xs text-slate-400 mb-2">Register a stdio server with this command; most clients accept this JSON.</p>
                            <CodeBlock code={JSON_CONFIG} />
                        </div>
                    </div>
                </Section>

                <Section icon={<KeyRound className="text-rose-500" />} title="3. Credentials"
                    description="No secret goes into an agent's config.">
                    <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800 space-y-3 text-sm text-slate-300 leading-relaxed">
                        <p>The server calls <code className="text-blue-400">http://localhost:3000/api</code> and reads <code className="text-blue-400">UI_USERNAME</code> / <code className="text-blue-400">UI_PASSWORD</code> from the repo&apos;s <code className="text-blue-400">.env</code>.</p>
                        <p>For another deployment set <code className="text-blue-400">RM_URL</code> plus <code className="text-blue-400">RM_USERNAME</code> / <code className="text-blue-400">RM_PASSWORD</code>, or <code className="text-blue-400">RM_API_KEY</code> to call the API directly.</p>
                        <p>Then ask your agent something like: <em>&quot;Using reliability-modeler, is our reliability improving?&quot;</em></p>
                    </div>
                </Section>
            </div>
        </div>
    );
}

function Section({ icon, title, description, children }: { icon: React.ReactNode, title: string, description: string, children: React.ReactNode }) {
    return (
        <section>
            <div className="flex items-center space-x-3 mb-4">
                {icon}
                <div>
                    <h3 className="text-lg font-semibold text-white">{title}</h3>
                    <p className="text-xs text-slate-500">{description}</p>
                </div>
            </div>
            {children}
        </section>
    );
}

function CodeBlock({ code }: { code: string }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            // Clipboard is blocked on plain-http non-localhost origins; the text stays selectable.
        }
    };
    return (
        <div className="relative group">
            <pre className="p-4 pr-12 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 overflow-x-auto"><code>{code}</code></pre>
            <button type="button" onClick={copy} aria-label="Copy to clipboard"
                className="absolute top-2 right-2 p-2 rounded-lg text-slate-500 hover:text-white hover:bg-slate-800 transition-colors">
                {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            </button>
        </div>
    );
}
