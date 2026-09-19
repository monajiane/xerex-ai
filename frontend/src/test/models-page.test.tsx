/**
 * M3 module tests: model registry, discovery dialog and the playground.
 *
 * The mocked API mirrors the backend schemas, so the tests assert Persian copy,
 * capability badges, the real counters reported by discovery, and that the
 * playground renders the answer with token counts instead of a fake success.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { ModelDetailPage } from "@/features/models/ModelDetailPage";
import { ModelsPage } from "@/features/models/ModelsPage";
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
  model_count: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

const MODEL = {
  id: "33333333-3333-3333-3333-333333333333",
  provider_id: PROVIDER.id,
  name: "gpt-4o-mini",
  display_name: "GPT-4o mini",
  context_window: 128000,
  max_output_tokens: 16384,
  input_price_per_1m: 0.15,
  output_price_per_1m: 0.6,
  capabilities: { vision: true, tools: true, audio: false },
  enabled: true,
  deprecated: false,
  discovered_at: "2026-01-03T00:00:00Z",
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-03T00:00:00Z",
};

const ENDPOINT = {
  id: "44444444-4444-4444-4444-444444444444",
  model_id: MODEL.id,
  provider_id: PROVIDER.id,
  credential_id: null,
  path: "/chat/completions",
  method: "POST",
  streaming_supported: true,
  param_map: null,
  enabled: true,
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
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

function sessionHandler(): Handler {
  return (url) => {
    if (url.includes("/auth/me")) return json(OWNER);
    if (url.includes("/auth/refresh")) {
      return json({ tokens: { access_token: "t", token_type: "bearer", expires_in: 900, expires_at: "" } });
    }
    return undefined;
  };
}

function providersHandler(): Handler {
  return (url) =>
    url.includes("/providers") ? json({ items: [PROVIDER], total: 1, page: 1, page_size: 100 }) : undefined;
}

function renderPage(page: React.ReactNode, path = "/models") {
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

describe("models module", () => {
  it("renders the registry in Persian with capability badges and pricing", async () => {
    mockApi(
      sessionHandler(),
      providersHandler(),
      (url) => (url.includes("/models") ? json({ items: [MODEL], total: 1, page: 1, page_size: 100 }) : undefined),
    );

    renderPage(<ModelsPage />);

    expect(await screen.findByText("GPT-4o mini")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "مدل‌ها" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /کشف مدل‌ها/ }).length).toBeGreaterThan(0);

    // Capability keys stay technical and LTR-isolated.
    const vision = screen.getByText("vision");
    expect(vision).toHaveAttribute("dir", "ltr");
    expect(screen.queryByText("audio")).not.toBeInTheDocument(); // false flags are not badges

    // Persian provider name instead of the raw id.
    const row = screen.getByText("GPT-4o mini").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("OpenAI Primary")).toBeInTheDocument();
    expect(within(row!).getByText("۱۲۸۰۰۰")).toBeInTheDocument();
  });

  it("shows the empty state with a discovery call to action", async () => {
    mockApi(
      sessionHandler(),
      providersHandler(),
      (url) => (url.includes("/models") ? json({ items: [], total: 0, page: 1, page_size: 100 }) : undefined),
    );

    renderPage(<ModelsPage />);

    expect(await screen.findByText("هنوز مدلی ثبت نشده است")).toBeInTheDocument();
  });

  it("reports the real discovery counters", async () => {
    mockApi(sessionHandler(), providersHandler(), (url, init) => {
      if (url.includes("/models/discover")) {
        expect(init?.method).toBe("POST");
        return json({
          provider_id: PROVIDER.id,
          provider_name: PROVIDER.name,
          discovered: 12,
          created: 9,
          updated: 2,
          skipped: 1,
          failed: 0,
          models: [],
        });
      }
      if (url.includes("/models")) return json({ items: [], total: 0, page: 1, page_size: 100 });
      return undefined;
    });

    renderPage(<ModelsPage />);
    const discoveryButtons = await screen.findAllByRole("button", { name: /کشف مدل‌ها/ });
    fireEvent.click(discoveryButtons[0]);

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /شروع کشف/ }));

    await waitFor(() => expect(within(dialog).getByText("نتیجه کشف مدل‌ها")).toBeInTheDocument());
    expect(within(dialog).getByText("۹")).toBeInTheDocument();
    expect(within(dialog).getByText("۲")).toBeInTheDocument();
  });

  it("requires a Persian confirmation before deleting a model", async () => {
    const deletes: string[] = [];
    mockApi(sessionHandler(), providersHandler(), (url, init) => {
      if (url.includes("/models/") && init?.method === "DELETE") {
        deletes.push(url);
        return json({ status: "deleted" });
      }
      if (url.includes("/models")) return json({ items: [MODEL], total: 1, page: 1, page_size: 100 });
      return undefined;
    });

    renderPage(<ModelsPage />);
    await screen.findByText("GPT-4o mini");

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "حذف" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/حذف مدل «GPT-4o mini»/)).toBeInTheDocument();
    expect(deletes).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "حذف مدل" }));
    await waitFor(() => expect(deletes).toHaveLength(1));
  });
});

describe("model playground", () => {
  function renderDetail() {
    mockApi(sessionHandler(), providersHandler(), (url, init) => {
      if (url.includes("/test")) {
        expect(init?.method).toBe("POST");
        return json({
          model_id: MODEL.id,
          provider_id: PROVIDER.id,
          latency_ms: 812,
          input_tokens: 12,
          output_tokens: 34,
          output_text: "پاسخ آزمایشی مدل",
          finish_reason: "stop",
          error_code: null,
        });
      }
      if (url.includes("/endpoints")) return json([ENDPOINT]);
      if (url.match(/\/models\/[0-9a-f-]+$/)) return json(MODEL);
      if (url.includes("/models")) return json({ items: [MODEL], total: 1, page: 1, page_size: 100 });
      return undefined;
    });

    return renderPage(
      <Routes>
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
      </Routes>,
      `/models/${MODEL.id}`,
    );
  }

  it("sends a prompt and shows the answer with real token counts", async () => {
    renderDetail();

    expect(await screen.findByRole("heading", { name: "GPT-4o mini" })).toBeInTheDocument();
    const path = await screen.findByText("/chat/completions");
    expect(path).toHaveAttribute("dir", "ltr");

    fireEvent.change(screen.getByLabelText(/متن درخواست/), {
      target: { value: "سلام، خودت را معرفی کن" },
    });
    // Streaming is on by default: switch it off so the JSON path is exercised.
    fireEvent.click(screen.getByRole("switch", { name: /پاسخ جریانی/ }));
    fireEvent.click(screen.getByRole("button", { name: /ارسال درخواست/ }));

    expect(await screen.findByText("پاسخ آزمایشی مدل")).toBeInTheDocument();
    expect(screen.getByText("۱۲")).toBeInTheDocument(); // input tokens in Persian digits
    expect(screen.getByText("۳۴")).toBeInTheDocument();
  });

  it("shows the upstream error code instead of an empty answer", async () => {
    mockApi(sessionHandler(), providersHandler(), (url) => {
      if (url.includes("/test")) {
        return json({
          model_id: MODEL.id,
          provider_id: PROVIDER.id,
          latency_ms: 250,
          input_tokens: 0,
          output_tokens: 0,
          output_text: "",
          finish_reason: null,
          error_code: "provider_rate_limited",
        });
      }
      if (url.includes("/endpoints")) return json([ENDPOINT]);
      if (url.match(/\/models\/[0-9a-f-]+$/)) return json(MODEL);
      if (url.includes("/models")) return json({ items: [MODEL], total: 1, page: 1, page_size: 100 });
      return undefined;
    });

    renderPage(
      <Routes>
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
      </Routes>,
      `/models/${MODEL.id}`,
    );

    await screen.findByRole("heading", { name: "GPT-4o mini" });
    fireEvent.change(screen.getByLabelText(/متن درخواست/), { target: { value: "سلام" } });
    fireEvent.click(screen.getByRole("switch", { name: /پاسخ جریانی/ }));
    fireEvent.click(screen.getByRole("button", { name: /ارسال درخواست/ }));

    const code = await screen.findByText("provider_rate_limited");
    expect(code).toHaveAttribute("dir", "ltr");
  });
});
