/**
 * M5 module tests: routing rules, the strategy catalogue and the dry-run simulator.
 *
 * The assertions focus on what an operator must be able to trust: the strategy table
 * says which criteria each strategy uses, the simulator renders the real candidate
 * order with Persian reasons, and a provider whose health is down is visibly excluded.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { RoutingPage } from "@/features/routing/RoutingPage";
import { applyDocumentLocale } from "@/i18n";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

const OWNER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@xerex.ai",
  full_name: "مالک سامانه",
  role: "owner",
  status: "active",
  mfa_enabled: false,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const STRATEGIES = [
  {
    strategy: "priority",
    requires_priority: true,
    requires_weight: false,
    uses_health: false,
    uses_latency: false,
    uses_cost: false,
    implemented: true,
    summary: "Order candidates by provider priority, then by weight.",
    milestone: "M5",
  },
  {
    strategy: "latency_aware",
    requires_priority: false,
    requires_weight: false,
    uses_health: true,
    uses_latency: true,
    uses_cost: false,
    implemented: true,
    summary: "Prefer candidates with the lowest observed latency.",
    milestone: "M5",
  },
];

const RULE = {
  id: "77777777-7777-7777-7777-777777777777",
  name: "قاعده چت",
  strategy: "latency_aware",
  match_conditions: { model: "gpt-4o*" },
  target_model_ids: [],
  fallback_chain: [],
  enabled: true,
  priority: 10,
  created_at: "2026-02-01T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
};

const SIMULATION = {
  model: "gpt-4o-mini",
  strategy: "latency_aware",
  rule_id: RULE.id,
  rule_name: RULE.name,
  candidates: [
    {
      model_id: "33333333-3333-3333-3333-333333333333",
      model_name: "gpt-4o-mini",
      provider_id: "22222222-2222-2222-2222-222222222222",
      provider_name: "OpenAI Primary",
      credential_id: "44444444-4444-4444-4444-444444444444",
      endpoint_id: "55555555-5555-5555-5555-555555555555",
      score: 0,
      eligible: true,
      latency_ms: 180,
      price_per_1m: 0.75,
      estimated_cost: 0.00075,
      reasons: ["observed_latency_ms=180", "health=healthy"],
    },
    {
      model_id: "66666666-6666-6666-6666-666666666666",
      model_name: "gpt-4o-mini",
      provider_id: "88888888-8888-8888-8888-888888888888",
      provider_name: "Backup Provider",
      credential_id: null,
      endpoint_id: null,
      score: 0,
      eligible: false,
      latency_ms: null,
      price_per_1m: null,
      estimated_cost: null,
      reasons: ["excluded_health_down", "no_price_data"],
    },
  ],
  selected_model_id: "33333333-3333-3333-3333-333333333333",
  selected_provider_id: "22222222-2222-2222-2222-222222222222",
  explanation: ["strategy=latency_aware", "candidates=2", "eligible=1"],
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
    if (url.includes("/auth/bootstrap-status")) {
      return json({
        requires_bootstrap: false,
        bootstrap_enabled: true,
        admin_user_count: 1,
        bootstrap_allowed: false,
      });
    }
    if (url.includes("/auth/me")) return json(OWNER);
    if (url.includes("/auth/refresh")) {
      return json({
        tokens: { access_token: "t", token_type: "bearer", expires_in: 900, expires_at: "" },
      });
    }
    return undefined;
  };
}

function baseHandlers(rules = [RULE]): Handler[] {
  return [
    sessionHandler(),
    (url) => (url.includes("/routing/strategies") ? json({ items: STRATEGIES, implemented: true, milestone: "M5" }) : undefined),
    (url, init) =>
      url.includes("/routing/rules") && (!init?.method || init.method === "GET")
        ? json(rules)
        : undefined,
  ];
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
              <MemoryRouter initialEntries={["/routing"]}>
                <RoutingPage />
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

describe("routing module", () => {
  it("lists the strategies with the criteria each one uses", async () => {
    mockApi(...baseHandlers());

    renderPage();

    expect(await screen.findByRole("heading", { name: "مسیریابی هوشمند" })).toBeInTheDocument();
    // Strategy names stay technical (English) even inside the Persian UI.
    expect(await screen.findByText("latency_aware")).toBeInTheDocument();
    // …but the criteria are Persian labels.
    expect(screen.getAllByText("زمان پاسخ").length).toBeGreaterThan(0);
    expect(screen.getAllByText("سلامت").length).toBeGreaterThan(0);
    expect(screen.getByText("ترتیب ثابت")).toBeInTheDocument();
  });

  it("shows the rule with its condition and Persian state", async () => {
    mockApi(...baseHandlers());

    renderPage();

    expect(await screen.findByText("قاعده چت")).toBeInTheDocument();
    const pattern = screen.getByText("gpt-4o*");
    expect(pattern).toHaveAttribute("dir", "ltr");
    expect(screen.getByText("۱۰")).toBeInTheDocument();
  });

  it("shows the empty state when no rule exists", async () => {
    mockApi(...baseHandlers([]));

    renderPage();

    expect(await screen.findByText("هنوز قاعده‌ای ثبت نشده است")).toBeInTheDocument();
  });

  it("simulates routing and explains every candidate in Persian", async () => {
    const requests: string[] = [];
    mockApi(...baseHandlers(), (url, init) => {
      if (url.includes("/routing/simulate") && init?.method === "POST") {
        requests.push(String(init.body));
        return json(SIMULATION);
      }
      return undefined;
    });

    renderPage();
    await screen.findByText("قاعده چت");

    fireEvent.change(screen.getByLabelText("مدل"), { target: { value: "gpt-4o-mini" } });
    fireEvent.click(screen.getByRole("button", { name: "اجرای شبیه‌سازی" }));

    await waitFor(() =>
      expect(screen.getByText("OpenAI Primary")).toBeInTheDocument(),
    );
    expect(requests[0]).toContain("gpt-4o-mini");

    // Reasons: English tokens are translated, not printed raw.
    expect(screen.getByText("زمان پاسخ مشاهده‌شده: ۱۸۰ میلی‌ثانیه")).toBeInTheDocument();
    expect(screen.getByText("به دلیل قطع بودن ارائه‌دهنده کنار گذاشته شد")).toBeInTheDocument();
    expect(screen.queryByText("excluded_health_down")).not.toBeInTheDocument();

    // The excluded provider is still visible, marked as such.
    const row = screen.getByText("Backup Provider").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("کنارگذاشته‌شده")).toBeInTheDocument();

    // Decision details stay technical and LTR.
    const detail = screen.getByText("candidates=2");
    expect(detail).toHaveAttribute("dir", "ltr");
  });

  it("reports the missing model error code from the backend", async () => {
    mockApi(...baseHandlers(), (url, init) => {
      if (url.includes("/routing/simulate") && init?.method === "POST") {
        return json(
          {
            error: {
              code: "routing_simulation_model_required",
              message: "A model name is required for a simulation.",
              request_id: "r1",
            },
          },
          422,
        );
      }
      return undefined;
    });

    renderPage();
    await screen.findByText("قاعده چت");

    fireEvent.change(screen.getByLabelText("مدل"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "اجرای شبیه‌سازی" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("routing_simulation_model_required");
  });

  it("requires a Persian confirmation before deleting a rule", async () => {
    const deletes: string[] = [];
    mockApi(...baseHandlers(), (url, init) => {
      if (url.includes("/routing/rules/") && init?.method === "DELETE") {
        deletes.push(url);
        return json({ status: "deleted" });
      }
      return undefined;
    });

    renderPage();
    await screen.findByText("قاعده چت");

    fireEvent.click(screen.getByRole("button", { name: "عملیات" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "حذف" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/حذف قاعده «قاعده چت»/)).toBeInTheDocument();
    expect(deletes).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "حذف قاعده" }));
    await waitFor(() => expect(deletes).toHaveLength(1));
  });
});
