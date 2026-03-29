import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CssBaseline, ThemeProvider } from "@mui/material";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import ErrorBoundary from "./components/common/ErrorBoundary";
import { initializeAuth } from "./lib/auth";
import { runtimeConfig } from "./config/runtime";
import { useThemeStore } from "./stores/userStore";
import { darkTheme, injectCssCustomProperties, lightTheme } from "./theme";
// Theme is now imported from @/theme - old inline theme definitions removed

const queryClient = new QueryClient();

function ThemedApp() {
  const themeMode = useThemeStore((state) => state.theme);
  const theme = themeMode === "dark" ? darkTheme : lightTheme;

  React.useEffect(() => {
    injectCssCustomProperties(theme);
  }, [theme]);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter>
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

async function enableMocking() {
  const useMockApi = runtimeConfig.useMockApi;
  
  if (import.meta.env.DEV && useMockApi) {
    const { worker } = await import("./mocks/browser");
    return worker.start({
      onUnhandledRequest: "bypass",
    });
  }
}

initializeAuth().then(() => {
  enableMocking().then(() => {
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <ThemedApp />
      </React.StrictMode>
    );
  });
});
