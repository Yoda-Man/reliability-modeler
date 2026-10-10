import type { HealthResponse } from './types';

export type SystemState = 'checking' | 'ok' | 'degraded' | 'error' | 'unreachable';

export interface HealthSummary {
    state: SystemState;
    label: string;
    detail?: string;
    version?: string;
}

const CHECK_LABELS: Record<string, string> = {
    output_writable: 'output not writable',
    config_readable: 'config unreadable',
    sentry_token_configured: 'Sentry token missing',
};

function failedChecks(body: Partial<HealthResponse> | null): string | undefined {
    if (!body?.checks) return undefined;
    const failed = Object.entries(body.checks)
        .filter(([, ok]) => ok === false)
        .map(([k]) => CHECK_LABELS[k] ?? k);
    return failed.length > 0 ? failed.join(', ') : undefined;
}

/**
 * Map a /api/health result to a badge state.
 * `status` is the HTTP status, or null when the request itself failed.
 * 502/504 come from the UI proxy when the API cannot be reached.
 */
export function classifyHealth(status: number | null, body: Partial<HealthResponse> | null): HealthSummary {
    if (status === null || status === 502 || status === 504) {
        return { state: 'unreachable', label: 'API unreachable' };
    }
    const detail = failedChecks(body);
    const version = body?.version;
    if (status >= 200 && status < 300 && body?.status === 'ok') {
        return { state: 'ok', label: 'Operational', version };
    }
    if (status >= 200 && status < 300 && body?.status === 'degraded') {
        return { state: 'degraded', label: 'Degraded', detail, version };
    }
    return { state: 'error', label: 'Error', detail: detail ?? `HTTP ${status}`, version };
}
