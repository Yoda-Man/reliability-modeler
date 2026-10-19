// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import LogsView from '@/components/LogsView';
import ConfigView from '@/components/ConfigView';
import AgentsView from '@/components/AgentsView';
import Dashboard from '@/components/Dashboard';
import SentryView from '@/components/SentryView';
import TrendsView from '@/components/TrendsView';
import FailureNetworkGraph, { layoutNetwork } from '@/components/FailureNetworkGraph';
import type { AnalysisResults, CategorizedFailure, GraphReport, TrendRun } from '@/lib/types';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('LogsView', () => {
  it('shows an error state with status and detail on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Failed to reach the API' }, 502)));
    render(<LogsView />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('HTTP 502');
    expect(alert.textContent).toContain('Failed to reach the API');
    expect(screen.queryByText('No Analysis History Found')).toBeNull();
  });

  it('shows the empty state (not an error) when there are no logs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ total: 0, logs: [] })));
    render(<LogsView />);
    expect(await screen.findByText('No Analysis History Found')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('ConfigView', () => {
  it('shows save failures inline using the API detail', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return jsonResponse({ detail: 'Invalid taxonomy format' }, 400);
      return jsonResponse({ content: 'Net [timeout]', settings: { multi_label: false, optimization_method: 'TNC', tolerance: 1e-6 } });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ConfigView />);
    fireEvent.click(await screen.findByText('Save Changes'));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('HTTP 400: Invalid taxonomy format');

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      content: 'Net [timeout]',
      settings: { multi_label: false, optimization_method: 'TNC', tolerance: 1e-6 },
    });
  });
});

describe('AgentsView', () => {
  it('shows every client setup and copies a command', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    render(<AgentsView />);
    expect(screen.getByText('Claude Code')).toBeTruthy();
    expect(screen.getByText(/Yodaman, Claude Desktop/)).toBeTruthy();
    expect(screen.getByText(/mcp_servers\.reliability-modeler/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy to clipboard' })[1]);
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('claude mcp add reliability-modeler'));
  });
});

describe('LogsView search', () => {
  it('says "No matches on this page" instead of the empty-history state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      total: 1,
      logs: [{ id: 'AN-1', date: '2026-01-01', file: 'sentry:org/web', status: 'Completed', summary: { total_failures: 3, duration_hours: 1 } }],
    })));
    render(<LogsView />);
    await screen.findByText('sentry:org/web');
    fireEvent.change(screen.getByPlaceholderText('Search this page...'), { target: { value: 'nope' } });
    expect(screen.getByText('No matches on this page')).toBeTruthy();
    expect(screen.queryByText('No Analysis History Found')).toBeNull();
  });
});

function failures(n: number): CategorizedFailure[] {
  return Array.from({ length: n }, (_, i) => [
    new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString(), i, 'Network', `event-${i}`,
  ] as CategorizedFailure);
}

function results(overrides: Partial<AnalysisResults> = {}): AnalysisResults {
  return {
    id: 'AN-20260101-000000-abcdef',
    summary: { total_failures: 500, duration_hours: 100, start_time: '2026-01-01T00:00:00Z' },
    models: [{ id: 'go', name: 'Goel-Okumoto', aic: 10, total_expected_failures: 520, parameters: {} }],
    plots: {},
    categorized_failures: failures(100),
    categorized_total: 500,
    future_hours: 1500,
    truncated: false,
    ...overrides,
  };
}

describe('Dashboard', () => {
  it('renders without crashing when no model could be fitted', () => {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver);
    render(<Dashboard data={results({ models: [] })} />);
    expect(screen.getByRole('status').textContent).toContain('No model could be fitted to this data');
    expect(screen.getByText('Total Failures')).toBeTruthy();
    expect(screen.getByText('500')).toBeTruthy();
  });

  it('lists recent events newest first, captions truncated samples and shows the run horizon', () => {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver);
    render(<Dashboard data={results({ truncated: true })} />);
    const events = screen.getAllByText(/^event-\d+$/).map(el => el.textContent);
    expect(events.length).toBe(50);
    expect(events[0]).toBe('event-99');
    expect(events[49]).toBe('event-50');
    expect(screen.getAllByText('(most recent 100 of 500 events)').length).toBeGreaterThan(0);
    expect(screen.getByRole('note').textContent).toContain("hit Sentry's event cap");
    expect(screen.getByText(/Projected 1500h into the future/)).toBeTruthy();
    expect(screen.queryByRole('slider')).toBeNull();
  });
});

describe('SentryView', () => {
  it('lets the days field be cleared and sends the horizon with the request', async () => {
    const onAnalyze = vi.fn(async () => undefined);
    render(<SentryView onAnalyze={onAnalyze} isLoading={false} />);
    fireEvent.change(screen.getByPlaceholderText('e.g. my-company'), { target: { value: 'acme' } });
    fireEvent.change(screen.getByPlaceholderText('e.g. web-app'), { target: { value: 'web' } });
    const days = screen.getByLabelText(/Look-back Window/) as HTMLInputElement;
    fireEvent.change(days, { target: { value: '' } });
    expect(days.value).toBe('');
    fireEvent.click(screen.getByText('Pull & Analyze'));
    expect((await screen.findByRole('alert')).textContent).toContain('Days must be');
    expect(onAnalyze).not.toHaveBeenCalled();

    fireEvent.change(days, { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText(/Forecast Horizon/), { target: { value: '2500' } });
    fireEvent.click(screen.getByText('Pull & Analyze'));
    await vi.waitFor(() => expect(onAnalyze).toHaveBeenCalledWith('acme', 'web', 7, 2500));
  });
});

describe('TrendsView', () => {
  const run = (id: string, file: string, mtbf: number): TrendRun => ({
    id, date: `2026-01-0${id.slice(-1)} 00:00`, file, total_failures: 10, duration_hours: 10, mtbf_hours: mtbf, failure_rate_per_hour: 1 / mtbf,
  });

  it('shows the trend per source when the response has groups', async () => {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver);
    const a = [run('r1', 'sentry:org/a', 1), run('r2', 'sentry:org/a', 2)];
    const b = [run('r3', 'sentry:org/b', 4), run('r4', 'sentry:org/b', 2)];
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      runs: [...a, ...b], trend: 'degrading', mtbf_change_pct: -50, rate_change_pct: 100, num_runs: 2,
      groups: [
        { file: 'sentry:org/a', runs: a, trend: 'improving', mtbf_change_pct: 100, rate_change_pct: -50, num_runs: 2 },
        { file: 'sentry:org/b', runs: b, trend: 'degrading', mtbf_change_pct: -50, rate_change_pct: 100, num_runs: 2 },
      ],
    })));
    render(<TrendsView />);
    expect(await screen.findByText(/MTBF Degrading/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'sentry:org/a' } });
    expect(screen.getByText(/MTBF Improving/)).toBeTruthy();
  });

  it('still works when groups is absent', async () => {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      runs: [run('r1', 'x', 1), run('r2', 'x', 2)], trend: 'improving', mtbf_change_pct: 100, num_runs: 2,
    })));
    render(<TrendsView />);
    expect(await screen.findByText(/MTBF Improving/)).toBeTruthy();
    expect(screen.queryByLabelText('Source')).toBeNull();
  });
});

const network: GraphReport = {
  keystone_categories: [{ name: 'Database', pagerank: 0.5, is_bridge: true }],
  top_cascade: { chain: 'Database → Network', confidence: 0.6 },
  num_communities: 2,
  graph_density: 0.5,
  graph_json: {
    nodes: [
      { id: 'Database', pagerank: 0.5, degree: 9, community: 0 },
      { id: 'Network', pagerank: 0.3, degree: 6, community: 0 },
      { id: 'Memory', pagerank: 0.2, degree: 3, community: 1 },
    ],
    edges: [{ source: 'Database', target: 'Network', weight: 5, jaccard: 0.4 }],
    cascade_edges: [
      { source: 'Database', target: 'Network', weight: 4, confidence: 0.6, avg_latency: 0.5 },
      { source: 'Memory', target: 'Database', weight: 1, confidence: 0.2, avg_latency: 1.5 },
    ],
  },
};

describe('FailureNetworkGraph', () => {
  it('lays nodes out inside the canvas, grouped by community, biggest PageRank largest', () => {
    const pos = layoutNetwork(network.graph_json!, 560);
    expect(pos.map(p => p.id)).toEqual(['Database', 'Network', 'Memory']);
    for (const p of pos) {
      expect(p.x - p.r).toBeGreaterThanOrEqual(0);
      expect(p.x + p.r).toBeLessThanOrEqual(560);
      expect(p.y - p.r).toBeGreaterThanOrEqual(0);
      expect(p.y + p.r).toBeLessThanOrEqual(560);
    }
    expect(pos[0].r).toBeGreaterThan(pos[2].r);
  });

  it('shows the cascades of a clicked category, and the Dashboard renders the card', () => {
    vi.stubGlobal('ResizeObserver', NoopResizeObserver);
    render(<FailureNetworkGraph graphReport={network} palette={['#3b82f6', '#10b981']} />);
    fireEvent.click(screen.getByRole('button', { name: /^Database, PageRank 0\.500, keystone, bridge$/ }));
    expect(screen.getByText('Triggers')).toBeTruthy();
    expect(screen.getByText('Triggered by')).toBeTruthy();
    expect(screen.getByText('60% · 0.5h')).toBeTruthy();
    cleanup();
    render(<Dashboard data={results({ graph_report: network })} />);
    expect(screen.getByRole('img', { name: 'Failure network of 3 categories' })).toBeTruthy();
  });
});
