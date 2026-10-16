import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '@/app/api/[...path]/route';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

async function forwardedFor(trustProxy: string | undefined): Promise<string | null> {
  if (trustProxy !== undefined) vi.stubEnv('TRUST_PROXY', trustProxy);
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const req = new NextRequest('http://ui.local/api/health', { headers: { 'x-forwarded-for': '6.6.6.6' } });
  const res = await GET(req);
  expect(res.status).toBe(200);
  const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
  return headers.get('x-forwarded-for');
}

describe('API proxy route X-Forwarded-For', () => {
  it('does not forward client-supplied XFF by default', async () => {
    expect(await forwardedFor(undefined)).toBeNull();
    expect(await forwardedFor('false')).toBeNull();
  });
  it('forwards the right-most XFF entry when TRUST_PROXY=true', async () => {
    expect(await forwardedFor('true')).toBe('6.6.6.6');
  });
});

describe('API proxy route body limits', () => {
  it('rejects chunked uploads without Content-Length (Next may have truncated them)', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const req = new NextRequest('http://ui.local/api/config', {
      method: 'POST',
      headers: { 'transfer-encoding': 'chunked', 'content-type': 'application/json' },
      body: '{}',
    });
    const res = await POST(req);
    expect(res.status).toBe(411);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('rejects a declared Content-Length over 1 MiB with 413', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const req = new NextRequest('http://ui.local/api/config', {
      method: 'POST',
      headers: { 'content-length': String(2 * 1024 * 1024), 'content-type': 'application/json' },
      body: '{}',
    });
    expect((await POST(req)).status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
