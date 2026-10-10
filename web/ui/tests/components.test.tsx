// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import LogsView from '@/components/LogsView';
import ConfigView from '@/components/ConfigView';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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
