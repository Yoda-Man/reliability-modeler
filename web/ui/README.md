# Reliability Modeler UI

The Next.js 16 (App Router) front end for Reliability Modeler. It renders the
Sentry ingest form, the analysis dashboard, trends, the logs archive and the
configuration editor. It talks to the FastAPI backend (`web/api`) only through
its own server-side proxy, so the API key never reaches the browser.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `UI_PASSWORD` | none (required) | HTTP Basic auth password. If it is empty, every request except `/healthz` gets `503 {"detail":"UI_PASSWORD not configured"}`. |
| `UI_USERNAME` | `admin` | HTTP Basic auth username. |
| `UI_AUTH_DISABLED` | `false` | Set to `true` to turn auth off. Only for local development. |
| `API_URL` | `http://localhost:8000` | Base URL of the FastAPI backend (Compose sets `http://api:8000`). |
| `RELIABILITY_API_KEY` | none | Sent to the API as `X-API-Key`. Server-side only. |
| `PROXY_TIMEOUT_MS` | `130000` | Upstream timeout for proxied API calls. It sits a little above the API's 120 s analysis timeout. |
| `PORT` / `HOSTNAME` | `3000` / `0.0.0.0` | Listen address (Docker image defaults). |

All of these are read at request time on the server. None of them is `NEXT_PUBLIC_*`.

## Authentication

`src/proxy.ts` uses the Next.js 16 request-proxy file convention, which
replaces `middleware.ts`. It enforces HTTP Basic auth on every route,
including `/api/*` and static assets. `/healthz` is the only exemption. The
credential check compares SHA-256 digests in constant time. The pure logic
lives in `src/lib/basicAuth.ts`.

## API proxy (`/api/*`)

`src/app/api/[...path]/route.ts` forwards `/api/<path>?<query>` to
`${API_URL}/<path>?<query>`:

- Only `GET` and `POST` are proxied. Next answers any other method with `405`.
- Request bodies are capped at 1 MiB, checked against `Content-Length` and
  again while streaming. Oversized bodies get `413`.
- Request and response bodies are handled as raw bytes, so binary data is safe.
- `X-Request-ID` is forwarded when it is safe (`[A-Za-z0-9._-]{1,128}`) and
  generated otherwise. It is echoed on the response.
- `X-Forwarded-For` carries the client address. The proxy takes the right-most
  entry of the incoming header, or `X-Real-IP`.
- The proxy forwards these upstream response headers: `content-type`,
  `content-disposition`, `cache-control`, `retry-after`, `x-request-id`.
- When the API is unreachable the proxy returns `502`. On timeout it returns
  `504`. Both use the body `{"detail": "..."}` and are logged to stderr as a
  single JSON line (`ts`, `level`, `logger`, `msg`, `request_id`, ...).

In the browser, `src/lib/api.ts` provides `apiFetch` and `apiJson`. It parses
errors as `detail ?? error ?? fallback` and throws `ApiError(status, detail)`,
which views render with `components/ErrorState.tsx`.

The sidebar status badge polls `/api/health` every 30 s and shows one of four
states: operational, degraded, error or API unreachable.

## Development

```bash
npm ci
UI_AUTH_DISABLED=true API_URL=http://localhost:8000 RELIABILITY_API_KEY=dev-key npm run dev
```

The app runs at http://localhost:3000.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server |
| `npm run build` | Production build (`output: 'standalone'`) |
| `npm start` | Serve a production build |
| `npm run lint` | ESLint (`eslint-config-next`) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest unit and component tests (`tests/`) |

Fonts use the system font stack, so the build needs no network access to
Google Fonts.

## Docker

```bash
docker build -t reliability-modeler-ui .
docker run --rm -p 3000:3000 -e UI_PASSWORD=change-me \
  -e API_URL=http://api:8000 -e RELIABILITY_API_KEY=... reliability-modeler-ui
```

The image is based on `node:22-alpine`, pinned by digest. It runs as the
non-root `nextjs` user. Its `HEALTHCHECK` probes `http://127.0.0.1:3000/healthz`.
