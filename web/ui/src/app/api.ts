/**
 * Shared API helper — includes X-API-Key header when configured.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

interface FetchOptions extends RequestInit {
    timeout?: number;
}

export async function apiFetch(path: string, options: FetchOptions = {}): Promise<Response> {
    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
    };
    if (API_KEY) {
        headers['X-API-Key'] = API_KEY;
    }

    const controller = new AbortController();
    const timeout = options.timeout || 30000;
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(`${API_URL}${path}`, {
            ...options,
            headers,
            signal: controller.signal,
        });
        return response;
    } finally {
        clearTimeout(timer);
    }
}

export { API_URL };
