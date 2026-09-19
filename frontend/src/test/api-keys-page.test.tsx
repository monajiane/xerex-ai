/**
 * M4 module tests: the API-key page («کلیدهای API»).
 *
 * The mocked API mirrors the backend schemas. The tests assert the Persian copy, the
 * one-time secret flow, the destructive confirmation, the aggregated usage numbers and
 * that a viewer never sees a management affordance.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ApiKeysPage } from "@/features/api-keys/ApiKeysPage";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { applyDocumentLocale } from "@/i18n";
import type { AdminUser, ApiKey } from "@/lib/api/types";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

const OWNER: AdminUser = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@xerex.ai",
  full_name: "مالک سامانه",
  role: "owner" as const,
  status: "active" as const,
  mfa_enabled: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const VIEWER: AdminUser = { ...OWNER, id: "99999999-9999-9999-9999-999999999999", role: "viewer" };

const KEY: ApiKey = {
  id: "55555555-5555-5555-5555-555555555555",
  name: "سرویس پشتیبانی",
  prefix: "xrx_live_8f2a1b3c",
  masked: "xrx_live_8f2a1b3c…",
  scopes: ["chat", "models"],
  rate_limit_per_min: 120,
  quota_tokens: 500000,
  enabled: true,
  expires_at: null,
  last_used_at: "2026-02-01T10:00:00Z",
  revoked_at: null,
  created_at: "2026-01-20T08:00:00Z",
  updated_at: "2026-01-20T08:00:00Z",
};

const REVOKED_KEY: ApiKey = {
  ...KEY,
  id: "66666666-6666-6666-6666-666666666666",
  name: "کلید قدیمی",
  enabled: false,
  revoked_at: "2026-02-02T09:00:00Z",
};

type Handler = (url: string, init?: RequestInit) => Response | undefined;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(...handlers: Handler[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      for (const handler of handlers) {
        const response = handler(url, init);
        if (response) return response;
      }
      return json({ error: { code: "not_found", message: "missing" } }, 404);
    }),
  );
}

function sessionHandler(user = OWNER): Handler {
  return (url) => {
    if (url.includes("/auth/bootstrap-status")) {
      return json({
        requires_bootstrap: false,
        bootstrap_enabled: true,
        admin_user_count: 1,
        bootstrap_allowed: false,
      });
    }
    if (url.includes("/auth/me")) return json(user);
    if (url.includes("/auth/refresh")) {
      return json({
        tokens: { access_token: "t", token_type: "bearer", expires_in: 900, expires_at: "" },
      });
    }
    return undefined;
  };
}

function keysHandler(items = [KEY]): Handler {
  return (url, init) => {
    // Only the collection endpoint itself; /usage and /revoke have their own handlers.
    if (/\/api-keys(\?|$)/.test(url) && (!init?.method || init.method === "GET")) {
      return json({ items, total: items.length, page: 1, page_size: 100 });
    }
    return undefined;
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ToastProvider>
              <MemoryRouter initialEntries={["/api-keys"]}>
                <ApiKeysPage />
              </MemoryRouter>
            </ToastProvider>
          </AuthProvider>
        </QueryClientProvider>
      </LocaleProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  applyDocumentLocale("fa");
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api keys module", () => {
  it("lists keys in Persian and never shows the secret", async () => {
    mockApi(sessionHandler(), keysHandler());

    renderPage();

    expect(await screen.findByText("سرویس پشتیبانی")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "کلیدهای API" })).toBeInTheDocument();

    // The masked prefix is technical data: it must stay inside an LTR container.
    const masked = screen.getByText("xrx_live_8f2a1b3c…");
    expect(masked).toHaveAttribute("dir", "ltr");

    // Scope names are translated, not shown as raw English enums.
    const row = screen.getByText("سرویس پشتیبانی").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("گفت‌وگو")).toBeInTheDocument();
    expect(within(row!).getByText("مدل‌ها")).toBeInTheDocument();
    expect(within(row!).getByText("فعال")).toBeInTheDocument();

    // The base URL and the public routes are documented for the operator.
    const routes = screen.getAllByText(/\/v1\/chat\/completions/);
    expect(routes.length).toBeGreaterThan(0);
    expect(routes[0]).toHaveAttribute("dir", "ltr");
  });

  it("shows the empty state before the first key is issued", async () => {
    mockApi(sessionHandler(), keysHandler([]));

    renderPage();

    expect(await screen.findByText("هنوز کلید API صادر نشده است")).toBeInTheDocument();
  });

  it("reveals a newly created key exactly once, in LTR", async () => {
    mockApi(sessionHandler(), keysHandler([]), (url, init) => {
      if (url.endsWith("/api-keys") && init?.method === "POST") {
        return json({ ...KEY, secret: "xrx_live_8f2a1b3c_secretvalue" }, 201);
      }
      return undefined;
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /صدور کلید/ }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "نام" }), {
      target: { value: "سرویس گزارش‌ها" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "ذخیره تغییرات" }));

    const secretDialog = await screen.findByRole("dialog", { name: /کلید ساخته شد/ });
    const secret = within(secretDialog).getByText("xrx_live_8f2a1b3c_secretvalue");
    expect(secret).toHaveAttribute("dir", "ltr");
    expect(
      within(secretDialog).getByText(/فقط همین یک‌بار نمایش داده می‌شود/),
    ).toBeInTheDocument();
  });

  it("requires a Persian confirmation before revoking a key", async () => {
    const revocations: string[] = [];
    mockApi(sessionHandler(), keysHandler(), (url, init) => {
      if (url.includes("/revoke") && init?.method === "POST") {
        revocations.push(url);
        return json({ ...KEY, enabled: false, revoked_at: "2026-02-03T00:00:00Z" });
      }
      return undefined;
    });

    renderPage();
    await screen.findByText("سرویس پشتیبانی");

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "ابطال" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/ابطال «سرویس پشتیبانی»/)).toBeInTheDocument();
    expect(within(dialog).getByText(/تاریخ مصرف آن حفظ می‌شود/)).toBeInTheDocument();
    expect(revocations).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "ابطال کلید" }));
    await waitFor(() => expect(revocations).toHaveLength(1));
  });

  it("shows the aggregated usage of one key", async () => {
    mockApi(sessionHandler(), keysHandler(), (url) => {
      if (url.includes("/usage")) {
        return json({
          api_key_id: KEY.id,
          requests: 42,
          input_tokens: 12000,
          output_tokens: 3000,
          total_tokens: 15000,
          cost: 0.42,
          error_count: 2,
          last_used_at: "2026-02-01T10:00:00Z",
          quota_tokens: 500000,
          quota_remaining_tokens: 485000,
        });
      }
      return undefined;
    });

    renderPage();
    await screen.findByText("سرویس پشتیبانی");

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "مشاهده مصرف" }));

    const dialog = await screen.findByRole("dialog", { name: /مصرف کلید/ });
    expect(await within(dialog).findByText("۱۵۰۰۰")).toBeInTheDocument();
    expect(within(dialog).getByText("۴۲")).toBeInTheDocument();
    expect(within(dialog).getByText(/۴۸۵٬۰۰۰/)).toBeInTheDocument();
    expect(within(dialog).getByText(/دلار/)).toBeInTheDocument();
    expect(within(dialog).queryByText("0.42")).not.toBeInTheDocument();
  });

  it("hides management actions from a viewer", async () => {
    mockApi(sessionHandler(VIEWER), keysHandler());

    renderPage();

    await screen.findByText("سرویس پشتیبانی");
    expect(screen.queryByRole("button", { name: /صدور کلید/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    expect(await screen.findByRole("menuitem", { name: "مشاهده مصرف" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "ابطال" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "حذف" })).not.toBeInTheDocument();
  });

  it("marks a revoked key and keeps it in the list", async () => {
    mockApi(sessionHandler(), keysHandler([KEY, REVOKED_KEY]));

    renderPage();

    await screen.findByText("کلید قدیمی");
    const row = screen.getByText("کلید قدیمی").closest("tr");
    expect(within(row!).getByText("باطل‌شده")).toBeInTheDocument();
  });
});
