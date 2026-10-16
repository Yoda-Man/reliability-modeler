import { describe, expect, it } from 'vitest';
import {
  BodyTooLargeError,
  DEFAULT_PROXY_TIMEOUT_MS,
  clientAddress,
  contentLengthTooLarge,
  errorResponse,
  formatLogLine,
  isAllowedMethod,
  parseTimeoutMs,
  parseTrustProxy,
  pickResponseHeaders,
  readBodyWithLimit,
  resolveRequestId,
  sanitizeRequestId,
} from '@/lib/apiProxy';

function streamOf(...chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(c);
      controller.close();
    },
  });
}

describe('request id', () => {
  it('accepts safe ids and trims whitespace', () => {
    expect(sanitizeRequestId('abc-123_X.y')).toBe('abc-123_X.y');
    expect(sanitizeRequestId('  abc  ')).toBe('abc');
  });
  it('rejects unsafe or oversized ids', () => {
    expect(sanitizeRequestId(null)).toBeNull();
    expect(sanitizeRequestId('')).toBeNull();
    expect(sanitizeRequestId('bad id')).toBeNull();
    expect(sanitizeRequestId('a\r\nInjected: 1')).toBeNull();
    expect(sanitizeRequestId('x'.repeat(129))).toBeNull();
  });
  it('generates a new id when the incoming one is invalid', () => {
    expect(resolveRequestId('ok-1', () => 'gen')).toBe('ok-1');
    expect(resolveRequestId('<script>', () => 'gen')).toBe('gen');
    expect(resolveRequestId(null)).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe('method allowlist', () => {
  it('allows only GET and POST', () => {
    expect(isAllowedMethod('GET')).toBe(true);
    expect(isAllowedMethod('post')).toBe(true);
    for (const m of ['DELETE', 'PUT', 'PATCH', 'OPTIONS', 'HEAD']) expect(isAllowedMethod(m)).toBe(false);
  });
});

describe('timeout', () => {
  it('parses PROXY_TIMEOUT_MS with a safe default', () => {
    expect(parseTimeoutMs(undefined)).toBe(DEFAULT_PROXY_TIMEOUT_MS);
    expect(DEFAULT_PROXY_TIMEOUT_MS).toBe(250000);
    expect(parseTimeoutMs('5000')).toBe(5000);
    expect(parseTimeoutMs('-1')).toBe(DEFAULT_PROXY_TIMEOUT_MS);
    expect(parseTimeoutMs('abc')).toBe(DEFAULT_PROXY_TIMEOUT_MS);
  });
});

describe('body limit', () => {
  it('flags declared content-length over 1 MiB', () => {
    expect(contentLengthTooLarge(null)).toBe(false);
    expect(contentLengthTooLarge('1048576')).toBe(false);
    expect(contentLengthTooLarge('1048577')).toBe(true);
  });
  it('reads bodies under the limit byte-for-byte (binary safe)', async () => {
    const bytes = new Uint8Array([0, 255, 128, 10, 13]);
    const buf = await readBodyWithLimit(streamOf(bytes.slice(0, 2), bytes.slice(2)), 10);
    expect(new Uint8Array(buf!)).toEqual(bytes);
  });
  it('returns undefined for no body', async () => {
    expect(await readBodyWithLimit(null)).toBeUndefined();
  });
  it('throws BodyTooLargeError once the streamed size exceeds the limit', async () => {
    await expect(readBodyWithLimit(streamOf(new Uint8Array(6), new Uint8Array(6)), 10))
      .rejects.toBeInstanceOf(BodyTooLargeError);
  });
});

describe('X-Forwarded-For', () => {
  it('ignores client-supplied forwarding headers unless the proxy is trusted', () => {
    expect(clientAddress('6.6.6.6', null)).toBeNull();
    expect(clientAddress(null, '6.6.6.6')).toBeNull();
    expect(clientAddress('6.6.6.6', '7.7.7.7', false)).toBeNull();
  });
  it('with a trusted proxy uses the right-most forwarded address, else x-real-ip', () => {
    expect(clientAddress('1.1.1.1, 10.0.0.2', null, true)).toBe('10.0.0.2');
    expect(clientAddress(null, '192.168.1.5', true)).toBe('192.168.1.5');
    expect(clientAddress(null, null, true)).toBeNull();
    expect(clientAddress('::ffff:172.18.0.1', null, true)).toBe('::ffff:172.18.0.1');
  });
  it('drops values that are not IP addresses', () => {
    expect(clientAddress('evil\r\nX: y', null, true)).toBeNull();
    expect(clientAddress('example.com', null, true)).toBeNull();
  });
  it('parses TRUST_PROXY strictly (only "true" enables it)', () => {
    expect(parseTrustProxy(undefined)).toBe(false);
    expect(parseTrustProxy('')).toBe(false);
    expect(parseTrustProxy('1')).toBe(false);
    expect(parseTrustProxy('false')).toBe(false);
    expect(parseTrustProxy('true')).toBe(true);
    expect(parseTrustProxy(' TRUE ')).toBe(true);
  });
});

describe('error shape', () => {
  it('returns {"detail"} JSON with request id', async () => {
    const res = errorResponse(502, 'Failed to reach the API', 'rid-1');
    expect(res.status).toBe(502);
    expect(res.headers.get('content-type')).toBe('application/json');
    expect(res.headers.get('x-request-id')).toBe('rid-1');
    expect(await res.json()).toEqual({ detail: 'Failed to reach the API' });
  });
  it('formats single-line JSON log records', () => {
    const line = formatLogLine('error', { msg: 'boom', request_id: 'r', method: 'GET', path: '/x' }, new Date(0));
    expect(line).not.toContain('\n');
    expect(JSON.parse(line)).toEqual({
      ts: '1970-01-01T00:00:00.000Z', level: 'error', logger: 'ui.proxy', msg: 'boom', request_id: 'r', method: 'GET', path: '/x',
    });
  });
});

describe('response headers', () => {
  it('forwards only the allowlisted headers', () => {
    const out = pickResponseHeaders(new Headers({
      'content-type': 'image/png',
      'content-disposition': 'attachment; filename="r.html"',
      'cache-control': 'no-store',
      'set-cookie': 'x=1',
      server: 'uvicorn',
    }));
    expect(out.get('content-type')).toBe('image/png');
    expect(out.get('content-disposition')).toContain('attachment');
    expect(out.get('cache-control')).toBe('no-store');
    expect(out.get('set-cookie')).toBeNull();
    expect(out.get('server')).toBeNull();
  });
});
