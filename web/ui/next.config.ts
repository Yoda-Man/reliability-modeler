import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  experimental: {
    // Next buffers each request body (default up to 10 MiB) before proxy.ts runs
    // Basic auth, so unauthenticated uploads could pin memory. Cap it at the API
    // route's own 1 MiB limit + 1 byte: Next truncates silently at this size, so the
    // extra byte lets route.ts still detect an oversized body and answer 413.
    proxyClientMaxBodySize: 1024 * 1024 + 1,
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ];
  },
};

export default nextConfig;
