import { NextRequest, NextResponse } from 'next/server';

/**
 * Server-side proxy to the FastAPI backend.
 *
 * Holds RELIABILITY_API_KEY server-side (never shipped to the browser) and
 * injects it into outbound requests. The client SPA calls same-origin `/api/*`
 * and this route forwards to the API at API_URL.
 */

const API_URL = process.env.API_URL || 'http://localhost:8000';
const API_KEY = process.env.RELIABILITY_API_KEY || '';
const API_TIMEOUT_MS = 130000; // slightly above the API's 120s analysis timeout

async function proxy(req: NextRequest): Promise<NextResponse> {
    // Strip the /api prefix to get the backend path
    const path = req.nextUrl.pathname.replace(/^\/api/, '');
    const target = `${API_URL}${path}${req.nextUrl.search}`;

    const headers: Record<string, string> = {};
    if (API_KEY) {
        headers['X-API-Key'] = API_KEY;
    }
    const contentType = req.headers.get('content-type');
    if (contentType) {
        headers['Content-Type'] = contentType;
    }

    let body: BodyInit | undefined;
    if (req.method !== 'GET' && req.method !== 'HEAD') {
        body = await req.text();
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

    try {
        const resp = await fetch(target, {
            method: req.method,
            headers,
            body,
            signal: controller.signal,
            // Important: do not auto-redirect; forward status codes as-is
            redirect: 'manual',
        });

        const respContentType = resp.headers.get('content-type') || 'application/json';
        const text = await resp.text();

        return new NextResponse(text, {
            status: resp.status,
            headers: {
                'Content-Type': respContentType,
            },
        });
    } catch (err: any) {
        const isTimeout = err && (err.name === 'AbortError');
        return NextResponse.json(
            { error: isTimeout ? 'Upstream API timeout' : 'Failed to reach the API' },
            { status: 502 },
        );
    } finally {
        clearTimeout(timer);
    }
}

export async function GET(req: NextRequest) {
    return proxy(req);
}

export async function POST(req: NextRequest) {
    return proxy(req);
}

export async function DELETE(req: NextRequest) {
    return proxy(req);
}
