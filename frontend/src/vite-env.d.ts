/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AZURE_CLIENT_ID?: string;
  readonly VITE_AZURE_TENANT_ID?: string;
  readonly VITE_AZURE_AUTHORITY?: string;
  readonly VITE_API_SCOPE?: string;
  readonly VITE_REDIRECT_URI?: string;
  readonly VITE_POST_LOGOUT_URI?: string;
  readonly VITE_WS_ENDPOINT?: string;
  readonly VITE_ENVIRONMENT?: string;
  readonly VITE_USE_MOCK_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
