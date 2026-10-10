/**
 * Browser-side API helpers. All calls go through the same-origin Next.js proxy
 * (`/api/*`), which injects the API key server-side.
 */

export const API_BASE = '/api';
export const DEFAULT_CLIENT_TIMEOUT_MS = 130_000;

export interface FetchOptions extends RequestInit {
    timeout?: number;
}

/** Error raised for non-OK responses (status > 0) or network failures (status 0). */
export class ApiError extends Error {
    constructor(public readonly status: number, public readonly detail: string) {
        super(detail);
        this.name = 'ApiError';
    }
}

function stringifyDetail(value: unknown): string | null {
    if (value === null || value === undefined) return null;
    if (typeof value === 'string') return value || null;
    // FastAPI validation errors: [{loc, msg, type}, ...]
    if (Array.isArray(value)) {
        const msgs = value
            .map(v => (v && typeof v === 'object' && 'msg' in v ? String((v as { msg: unknown }).msg) : JSON.stringify(v)))
            .filter(Boolean);
        return msgs.length > 0 ? msgs.join('; ') : null;
    }
    return JSON.stringify(value);
}

/** Extract a human-readable message: `body.detail ?? body.error ?? fallback`. */
export function parseErrorDetail(body: unknown, fallback: string): string {
    if (body && typeof body === 'object') {
        const b = body as { detail?: unknown; error?: unknown };
        return stringifyDetail(b.detail) ?? stringifyDetail(b.error) ?? fallback;
    }
    if (typeof body === 'string' && body.trim()) return body.trim().slice(0, 500);
    return fallback;
}

/** Build an ApiError from a non-OK Response. Never throws. */
export async function errorFromResponse(response: Response, fallback: string): Promise<ApiError> {
    let body: unknown = null;
    try {
        const text = await response.text();
        try {
            body = JSON.parse(text);
        } catch {
            body = text;
        }
    } catch {
        /* body unreadable */
    }
    const statusFallback = `${fallback} (${response.status}${response.statusText ? ' ' + response.statusText : ''})`;
    return new ApiError(response.status, parseErrorDetail(body, statusFallback));
}

/** Format any thrown value for display, including the HTTP status when known. */
export function formatError(err: unknown): string {
    if (err instanceof ApiError) {
        return err.status > 0 ? `HTTP ${err.status}: ${err.detail}` : err.detail;
    }
    if (err instanceof Error) return err.message;
    return String(err);
}

export async function apiFetch(path: string, options: FetchOptions = {}): Promise<Response> {
    const { timeout = DEFAULT_CLIENT_TIMEOUT_MS, signal, ...init } = options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const onAbort = () => controller.abort();
    signal?.addEventListener('abort', onAbort);
    try {
        return await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);
    }
}

/**
 * Fetch JSON, throwing ApiError on non-OK status or network failure.
 * `fallback` is used as the message when the error body carries none.
 */
export async function apiJson<T>(path: string, options: FetchOptions = {}, fallback = 'Request failed'): Promise<T> {
    let response: Response;
    try {
        response = await apiFetch(path, options);
    } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
            throw new ApiError(0, `${fallback}: request timed out or was cancelled`);
        }
        throw new ApiError(0, `${fallback}: network error`);
    }
    if (!response.ok) {
        throw await errorFromResponse(response, fallback);
    }
    return (await response.json()) as T;
}
