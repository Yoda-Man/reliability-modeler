import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { checkBasicAuth, getAuthConfig, isAuthExempt } from '@/lib/basicAuth';

/**
 * Next.js 16 request proxy (the file convention formerly called `middleware.ts`).
 * Enforces HTTP Basic auth on every route except `/healthz`.
 *
 * Not to be confused with the API reverse proxy in `src/app/api/[...path]/route.ts`.
 */
export function proxy(request: NextRequest): NextResponse {
    if (isAuthExempt(request.nextUrl.pathname)) {
        return NextResponse.next();
    }
    const decision = checkBasicAuth(request.headers.get('authorization'), getAuthConfig());
    if (decision.ok) {
        return NextResponse.next();
    }
    return NextResponse.json(
        { detail: decision.detail },
        { status: decision.status, headers: { ...decision.headers, 'Cache-Control': 'no-store' } },
    );
}

export const config = {
    // Run on everything; the exemption list lives in code so it is unit-tested.
    matcher: '/:path*',
};
