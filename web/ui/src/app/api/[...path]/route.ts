import type { NextRequest } from 'next/server';
import {
    BodyTooLargeError,
    MAX_BODY_BYTES,
    clientAddress,
    contentLengthTooLarge,
    errorResponse,
    formatLogLine,
    isAbortError,
    isAllowedMethod,
    parseTimeoutMs,
    pickResponseHeaders,
    readBodyWithLimit,
    resolveRequestId,
} from '@/lib/apiProxy';

/**
 * Server-side reverse proxy to the FastAPI backend.
 *
 * Holds RELIABILITY_API_KEY server-side (never shipped to the browser) and
 * injects it into outbound requests. The browser calls same-origin `/api/*`
 * and this route forwards to API_URL. Only GET and POST are exported, so Next
 * answers any other method with 405.
 */

export const dynamic = 'force-dynamic';

function log(level: 'error' | 'warning', fields: Parameters<typeof formatLogLine>[1]): void {
    const line = formatLogLine(level, fields);
    if (level === 'error') console.error(line);
    else console.warn(line);
}

async function proxy(req: NextRequest): Promise<Response> {
    const apiUrl = (process.env.API_URL || 'http://localhost:8000').replace(/\/+$/, '');
    const apiKey = process.env.RELIABILITY_API_KEY || '';
    const timeoutMs = parseTimeoutMs(process.env.PROXY_TIMEOUT_MS);

    const requestId = resolveRequestId(req.headers.get('x-request-id'));
    const method = req.method.toUpperCase();
    const path = req.nextUrl.pathname.replace(/^\/api/, '') || '/';

    if (!isAllowedMethod(method)) {
        return errorResponse(405, `Method ${method} not allowed`, requestId, { Allow: 'GET, POST' });
    }

    const headers = new Headers({ 'X-Request-ID': requestId });
    if (apiKey) headers.set('X-API-Key', apiKey);
    const contentType = req.headers.get('content-type');
    if (contentType) headers.set('Content-Type', contentType);
    const accept = req.headers.get('accept');
    if (accept) headers.set('Accept', accept);
    const client = clientAddress(req.headers.get('x-forwarded-for'), req.headers.get('x-real-ip'));
    if (client) headers.set('X-Forwarded-For', client);

    let body: ArrayBuffer | undefined;
    if (method === 'POST') {
        if (contentLengthTooLarge(req.headers.get('content-length'))) {
            return errorResponse(413, `Request body exceeds ${MAX_BODY_BYTES} bytes`, requestId);
        }
        try {
            body = await readBodyWithLimit(req.body);
        } catch (err) {
            if (err instanceof BodyTooLargeError) {
                return errorResponse(413, err.message, requestId);
            }
            log('error', { msg: 'Failed to read request body', request_id: requestId, method, path, error: String(err) });
            return errorResponse(400, 'Could not read request body', requestId);
        }
    }

    try {
        const upstream = await fetch(`${apiUrl}${path}${req.nextUrl.search}`, {
            method,
            headers,
            body,
            signal: AbortSignal.timeout(timeoutMs),
            redirect: 'manual',
            cache: 'no-store',
        });
        const payload = await upstream.arrayBuffer();
        const outHeaders = pickResponseHeaders(upstream.headers);
        outHeaders.set('X-Request-ID', upstream.headers.get('x-request-id') ?? requestId);
        if (upstream.status >= 500) {
            log('warning', { msg: 'Upstream API returned an error', request_id: requestId, method, path, status: upstream.status });
        }
        return new Response(payload, { status: upstream.status, headers: outHeaders });
    } catch (err) {
        const timedOut = isAbortError(err);
        const status = timedOut ? 504 : 502;
        log('error', {
            msg: timedOut ? 'Upstream API timeout' : 'Failed to reach the API',
            request_id: requestId,
            method,
            path,
            status,
            error: err instanceof Error ? `${err.name}: ${err.message}` : String(err),
        });
        return errorResponse(status, timedOut ? 'Upstream API timeout' : 'Failed to reach the API', requestId);
    }
}

export async function GET(req: NextRequest): Promise<Response> {
    return proxy(req);
}

export async function POST(req: NextRequest): Promise<Response> {
    return proxy(req);
}
