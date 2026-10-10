/**
 * HTTP Basic auth helpers used by `src/proxy.ts` (Next.js 16 request proxy,
 * formerly "middleware"). Kept free of Next.js imports so they can be unit-tested.
 *
 * Env:
 *   UI_USERNAME       default "admin"
 *   UI_PASSWORD       required; when empty every request gets 503 unless
 *   UI_AUTH_DISABLED  is "true" (local development only)
 */
import { createHash, timingSafeEqual } from 'node:crypto';

export const AUTH_REALM = 'Reliability Modeler';
export const AUTH_EXEMPT_PATHS: readonly string[] = ['/healthz'];

export interface AuthConfig {
    username: string;
    password: string;
    disabled: boolean;
}

export type AuthDecision =
    | { ok: true }
    | { ok: false; status: 401 | 503; detail: string; headers: Record<string, string> };

type Env = Record<string, string | undefined>;

export function getAuthConfig(env: Env = process.env): AuthConfig {
    return {
        username: env.UI_USERNAME || 'admin',
        password: env.UI_PASSWORD ?? '',
        disabled: (env.UI_AUTH_DISABLED ?? '').trim().toLowerCase() === 'true',
    };
}

export function isAuthExempt(pathname: string): boolean {
    return AUTH_EXEMPT_PATHS.includes(pathname);
}

/** Parse an `Authorization: Basic <base64>` header. Returns null when malformed. */
export function parseBasicAuth(header: string | null | undefined): { username: string; password: string } | null {
    if (!header) return null;
    const match = /^Basic\s+([A-Za-z0-9+/=]+)\s*$/i.exec(header);
    if (!match) return null;
    let decoded: string;
    try {
        decoded = Buffer.from(match[1], 'base64').toString('utf8');
    } catch {
        return null;
    }
    const sep = decoded.indexOf(':');
    if (sep < 0) return null;
    return { username: decoded.slice(0, sep), password: decoded.slice(sep + 1) };
}

/**
 * Constant-time string comparison. Both inputs are hashed to fixed-length
 * digests first so neither content nor length leaks through timing.
 */
export function safeEqual(a: string, b: string): boolean {
    const da = createHash('sha256').update(a, 'utf8').digest();
    const db = createHash('sha256').update(b, 'utf8').digest();
    return timingSafeEqual(da, db);
}

export function checkBasicAuth(authorization: string | null | undefined, config: AuthConfig): AuthDecision {
    if (config.disabled) return { ok: true };
    if (!config.password) {
        return { ok: false, status: 503, detail: 'UI_PASSWORD not configured', headers: {} };
    }
    const creds = parseBasicAuth(authorization);
    // Always run both comparisons so timing does not reveal which part failed.
    const userOk = safeEqual(creds?.username ?? '', config.username);
    const passOk = safeEqual(creds?.password ?? '', config.password);
    if (creds && userOk && passOk) return { ok: true };
    return {
        ok: false,
        status: 401,
        detail: 'Authentication required',
        headers: { 'WWW-Authenticate': `Basic realm="${AUTH_REALM}", charset="UTF-8"` },
    };
}
