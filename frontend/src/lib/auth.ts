import { AccountInfo, Configuration, LogLevel, PublicClientApplication } from "@azure/msal-browser";
import { runtimeConfig } from "@/config/runtime";

const msalConfig: Configuration = {
  auth: {
    clientId: runtimeConfig.azureClientId,
    authority: runtimeConfig.azureAuthority,
    redirectUri: runtimeConfig.redirectUri,
    postLogoutRedirectUri: runtimeConfig.postLogoutUri,
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: runtimeConfig.environment === "production" ? LogLevel.Error : LogLevel.Verbose,
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        if (level === LogLevel.Error) {
          console.error(message);
        } else if (runtimeConfig.environment !== "production") {
          console.debug(message);
        }
      },
      piiLoggingEnabled: false, // MANDATORY for HIPAA compliance
    },
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);
const apiScopes = [runtimeConfig.apiScope];

export async function initializeAuth(): Promise<void> {
  await msalInstance.initialize();
  await msalInstance.handleRedirectPromise();

  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0) {
    msalInstance.setActiveAccount(accounts[0]);
  }
}

export async function login(): Promise<void> {
  try {
    await msalInstance.loginRedirect({
      scopes: apiScopes,
      prompt: "login",
      loginHint: undefined,
    });
  } catch (error) {
    console.error("Login failed:", error);
    throw error;
  }
}

export async function logout(): Promise<void> {
  const account = msalInstance.getActiveAccount();
  if (account) {
    await msalInstance.logoutRedirect({
      account,
      postLogoutRedirectUri: runtimeConfig.postLogoutUri,
    });
  }
}

export async function getAccessToken(): Promise<string | null> {
  const account = msalInstance.getActiveAccount();
  if (!account) {
    return null;
  }

  try {
    const response = await msalInstance.acquireTokenSilent({
      scopes: apiScopes,
      account,
    });
    return response.accessToken;
  } catch {
    try {
      const response = await msalInstance.acquireTokenPopup({
        scopes: apiScopes,
        account,
      });
      return response.accessToken;
    } catch {
      await login();
      return null;
    }
  }
}

export function getActiveAccount(): AccountInfo | null {
  return msalInstance.getActiveAccount();
}

export function isAuthenticated(): boolean {
  return msalInstance.getAllAccounts().length > 0;
}
