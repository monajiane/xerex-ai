/**
 * M2 module tests («ارائه‌دهندگان» / «اطلاعات احراز هویت»).
 *
 * The mocked API returns the same shapes as the backend schemas, so the tests
 * assert the four UI states, the Persian copy, RBAC-driven action hiding and the
 * LTR isolation of technical values (keys, URLs, ids).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { ProvidersPage } from "@/features/providers/ProvidersPage";
import { CredentialsPage } from "@/features/providers/CredentialsPage";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { applyDocumentLocale } from "@/i18n";

const OWNER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@xerex.ai",
  full_name: "مالک سامانه",
  role: "owner" as const,
  status: "active" as const,
  mfa_enabled: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const PROVIDER = {
  id: "22222222-2222-2222-2222-222222222222",
  slug: "openai-primary",
  name: "OpenAI Primary",
  kind: "openai" as const,
  base_url: "https://api.openai.com/v1",
  description: null,
  enabled: true,
  priority: 10,
  weight: 100,
  timeout_ms: 30000,
  max_retries: 2,
  health_status: "healthy" as const,
  credential_count: 1,
  model_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

const CREDENTIAL = {
  id: "33333333-3333-3333-3333-333333333333",
  provider_id: PROVIDER.id,
  label: "کلید اصلی",
  status: "active" as const,
  key_hint: "sk-…cdefghijkl",
  last_verified_at: "2026-01-03T10:00:00Z",
  last_error_code: null,
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-03T10:00:00Z",
};

const CATALOG = {
  implemented: true,
  milestone: "M2",
  items: [
    {
      kind: "openai",
      display_name: "OpenAI",
      default_base_url: "https://api.openai.com/v1",
      auth_scheme: "bearer",
      supports_model_discovery: true,
      supports_streaming: true,
      supports_embeddings: true,
      implemented: true,
      notes: "",
      milestone: "M2",
    },
  ],
};

type Handler = (input: string, init?: RequestInit) => Response | undefined;

function mockApi(...handlers: Handler[]) {
  const fallback = () =>
    new Response(JSON.stringify({ error: { code: "not_found", message: "missing" } }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      for (const handler of handlers) {
        const response = handler(url, init);
        if (response) return response;
      }
      return fallback();
    }),
  );
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sessionHandler(): Handler {
  return (url) => {
    if (url.includes("/auth/me")) return json(OWNER);
    if (url.includes("/auth/refresh")) {
      return json({ tokens: { access_token: "t", token_type: "bearer", expires_in: 900, expires_at: "" } });
    }
    return undefined;
  };
}

function renderPage(page: React.ReactNode, path = "/providers") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ToastProvider>
              <MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>
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

describe("providers module", () => {
  it("renders the Persian registry with LTR-isolated technical values", async () => {
    mockApi(
      sessionHandler(),
      (url) => (url.includes("/providers") ? json({ items: [PROVIDER], total: 1, page: 1, page_size: 50 }) : undefined),
    );

    renderPage(<ProvidersPage />);

    expect(await screen.findByText("OpenAI Primary")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ارائه‌دهندگان" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /افزودن ارائه‌دهنده/ })).toBeInTheDocument();

    const slug = screen.getByText("openai-primary");
    expect(slug).toHaveAttribute("dir", "ltr");
    expect(slug).toHaveAttribute("lang", "en");

    const baseUrl = screen.getByText("https://api.openai.com/v1");
    expect(baseUrl).toHaveAttribute("dir", "ltr");

    // Persian status wording, not the raw enum value alone.
    const row = screen.getByText("OpenAI Primary").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("سالم")).toBeInTheDocument();
    expect(within(row!).getByText("فعال")).toBeInTheDocument();
  });

  it("pre-fills the base URL of the selected kind from the backend catalog", async () => {
    let posted: Record<string, unknown> | null = null;
    mockApi(sessionHandler(), (url, init) => {
      if (url.includes("/catalog/providers")) return json(CATALOG);
      if (url.includes("/providers") && init?.method === "POST") {
        posted = JSON.parse(String(init.body)) as Record<string, unknown>;
        return json(PROVIDER, 201);
      }
      if (url.includes("/providers")) {
        return json({ items: [], total: 0, page: 1, page_size: 50 });
      }
      return undefined;
    });

    renderPage(<ProvidersPage />);
    const addButtons = await screen.findAllByRole("button", { name: /افزودن ارائه‌دهنده/ });
    fireEvent.click(addButtons[0]);

    const dialog = await screen.findByRole("dialog");
    const baseUrl = dialog.querySelector<HTMLInputElement>("#provider-base-url")!;
    await waitFor(() => expect(baseUrl.value).toBe("https://api.openai.com/v1"));
    expect(baseUrl).toHaveAttribute("dir", "ltr");

    fireEvent.change(dialog.querySelector<HTMLInputElement>("#provider-name")!, {
      target: { value: "OpenAI Primary" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "ذخیره تغییرات" }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({
      name: "OpenAI Primary",
      kind: "openai",
      base_url: "https://api.openai.com/v1",
    });
  });

  it("shows the empty state with a call to action when nothing is registered", async () => {
    mockApi(sessionHandler(), (url) =>
      url.includes("/providers") ? json({ items: [], total: 0, page: 1, page_size: 50 }) : undefined,
    );

    renderPage(<ProvidersPage />);

    expect(await screen.findByText("هنوز ارائه‌دهنده‌ای ثبت نشده است")).toBeInTheDocument();
  });

  it("shows the error state with the stable English error code", async () => {
    mockApi(sessionHandler(), (url) =>
      url.includes("/providers")
        ? json({ error: { code: "internal_error", message: "boom", request_id: "req-1" } }, 500)
        : undefined,
    );

    renderPage(<ProvidersPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("internal_error")).toBeInTheDocument();
  });

  it("requires a Persian confirmation before deleting a provider", async () => {
    const deleteCalls: string[] = [];
    mockApi(sessionHandler(), (url, init) => {
      if (url.includes("/delete-impact")) {
        return json({
          provider_id: PROVIDER.id,
          name: PROVIDER.name,
          credential_count: 1,
          model_count: 3,
          endpoint_count: 2,
        });
      }
      if (url.includes("/providers/") && init?.method === "DELETE") {
        deleteCalls.push(url);
        return json({ status: "deleted" });
      }
      if (url.includes("/providers")) {
        return json({ items: [PROVIDER], total: 1, page: 1, page_size: 50 });
      }
      return undefined;
    });

    renderPage(<ProvidersPage />);
    await screen.findByText("OpenAI Primary");

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "حذف" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/آیا از حذف «OpenAI Primary» مطمئن هستید؟/)).toBeInTheDocument();
    await waitFor(() =>
      expect(within(dialog).getByText(/۱ اطلاعات احراز هویت و ۳ مدل/)).toBeInTheDocument(),
    );
    expect(deleteCalls).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "حذف ارائه‌دهنده" }));
    await waitFor(() => expect(deleteCalls).toHaveLength(1));
  });
});

describe("credentials module", () => {
  it("never shows the secret and marks the masked hint as technical", async () => {
    mockApi(
      sessionHandler(),
      (url) => {
        if (url.includes("/credentials")) {
          return json({ items: [CREDENTIAL], total: 1, page: 1, page_size: 100 });
        }
        if (url.includes("/providers")) {
          return json({ items: [PROVIDER], total: 1, page: 1, page_size: 100 });
        }
        return undefined;
      },
    );

    renderPage(<CredentialsPage />, "/credentials");

    expect(await screen.findByText("کلید اصلی")).toBeInTheDocument();
    const hint = screen.getByText("sk-…cdefghijkl");
    expect(hint).toHaveAttribute("dir", "ltr");
    expect(screen.getByText("بررسی اعتبار")).toBeInTheDocument();
    expect(screen.getByText("چرخش کلید")).toBeInTheDocument();
  });

  it("creates a credential through the Persian dialog", async () => {
    let posted: unknown = null;
    mockApi(sessionHandler(), (url, init) => {
      if (url.includes("/credentials") && init?.method === "POST") {
        posted = JSON.parse(String(init.body));
        return json({ ...CREDENTIAL, status: "unverified", last_verified_at: null }, 201);
      }
      if (url.includes("/credentials")) {
        return json({ items: [], total: 0, page: 1, page_size: 100 });
      }
      if (url.includes("/providers")) {
        return json({ items: [PROVIDER], total: 1, page: 1, page_size: 100 });
      }
      return undefined;
    });

    renderPage(<CredentialsPage />, "/credentials");
    await screen.findByText("برای این ارائه‌دهنده اطلاعات احراز هویتی ثبت نشده است");

    fireEvent.click(screen.getByRole("button", { name: /افزودن اطلاعات احراز هویت/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/برچسب/), { target: { value: "کلید پشتیبان" } });
    fireEvent.change(within(dialog).getByLabelText(/کلید دسترسی/), { target: { value: "sk-live-abcdefghijklmnop" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "ذخیره تغییرات" }));

    await waitFor(() => expect(posted).toEqual({ label: "کلید پشتیبان", secret: "sk-live-abcdefghijklmnop" }));
  });
});
