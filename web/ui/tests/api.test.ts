import { describe, expect, it } from 'vitest';
import { ApiError, errorFromResponse, formatError, parseErrorDetail } from '@/lib/api';
import { classifyHealth } from '@/lib/health';

describe('parseErrorDetail', () => {
  it('prefers detail, then error, then fallback', () => {
    expect(parseErrorDetail({ detail: 'd', error: 'e' }, 'f')).toBe('d');
    expect(parseErrorDetail({ error: 'e' }, 'f')).toBe('e');
    expect(parseErrorDetail({}, 'f')).toBe('f');
    expect(parseErrorDetail(null, 'f')).toBe('f');
    expect(parseErrorDetail({ detail: '' }, 'f')).toBe('f');
  });
  it('flattens FastAPI validation error lists', () => {
    expect(parseErrorDetail({ detail: [{ msg: 'field required' }, { msg: 'bad type' }] }, 'f'))
      .toBe('field required; bad type');
  });
  it('uses plain-text bodies', () => {
    expect(parseErrorDetail('Bad Gateway', 'f')).toBe('Bad Gateway');
  });
});

describe('errorFromResponse / formatError', () => {
  it('builds ApiError from JSON detail', async () => {
    const err = await errorFromResponse(new Response(JSON.stringify({ detail: 'nope' }), { status: 400 }), 'Failed');
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.detail).toBe('nope');
    expect(formatError(err)).toBe('HTTP 400: nope');
  });
  it('falls back to a status message for empty bodies', async () => {
    const err = await errorFromResponse(new Response('', { status: 500 }), 'Failed');
    expect(err.detail).toBe('Failed (500)');
  });
  it('formats network errors without a status', () => {
    expect(formatError(new ApiError(0, 'network error'))).toBe('network error');
    expect(formatError(new Error('x'))).toBe('x');
  });
});

describe('classifyHealth', () => {
  it('maps API health responses to badge states', () => {
    expect(classifyHealth(200, { status: 'ok', version: '2.9.0' })).toMatchObject({ state: 'ok', version: '2.9.0' });
    expect(classifyHealth(200, {
      status: 'degraded',
      checks: { output_writable: true, config_readable: true, sentry_token_configured: false },
    })).toMatchObject({ state: 'degraded', detail: 'Sentry token missing' });
    expect(classifyHealth(503, {
      status: 'error',
      checks: { output_writable: false, config_readable: true, sentry_token_configured: true },
    })).toMatchObject({ state: 'error', detail: 'output not writable' });
    expect(classifyHealth(401, { detail: 'x' } as never)).toMatchObject({ state: 'error', detail: 'HTTP 401' });
  });
  it('treats proxy failures and network errors as unreachable', () => {
    expect(classifyHealth(502, null).state).toBe('unreachable');
    expect(classifyHealth(504, null).state).toBe('unreachable');
    expect(classifyHealth(null, null).state).toBe('unreachable');
  });
});
