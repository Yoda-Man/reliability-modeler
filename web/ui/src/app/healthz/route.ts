/** Liveness probe for the UI container. Exempt from Basic auth (see src/proxy.ts). */
export const dynamic = 'force-dynamic';

export function GET(): Response {
    return new Response('ok', {
        status: 200,
        headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' },
    });
}
