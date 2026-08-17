/**
 * Shared API helper — routes through the same-origin Next.js proxy,
 * which injects the API key server-side (never exposed to the browser).
 */

const API_URL = '/api';

interface FetchOptions extends RequestInit {
    timeout?: number;
}

export async function apiFetch(path: string, options: FetchOptions = {}): Promise<Response> {
    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
    };

    const controller = new AbortController();
    const timeout = options.timeout || 130000; // match the API's 120s analysis timeout
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
