/**
 * Entry point.
 *
 * Provider order matters: i18n → theme → locale → query → auth → toasts.
 * `<html lang dir>` is already Persian/RTL in `index.html` and is synchronised
 * here whenever the administrator switches language.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "@/i18n";
import "@/styles/index.css";

import App from "@/App";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { queryClient } from "@/lib/query/client";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

const container = document.getElementById("root");
if (!container) throw new Error("Root container #root was not found");

createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <LocaleProvider>
          <QueryClientProvider client={queryClient}>
            <AuthProvider>
              <ToastProvider>
                <BrowserRouter>
                  <App />
                </BrowserRouter>
              </ToastProvider>
            </AuthProvider>
          </QueryClientProvider>
        </LocaleProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
