# CDSS Pre-Deployment Audit
Generated: 2026-03-24T12:10:00+05:30

## Build System
- Framework: Vite (React + TypeScript)
- Build command: `npm run build` (`tsc -b && vite build`)
- Output directory: `dist/`

## Environment Variables
| Variable | Current Source | Production Target | Status |
|----------|----------------|-------------------|--------|
| `VITE_API_BASE_URL` | `src/config/runtime.ts` + `.env.production` | Container Apps HTTPS endpoint ending in `/api` | READY (placeholder in `.env.production`) |
| `VITE_AZURE_CLIENT_ID` | `src/config/runtime.ts` + `.env.production` | Entra SPA app client ID | READY (placeholder in `.env.production`) |
| `VITE_AZURE_TENANT_ID` | `src/config/runtime.ts` + `.env.production` | Entra tenant ID | READY (placeholder in `.env.production`) |
| `VITE_AZURE_AUTHORITY` | `src/config/runtime.ts` + `.env.production` | `https://login.microsoftonline.com/<TENANT_ID>` | READY |
| `VITE_API_SCOPE` | `src/config/runtime.ts` + `.env.production` | `api://cdss-api/access_as_user` | READY |
| `VITE_REDIRECT_URI` | `src/config/runtime.ts` + `.env.production` | SWA HTTPS origin | READY (placeholder in `.env.production`) |
| `VITE_POST_LOGOUT_URI` | `src/config/runtime.ts` + `.env.production` | SWA HTTPS origin | READY (placeholder in `.env.production`) |
| `VITE_WS_ENDPOINT` | `src/config/runtime.ts` + `.env.production` | Azure Web PubSub WSS endpoint | READY (placeholder in `.env.production`) |
| `VITE_ENVIRONMENT` | `src/config/runtime.ts` + `.env.production` | `production` | READY |
| `VITE_USE_MOCK_API` | `src/config/runtime.ts` + env files | `false` in production | READY |

## MSAL Configuration
- Config file: `frontend/src/lib/auth.ts`
- Runtime env adapter: `frontend/src/config/runtime.ts`
- Redirect URIs: env-driven (`VITE_REDIRECT_URI`, `VITE_POST_LOGOUT_URI`), required in production
- Authority: env-driven (`VITE_AZURE_AUTHORITY` or tenant-derived)
- Scope: env-driven (`VITE_API_SCOPE`)
- Cache location: `sessionStorage`
- PII logging: disabled (`piiLoggingEnabled: false`)

## API / Integration Layer
- Primary API client: `frontend/src/lib/api-client.ts` (env-driven base URL + bearer token via MSAL)
- Additional hook integration: `frontend/src/hooks/useClinicalQuery.ts` now uses same base URL convention and attaches bearer tokens.
- Endpoint normalization: `/v1/*` paths under `VITE_API_BASE_URL` (no duplicate `/api/api` paths).

## WebSocket / Streaming
- File: `frontend/src/hooks/useStreamingSession.ts`
- Endpoint source: `runtimeConfig.wsEndpoint` (`VITE_WS_ENDPOINT`)
- Removed `NEXT_PUBLIC_*` fallback.

## Hardcoded Localhost References (Source)
- Result: none found in `frontend/src` (`.ts/.tsx/.css`)

## Build Verification
- `npm run build` (frontend) completed successfully on this branch.
- `dist/` generated and includes production-ready bundles.

## Blocking Issues
- None in source configuration.
- Pending infrastructure inputs before release build:
  1. Replace `.env.production` placeholders: `__SPA_CLIENT_ID__`, `__TENANT_ID__`, `__STATIC_WEB_APP_HOSTNAME__`.
  2. Provision Azure resources and Entra app registrations to match those values.
  3. Apply backend CORS allow-list for the final SWA hostname.

## Checkpoint 1 Decision
- PASS with pending infra placeholders intentionally retained.
- Codebase is now deployment-ready without localhost dependency in production paths.
