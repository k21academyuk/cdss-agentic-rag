type AppEnvironment = "development" | "production" | "test";

function readEnv(key: keyof ImportMetaEnv): string {
  const raw = import.meta.env[key];
  if (raw === undefined || raw === null) {
    return "";
  }
  return String(raw).trim();
}

function ensureHttpsUrl(value: string, key: string): string {
  if (!/^https:\/\//i.test(value)) {
    throw new Error(`${key} must be an absolute HTTPS URL.`);
  }
  return value.replace(/\/+$/, "");
}

function ensureWssUrl(value: string, key: string): string {
  if (!/^wss:\/\//i.test(value)) {
    throw new Error(`${key} must be an absolute WSS URL.`);
  }
  return value.replace(/\/+$/, "");
}

const environment = (readEnv("VITE_ENVIRONMENT") ||
  (import.meta.env.PROD ? "production" : "development")) as AppEnvironment;

const apiBaseFromEnv = readEnv("VITE_API_BASE_URL") || "/api";
const apiBaseUrl =
  environment === "production"
    ? ensureHttpsUrl(apiBaseFromEnv, "VITE_API_BASE_URL")
    : apiBaseFromEnv.replace(/\/+$/, "");

const azureTenantId = readEnv("VITE_AZURE_TENANT_ID");
const azureClientId = readEnv("VITE_AZURE_CLIENT_ID");
const apiScope = readEnv("VITE_API_SCOPE") || "api://cdss-api/access_as_user";
const azureAuthority =
  readEnv("VITE_AZURE_AUTHORITY") ||
  (azureTenantId ? `https://login.microsoftonline.com/${azureTenantId}` : "https://login.microsoftonline.com/common");

const redirectFromEnv = readEnv("VITE_REDIRECT_URI");
const postLogoutFromEnv = readEnv("VITE_POST_LOGOUT_URI");
const redirectUri =
  environment === "production"
    ? ensureHttpsUrl(redirectFromEnv, "VITE_REDIRECT_URI")
    : redirectFromEnv || window.location.origin;
const postLogoutUri =
  environment === "production"
    ? ensureHttpsUrl(postLogoutFromEnv, "VITE_POST_LOGOUT_URI")
    : postLogoutFromEnv || window.location.origin;

const wsFromEnv = readEnv("VITE_WS_ENDPOINT");
const wsEndpoint =
  wsFromEnv && environment === "production"
    ? ensureWssUrl(wsFromEnv, "VITE_WS_ENDPOINT")
    : wsFromEnv;

if (environment === "production") {
  if (!azureClientId) {
    throw new Error("VITE_AZURE_CLIENT_ID is required in production.");
  }
  if (!azureTenantId) {
    throw new Error("VITE_AZURE_TENANT_ID is required in production.");
  }
  if (!wsEndpoint) {
    throw new Error("VITE_WS_ENDPOINT is required in production.");
  }
  if (!redirectFromEnv) {
    throw new Error("VITE_REDIRECT_URI is required in production.");
  }
  if (!postLogoutFromEnv) {
    throw new Error("VITE_POST_LOGOUT_URI is required in production.");
  }
}

export const runtimeConfig = {
  environment,
  apiBaseUrl,
  azureClientId,
  azureTenantId,
  azureAuthority,
  apiScope,
  redirectUri,
  postLogoutUri,
  wsEndpoint,
  useMockApi: readEnv("VITE_USE_MOCK_API") === "true",
} as const;
