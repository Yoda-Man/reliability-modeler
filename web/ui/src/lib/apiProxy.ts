/**
 * Pure helpers for the API reverse proxy (`src/app/api/[...path]/route.ts`).
 * No Next.js imports so they can be unit-tested in isolation.
 */

export const ALLOWED_METHODS: readonly string[] = ['GET', 'POST'];
export const MAX_BODY_BYTES = 1024 * 1024; // 1 MiB
export const DEFAULT_PROXY_TIMEOUT_MS = 130_000; // slightly above the API's 120s analysis timeout

/** Response headers copied from the upstream API to the browser. */
export const FORWARDED_RESPONSE_HEADERS: readonly string[] = [
    'content-type',
    'content-disposition',
    'cache-control',
    'retry-after',
];

const REQUEST_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

export function isAllowedMethod(method: string): boolean {
    return ALLOWED_METHODS.includes(method.toUpperCase());
}

/** Accept a client-supplied request id only when it is short and safe to log/echo. */
export function sanitizeRequestId(value: string | null | undefined): string | null {
    if (!value) return null;
    const trimmed = value.trim();
    return REQUEST_ID_RE.test(trimmed) ? trimmed : null;
}

export function resolveRequestId(incoming: string | null | undefined, generate: () => string = () => crypto.randomUUID()): string {
    return sanitizeRequestId(incoming) ?? generate();
}

export function parseTimeoutMs(raw: string | undefined): number {
    if (!raw) return DEFAULT_PROXY_TIMEOUT_MS;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : DEFAULT_PROXY_TIMEOUT_MS;
}

/**
 * Pick the client address to forward as X-Forwarded-For.
 * Uses the right-most entry of the incoming header (the hop closest to us),
 * falling back to X-Real-IP. Only IP-ish characters are allowed through.
 */
export function clientAddress(forwardedFor: string | null, realIp: string | null): string | null {
    const candidates = (forwardedFor ?? '').split(',').map(s => s.trim()).filter(Boolean);
    const pick = candidates.length > 0 ? candidates[candidates.length - 1] : (realIp ?? '').trim();
    if (!pick || pick.length > 64 || !/^[0-9A-Fa-f.:]+$/.test(pick)) return null;
    return pick;
}

/** True when the declared Content-Length already exceeds the limit. */
export function contentLengthTooLarge(header: string | null, limit: number = MAX_BODY_BYTES): boolean {
    if (!header) return false;
    const n = Number(header);
    return Number.isFinite(n) && n > limit;
}

export class BodyTooLargeError extends Error {
    constructor(public readonly limit: number) {
        super(`Request body exceeds ${limit} bytes`);
        this.name = 'BodyTooLargeError';
    }
}

/**
 * Read a request body stream into an ArrayBuffer, aborting as soon as more
 * than `limit` bytes have been received (guards chunked uploads that omit
 * Content-Length).
 */
export async function readBodyWithLimit(
    body: ReadableStream<Uint8Array> | null,
    limit: number = MAX_BODY_BYTES,
): Promise<ArrayBuffer | undefined> {
    if (!body) return undefined;
    const reader = body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > limit) {
            await reader.cancel().catch(() => undefined);
            throw new BodyTooLargeError(limit);
        }
        chunks.push(value);
    }
    const out = new Uint8Array(total);
    let offset = 0;
    for (const c of chunks) {
        out.set(c, offset);
        offset += c.byteLength;
    }
    return out.buffer;
}

export function pickResponseHeaders(upstream: Headers): Headers {
    const out = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
        const v = upstream.get(name);
        if (v) out.set(name, v);
    }
    return out;
}

/** Uniform error response body/shape, matching the API's `{"detail": ...}`. */
export function errorResponse(status: number, detail: string, requestId: string, extraHeaders: Record<string, string> = {}): Response {
    return new Response(JSON.stringify({ detail }), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'X-Request-ID': requestId,
            'Cache-Control': 'no-store',
            ...extraHeaders,
        },
    });
}

export interface ProxyLogFields {
    msg: string;
    request_id: string;
    method: string;
    path: string;
    status?: number;
    error?: string;
}

/** Single-line JSON log record, matching the API's log field names. */
export function formatLogLine(level: 'error' | 'warning' | 'info', fields: ProxyLogFields, now: Date = new Date()): string {
    return JSON.stringify({ ts: now.toISOString(), level, logger: 'ui.proxy', ...fields });
}

export function isAbortError(err: unknown): boolean {
    return err instanceof Error && (err.name === 'AbortError' || err.name === 'TimeoutError');
}
