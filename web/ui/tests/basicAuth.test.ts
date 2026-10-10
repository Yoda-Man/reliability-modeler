import { describe, expect, it } from 'vitest';
import { checkBasicAuth, getAuthConfig, isAuthExempt, parseBasicAuth, safeEqual } from '@/lib/basicAuth';

const b64 = (s: string) => Buffer.from(s, 'utf8').toString('base64');

describe('getAuthConfig', () => {
  it('defaults username to admin and auth enabled', () => {
    expect(getAuthConfig({})).toEqual({ username: 'admin', password: '', disabled: false });
  });
  it('reads env vars', () => {
    expect(getAuthConfig({ UI_USERNAME: 'ops', UI_PASSWORD: 'pw', UI_AUTH_DISABLED: 'TRUE' }))
      .toEqual({ username: 'ops', password: 'pw', disabled: true });
  });
  it('only treats exactly "true" as disabled', () => {
    expect(getAuthConfig({ UI_AUTH_DISABLED: '1' }).disabled).toBe(false);
  });
});

describe('parseBasicAuth', () => {
  it('parses valid header, keeping colons in the password', () => {
    expect(parseBasicAuth(`Basic ${b64('admin:a:b')}`)).toEqual({ username: 'admin', password: 'a:b' });
  });
  it('rejects missing, non-basic and malformed headers', () => {
    expect(parseBasicAuth(null)).toBeNull();
    expect(parseBasicAuth('Bearer abc')).toBeNull();
    expect(parseBasicAuth(`Basic ${b64('nocolon')}`)).toBeNull();
    expect(parseBasicAuth('Basic !!!')).toBeNull();
  });
});

describe('safeEqual', () => {
  it('compares strings of any length', () => {
    expect(safeEqual('abc', 'abc')).toBe(true);
    expect(safeEqual('abc', 'abd')).toBe(false);
    expect(safeEqual('abc', 'abcd')).toBe(false);
    expect(safeEqual('', '')).toBe(true);
  });
});

describe('checkBasicAuth', () => {
  const cfg = { username: 'admin', password: 's3cret', disabled: false };

  it('allows correct credentials', () => {
    expect(checkBasicAuth(`Basic ${b64('admin:s3cret')}`, cfg)).toEqual({ ok: true });
  });
  it('returns 401 with WWW-Authenticate for wrong or missing credentials', () => {
    for (const header of [null, `Basic ${b64('admin:nope')}`, `Basic ${b64('root:s3cret')}`]) {
      const d = checkBasicAuth(header, cfg);
      expect(d.ok).toBe(false);
      if (!d.ok) {
        expect(d.status).toBe(401);
        expect(d.headers['WWW-Authenticate']).toMatch(/^Basic realm=/);
      }
    }
  });
  it('returns 503 when UI_PASSWORD is not configured', () => {
    const d = checkBasicAuth(`Basic ${b64('admin:')}`, { ...cfg, password: '' });
    expect(d).toMatchObject({ ok: false, status: 503, detail: 'UI_PASSWORD not configured' });
  });
  it('allows everything when auth is disabled, even without a password', () => {
    expect(checkBasicAuth(null, { username: 'admin', password: '', disabled: true })).toEqual({ ok: true });
  });
});

describe('isAuthExempt', () => {
  it('exempts only /healthz', () => {
    expect(isAuthExempt('/healthz')).toBe(true);
    expect(isAuthExempt('/healthz/x')).toBe(false);
    expect(isAuthExempt('/')).toBe(false);
    expect(isAuthExempt('/api/health')).toBe(false);
  });
});
