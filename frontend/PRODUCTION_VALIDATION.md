# CDSS Production Validation Report
Date: 2026-03-24
Environment: Production-Target (Pre-Deployment Hardening)
Frontend URL: `https://<static-web-app-hostname>.azurestaticapps.net`
Backend URL: `https://<api-host>.azurecontainerapps.io/api`

## Scope
This report reflects codebase hardening and build-time validation only. Azure infrastructure deployment and live browser/UAT checks remain pending.

## Build and Configuration Validation
| Check | Status | Evidence |
|---|---|---|
| Frontend build succeeds (`npm run build`) | ✅ Pass | Executed in `frontend/` on 2026-03-24 |
| No localhost references in source production paths | ✅ Pass | `rg "localhost|127.0.0.1" frontend/src` returned no matches |
| API base URL is env-driven | ✅ Pass | `src/config/runtime.ts`, `src/lib/api-client.ts`, `src/hooks/useClinicalQuery.ts` |
| MSAL configuration is env-driven | ✅ Pass | `src/lib/auth.ts` + `src/config/runtime.ts` |
| WebSocket endpoint is env-driven | ✅ Pass | `src/hooks/useStreamingSession.ts` |
| Static Web App security config exists | ✅ Pass | `frontend/staticwebapp.config.json` |

## Security Checks
- [x] `sessionStorage` used for auth token cache.
- [x] MSAL PII logging disabled.
- [x] No secrets committed to frontend env templates.
- [x] CSP/X-Frame/X-Content-Type headers defined for SWA.
- [ ] TLS/headers validated on deployed SWA endpoint (pending deploy).
- [ ] CORS validated from deployed SWA origin (pending backend + SWA live endpoints).

## End-to-End Test Matrix (Post-Deployment)
| # | Test | Status | Notes |
|---|------|--------|-------|
| 1 | Frontend loads from SWA | ☐ Pending | Requires deployed SWA hostname |
| 2 | Entra login redirect and callback | ☐ Pending | Requires SPA redirect URI registration |
| 3 | Authenticated API call to backend | ☐ Pending | Requires valid token + CORS allow-list |
| 4 | Clinical query orchestration | ☐ Pending | Requires live backend dependencies |
| 5 | Streaming response path | ☐ Pending | Requires live SSE/WebSocket path |
| 6 | Drug safety alert rendering | ☐ Pending | Requires orchestration run |
| 7 | Document ingestion flow | ☐ Pending | Requires backend infra and storage/index |
| 8 | Search and retrieval | ☐ Pending | Requires indexed data in Search/Cosmos |

## Pending Infrastructure Assumptions
1. Backend and supporting Azure services are not yet deployed/verified in this run.
2. `.env.production` placeholders will be replaced with real tenant/client/SWA host values before release build.
3. Backend CORS allow-list must include only production SWA origin in production.
4. Entra SPA app registration must include SWA redirect/logout URIs and API delegated scope grant.

## Sign-Off
- Deployer: ___
- Reviewer: ___
- Date: ___
