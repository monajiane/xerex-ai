/**
 * Whole-app smoke test in Persian.
 *
 * It renders the real provider stack (i18n → theme → locale → query → auth →
 * toasts) against a mocked API and asserts that an administrator sees Persian copy
 * on an RTL page — including the first-run setup screen and the sign-in screen.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import App from "@/App";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { applyDocumentLocale } from "@/i18n";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ToastProvider>
              <MemoryRouter initialEntries={["/"]}>
                <App />
              </MemoryRouter>
            </ToastProvider>
          </AuthProvider>
        </QueryClientProvider>
      </LocaleProvider>
    </ThemeProvider>,
  );
}

function mockApi(handlers: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      for (const [path, body] of Object.entries(handlers)) {
        if (url.includes(path)) {
          return new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      return new Response(JSON.stringify({ error: { code: "not_found", message: "missing" } }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  applyDocumentLocale("fa");
});

describe("admin panel smoke test", () => {
  it("shows the Persian sign-in screen when the platform is already initialised", async () => {
    mockApi({
      "/auth/bootstrap-status": {
        requires_bootstrap: false,
        bootstrap_enabled: true,
        admin_user_count: 1,
      },
    });

    renderApp();

    expect(await screen.findByText("ورود به پنل مدیریت")).toBeInTheDocument();
    expect(screen.getByLabelText(/ایمیل/)).toBeInTheDocument();
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("fa");
  });

  it("shows the Persian first-run screen while no administrator exists", async () => {
    mockApi({
      "/auth/bootstrap-status": {
        requires_bootstrap: true,
        bootstrap_enabled: true,
        admin_user_count: 0,
      },
    });

    renderApp();

    expect(await screen.findByText("راه‌اندازی اولیه")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ساخت حساب مدیر/ })).toBeInTheDocument();
  });

  it("renders the Persian dashboard shell for an authenticated owner", async () => {
    mockApi({
      "/auth/bootstrap-status": {
        requires_bootstrap: false,
        bootstrap_enabled: true,
        admin_user_count: 1,
      },
      "/auth/refresh": {
        user: {
          id: "user-1",
          email: "admin@xerex.ai",
          full_name: "مدیر سیستم",
          role: "owner",
          status: "active",
          mfa_enabled: false,
          last_login_at: "2026-09-18T09:00:00Z",
          created_at: "2026-09-18T08:00:00Z",
        },
        tokens: {
          access_token: "test-token",
          token_type: "bearer",
          expires_in: 900,
          expires_at: "2026-09-18T10:15:00Z",
        },
      },
      "/auth/me": {
        id: "user-1",
        email: "admin@xerex.ai",
        full_name: "مدیر سیستم",
        role: "owner",
        status: "active",
        mfa_enabled: false,
        last_login_at: "2026-09-18T09:00:00Z",
        created_at: "2026-09-18T08:00:00Z",
      },
      "/system/info": {
        name: "Xerex AI",
        version: "0.1.0",
        milestone: "M1",
        environment: "test",
        api_version: "v1",
        started_at: "2026-09-18T10:00:00Z",
        uptime_seconds: 60,
        localization: {
          default_locale: "fa",
          supported_locales: ["fa", "en"],
          default_timezone: "Asia/Tehran",
        },
        capabilities: [
          { key: "dashboard", state: "implemented", milestone: "M1", api_prefix: "/api/v1" },
          { key: "providers", state: "planned", milestone: "M2", api_prefix: "/api/v1" },
        ],
      },
      "/dashboard/summary": {
        generated_at: "2026-09-18T10:00:00Z",
        window: "24h",
        metrics: [
          { key: "requests", value: 0, unit: "requests", trend_percent: null, window: "24h", available: true },
          { key: "tokens", value: 0, unit: "tokens", trend_percent: null, window: "24h", available: true },
          { key: "cost", value: 0, unit: "currency", trend_percent: null, window: "24h", available: true },
          { key: "p95_latency_ms", value: 0, unit: "ms", trend_percent: null, window: "24h", available: false },
          { key: "error_rate", value: 0, unit: "ratio", trend_percent: null, window: "24h", available: false },
          { key: "active_providers", value: 0, unit: "providers", trend_percent: null, window: "now", available: true },
        ],
        provider_health: [],
        top_models: [],
        counts: { providers: 0, models: 0, api_keys: 0, admin_users: 1 },
        has_provider_data: false,
        system_status: "healthy",
      },
      "/system/roadmap": { current_milestone: "M1", modules: [] },
    });

    renderApp();

    // Session restore runs through the refresh cookie, then `GET /auth/me`.
    await waitFor(() => expect(screen.getByRole("link", { name: /داشبورد/ })).toBeInTheDocument());
    expect(screen.getAllByText("ارائه‌دهندگان").length).toBeGreaterThan(0);
    expect(screen.getByText("کلیدهای API")).toBeInTheDocument();
  });
});
