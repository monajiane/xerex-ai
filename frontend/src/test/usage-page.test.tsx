/**
 * M6 module tests: «مصرف» analytics and «گزارش درخواست‌ها».
 *
 * The mocked API mirrors the backend schemas. The assertions cover what the milestone
 * promises: Jalali date filtering that converts to the ISO contract, honest empty
 * states, Persian metric formatting next to LTR technical values, the per-attempt
 * failover story in the request detail, and the export going through the authenticated
 * transport instead of a bare link.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { RequestLogsPage } from "@/features/logs/RequestLogsPage";
import { UsagePage } from "@/features/usage/UsagePage";
import { LocaleProvider } from "@/lib/locale/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { applyDocumentLocale } from "@/i18n";
import { formatDuration, formatNumber, formatPercent } from "@/i18n/formatters";
import { formatJalali, parseJalaliInput, toGregorian, toJalali } from "@/lib/locale/jalali";

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
  capabilities: {},
  enabled: true,
  deprecated: false,
  discovered_at: "2026-01-03T00:00:00Z",
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-03T00:00:00Z",
};

const SUMMARY = {
  totals: {
    requests: 1240,
    input_tokens: 480000,
    output_tokens: 152000,
    total_tokens: 632000,
    cost: 1.23,
    p95_latency_ms: 1800,
    avg_latency_ms: 420,
    error_rate: 0.032,
    error_count: 40,
  },
  series: {
    interval: "day" as const,
    points: [
      {
        bucket: "2026-09-17T00:00:00Z",
        requests: 800,
        tokens: 400000,
        cost: 0.8,
        error_rate: 0.02,
        avg_latency_ms: 1500,
      },
      {
        bucket: "2026-09-18T00:00:00Z",
        requests: 440,
        tokens: 232000,
        cost: 0.43,
        error_rate: 0.05,
        avg_latency_ms: 1800,
      },
    ],
  },
  generated_at: "2026-09-19T08:00:00Z",
  range_start: "2026-09-13T00:00:00Z",
  range_end: "2026-09-19T23:59:59Z",
};

const BREAKDOWN = {
  dimension: "provider" as const,
  items: [
    {
      key: PROVIDER.id,
      label: "OpenAI Primary",
      requests: 900,
      input_tokens: 480000,
      output_tokens: 152000,
      total_tokens: 632000,
      cost: 1.23,
      errors: 40,
      avg_latency_ms: 420,
      error_rate: 0.032,
    },
  ],
};

const LOG_ENTRY = {
  id: "55555555-5555-5555-5555-555555555555",
  request_id: "req-9f2a41",
  api_key_name: "سرویس پشتیبانی",
  provider_name: "OpenAI Primary",
  model_name: "gpt-4o-mini",
  status_code: 200,
  error_code: null,
  latency_ms: 320,
  total_tokens: 150,
  streaming: false,
  state: "succeeded" as const,
  attempt_count: 1,
  created_at: "2026-09-19T07:30:00Z",
};

const FAILED_ENTRY = {
  ...LOG_ENTRY,
  id: "66666666-6666-6666-6666-666666666666",
  request_id: "req-77bb02",
  status_code: 502,
  error_code: "provider_unavailable",
  state: "failed" as const,
  attempt_count: 2,
  created_at: "2026-09-19T06:10:00Z",
};

const API_KEY = {
  id: "99999999-9999-9999-9999-999999999999",
  name: "سرویس پشتیبانی",
  prefix: "xrx_live_test0001",
  scopes: ["chat"],
  rate_limit_per_min: 60,
  quota_tokens: null,
  quota_used_tokens: 0,
  enabled: true,
  revoked_at: null,
  expires_at: null,
  last_used_at: "2026-09-19T07:30:00Z",
  created_at: "2026-09-01T00:00:00Z",
};

const DETAIL = {
  request: FAILED_ENTRY,
  attempts: [
    {
      id: "77777777-7777-7777-7777-777777777777",
      attempt_number: 1,
      is_final: false,
      retryable: true,
      provider_name: "OpenAI Primary",
      model_name: "gpt-4o-mini",
      credential_label: "primary",
      endpoint_path: "/chat/completions",
      status_code: 503,
      error_code: "provider_unavailable",
      latency_ms: 800,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      cost: 0,
      streaming: false,
      created_at: "2026-09-19T06:10:00Z",
    },
    {
      id: "88888888-8888-8888-8888-888888888888",
      attempt_number: 2,
      is_final: true,
      retryable: false,
      provider_name: "OpenAI Primary",
      model_name: "gpt-4o-mini",
      credential_label: "primary",
      endpoint_path: "/chat/completions",
      status_code: 503,
      error_code: "provider_unavailable",
      latency_ms: 100,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      cost: 0,
      streaming: false,
      created_at: "2026-09-19T06:10:01Z",
    },
  ],
};

type Handler = (url: string, init?: RequestInit) => Response | undefined | Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function mockApi(...handlers: Handler[]) {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const handler of handlers) {
      const response = await handler(url, init);
      if (response) return response;
    }
    return json({ error: { code: "not_found", message: "missing" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function sessionHandler(): Handler {
  return (url) => {
    if (url.includes("/auth/me")) return json(OWNER);
    if (url.includes("/auth/refresh")) {
      return json({
        tokens: { access_token: "t", token_type: "bearer", expires_in: 900, expires_at: "" },
      });
    }
    return undefined;
  };
}

function lookupsHandler(): Handler {
  return (url) => {
    if (url.includes("/providers")) {
      return json({ items: [PROVIDER], total: 1, page: 1, page_size: 100 });
    }
    if (url.includes("/models")) {
      return json({ items: [MODEL], total: 1, page: 1, page_size: 200 });
    }
    if (url.includes("/api-keys")) {
      return json({ items: [API_KEY], total: 1, page: 1, page_size: 100 });
    }
    return undefined;
  };
}

function renderPage(page: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ToastProvider>
              <MemoryRouter>{page}</MemoryRouter>
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
  vi.restoreAllMocks();
});

describe("Jalali conversion", () => {
  it("round-trips Gregorian and Jalali dates", () => {
    expect(toJalali(2024, 8, 2)).toEqual([1403, 5, 12]);
    expect(toGregorian(1403, 5, 12)).toEqual([2024, 8, 2]);
    // A leap-year boundary: 1403/12/30 exists, 1404/01/01 is the day after.
    expect(parseJalaliInput("۱۴۰۳/۱۲/۳۰")).toBe("2025-03-20");
    expect(parseJalaliInput("1404/01/01")).toBe("2025-03-21");
  });

  it("formats for display in Persian digits and validates bad input", () => {
    expect(formatJalali("2024-08-02")).toBe("۱۴۰۳/۰۵/۱۲");
    expect(parseJalaliInput("۱۲/۰۵/۱۴۰۳")).toBeNull();
    expect(parseJalaliInput("۱۴۰۳/۱۳/۰۱")).toBeNull();
  });
});

describe("usage analytics page", () => {
  it("renders Persian metrics and sends the Jalali range as ISO dates", async () => {
    let summaryUrl = "";
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/summary")) {
          summaryUrl = url;
          return json(SUMMARY);
        }
        if (url.includes("/usage/breakdown")) return json(BREAKDOWN);
        return undefined;
      },
    );

    renderPage(<UsagePage />);

    const fa = { locale: "fa" as const, numeralStyle: "persian" as const };

    expect(await screen.findByRole("heading", { name: "مصرف" })).toBeInTheDocument();
    // Human-readable totals carry Persian digits and locale grouping.
    expect(await screen.findByText(formatNumber(1240, fa))).toBeInTheDocument();
    expect(screen.getByText(formatNumber(900, fa))).toBeInTheDocument();
    // Locale-aware percent for the error rate, and a human duration for latency.
    expect(screen.getByText(formatPercent(0.032, fa))).toBeInTheDocument();
    // The average latency appears both in the metric card and the breakdown row.
    expect(screen.getAllByText(formatDuration(420, fa)).length).toBeGreaterThan(0);

    // The default window is the last seven days, converted at the edge.
    expect(summaryUrl).toContain("date_from=");
    expect(summaryUrl).toMatch(/date_from=\d{4}-\d{2}-\d{2}/);

    // Provider label is technical → LTR island (the filter <option> is not isolated).
    const labels = await screen.findAllByText("OpenAI Primary");
    expect(labels.some((element) => element.getAttribute("dir") === "ltr")).toBe(true);
  });

  it("applies a Jalali date the administrator types", async () => {
    let summaryUrl = "";
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/summary")) {
          summaryUrl = url;
          return json(SUMMARY);
        }
        if (url.includes("/usage/breakdown")) return json(BREAKDOWN);
        return undefined;
      },
    );

    renderPage(<UsagePage />);
    await screen.findByRole("heading", { name: "مصرف" });

    fireEvent.change(screen.getByLabelText("از تاریخ"), { target: { value: "۱۴۰۵/۰۱/۰۱" } });
    fireEvent.change(screen.getByLabelText("تا تاریخ"), { target: { value: "۱۴۰۵/۰۱/۱۰" } });
    fireEvent.click(screen.getByRole("button", { name: "اعمال فیلتر" }));

    await waitFor(() => expect(summaryUrl).toContain("date_from=2026-03-21"));
    expect(summaryUrl).toContain("date_to=2026-03-30");
  });

  it("rejects a malformed Jalali date instead of sending it", async () => {
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/summary")) return json(SUMMARY);
        if (url.includes("/usage/breakdown")) return json(BREAKDOWN);
        return undefined;
      },
    );

    renderPage(<UsagePage />);
    await screen.findByRole("heading", { name: "مصرف" });

    fireEvent.change(screen.getByLabelText("از تاریخ"), { target: { value: "1405/13/40" } });

    expect(
      await screen.findByText("تاریخ خورشیدی را به شکل ۱۴۰۵/۰۶/۲۸ وارد کنید."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "اعمال فیلتر" })).toBeDisabled();
  });

  it("filters by API key and passes the key id to the export", async () => {
    const urls: string[] = [];
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/summary")) {
          urls.push(url);
          return json(SUMMARY);
        }
        if (url.includes("/usage/breakdown")) return json(BREAKDOWN);
        if (url.includes("/usage/export")) {
          urls.push(url);
          return new Response("\ufeffrequest_id\n", {
            status: 200,
            headers: { "Content-Type": "text/csv" },
          });
        }
        return undefined;
      },
    );

    renderPage(<UsagePage />);
    await screen.findByRole("heading", { name: "مصرف" });
    // The key select is populated from the real key list, not a free-text id.
    const keySelect = await screen.findByLabelText("کلید API");
    await waitFor(() => expect(within(keySelect).getByText("سرویس پشتیبانی")).toBeInTheDocument());

    fireEvent.change(keySelect, { target: { value: API_KEY.id } });
    await waitFor(() =>
      expect(urls.some((url) => url.includes(`api_key_id=${API_KEY.id}`))).toBe(true),
    );

    URL.createObjectURL = vi.fn(() => "blob:xerex");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fireEvent.click(screen.getByRole("button", { name: "برون‌بری CSV" }));
    await waitFor(() =>
      expect(
        urls.some((url) => url.includes("/usage/export") && url.includes(`api_key_id=${API_KEY.id}`)),
      ).toBe(true),
    );
  });

  it("shows an honest empty state when the window has no traffic", async () => {
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/summary")) {
          return json({
            ...SUMMARY,
            totals: { ...SUMMARY.totals, requests: 0, total_tokens: 0, error_count: 0 },
            series: { interval: "day", points: [] },
          });
        }
        if (url.includes("/usage/breakdown")) return json({ dimension: "provider", items: [] });
        return undefined;
      },
    );

    renderPage(<UsagePage />);

    expect(await screen.findByText("در این بازه داده‌ای برای نمایش نیست")).toBeInTheDocument();
    expect(await screen.findByText("مصرفی برای این بازه ثبت نشده است")).toBeInTheDocument();
    expect(
      screen.queryByText(formatNumber(1240, { locale: "fa", numeralStyle: "persian" })),
    ).not.toBeInTheDocument();
  });

  it("exports CSV through the authenticated request and reports the filename", async () => {
    let exportUrl = "";
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url, init) => {
        if (url.includes("/usage/summary")) return json(SUMMARY);
        if (url.includes("/usage/breakdown")) return json(BREAKDOWN);
        if (url.includes("/usage/export")) {
          exportUrl = url;
          expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer t");
          return new Response("\ufeffrequest_id\nreq-9f2a41\n", {
            status: 200,
            headers: {
              "Content-Type": "text/csv; charset=utf-8",
              "Content-Disposition": 'attachment; filename="xerex-usage-2026-09-19.csv"',
            },
          });
        }
        return undefined;
      },
    );

    renderPage(<UsagePage />);
    await screen.findByRole("heading", { name: "مصرف" });

    // jsdom lacks these APIs; the download itself is not what this test asserts.
    URL.createObjectURL = vi.fn(() => "blob:xerex");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    fireEvent.click(screen.getByRole("button", { name: "برون‌بری CSV" }));

    await waitFor(() => expect(exportUrl).toContain("format=csv"));
    expect(click).toHaveBeenCalled();
    expect(
      await screen.findByText("فایل «xerex-usage-2026-09-19.csv» آماده شد"),
    ).toBeInTheDocument();
  });
});

describe("request logs page", () => {
  it("lists requests with Persian state badges and LTR technical values", async () => {
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/requests")) {
          return json({ items: [LOG_ENTRY, FAILED_ENTRY], total: 2, page: 1, page_size: 20 });
        }
        return undefined;
      },
    );

    renderPage(<RequestLogsPage />);

    expect(
      await screen.findByRole("heading", { name: "گزارش درخواست‌ها" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("موفق")).toBeInTheDocument();
    // «ناموفق» also labels the state filter option, so at least the badge must exist.
    expect(screen.getAllByText("ناموفق").length).toBeGreaterThan(1);

    const requestId = screen.getByText("req-9f2a41");
    expect(requestId).toHaveAttribute("dir", "ltr");
    expect(requestId).toHaveAttribute("lang", "en");

    // The failing row surfaces the stable English error code for a bug report.
    const errorCode = screen.getByText("provider_unavailable");
    expect(errorCode).toHaveAttribute("dir", "ltr");

    // Request count uses Persian digits in the header line.
    expect(screen.getByText("۲ درخواست")).toBeInTheDocument();
    // HTTP status codes stay untranslated and LTR-isolated.
    expect(screen.getByText("502")).toHaveAttribute("dir", "ltr");
  });

  it("filters by state and sends the Jalali range as ISO dates", async () => {
    const urls: string[] = [];
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/requests")) {
          urls.push(url);
          return json({ items: [FAILED_ENTRY], total: 1, page: 1, page_size: 20 });
        }
        return undefined;
      },
    );

    renderPage(<RequestLogsPage />);
    await screen.findByRole("heading", { name: "گزارش درخواست‌ها" });

    fireEvent.change(screen.getByLabelText("وضعیت"), { target: { value: "failed" } });
    fireEvent.change(screen.getByLabelText("جست‌وجو"), { target: { value: "req-77" } });
    fireEvent.change(screen.getByLabelText("از تاریخ"), { target: { value: "۱۴۰۵/۰۱/۰۱" } });
    fireEvent.change(screen.getByLabelText("تا تاریخ"), { target: { value: "۱۴۰۵/۰۱/۱۰" } });
    fireEvent.click(screen.getByRole("button", { name: "اعمال فیلتر" }));

    await waitFor(() => expect(urls.some((url) => url.includes("state=failed"))).toBe(true));
    const applied = urls[urls.length - 1];
    expect(applied).toContain("search=req-77");
    expect(applied).toContain("date_from=2026-03-21");
    expect(applied).toContain("date_to=2026-03-30");
  });

  it("shows the attempts of a failed request in the detail dialog", async () => {
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) => {
        if (url.includes("/usage/requests/req-77bb02")) return json(DETAIL);
        if (url.includes("/usage/requests")) {
          return json({ items: [FAILED_ENTRY], total: 1, page: 1, page_size: 20 });
        }
        return undefined;
      },
    );

    renderPage(<RequestLogsPage />);
    await screen.findByText("req-77bb02");

    fireEvent.click(screen.getByRole("button", { name: "جزئیات" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("تلاش ۱")).toBeInTheDocument();
    expect(within(dialog).getByText("تلاش ۲")).toBeInTheDocument();
    expect(within(dialog).getByText("تلاش پایانی")).toBeInTheDocument();
    expect(within(dialog).getByText("قابل تلاش مجدد")).toBeInTheDocument();
    // Endpoint paths stay technical and LTR even inside the Persian dialog.
    const paths = within(dialog).getAllByText("/chat/completions");
    expect(paths[0]).toHaveAttribute("dir", "ltr");
    // Provider/model names remain untranslated inside LTR islands.
    expect(within(dialog).getAllByText("gpt-4o-mini")[0]).toHaveAttribute("dir", "ltr");

    // The raw payload is a strict LTR JSON viewer with copy-to-clipboard.
    const raw = within(dialog).getByText(/"attempt_number": 1/);
    expect(raw).toHaveAttribute("dir", "ltr");
    expect(raw.closest("pre")).toHaveAttribute("lang", "en");
    expect(within(dialog).getByRole("button", { name: "رونوشت JSON" })).toBeInTheDocument();
  });

  it("shows the empty state when no request matches", async () => {
    mockApi(
      sessionHandler(),
      lookupsHandler(),
      (url) =>
        url.includes("/usage/requests")
          ? json({ items: [], total: 0, page: 1, page_size: 20 })
          : undefined,
    );

    renderPage(<RequestLogsPage />);

    expect(await screen.findByText("درخواستی با این فیلترها پیدا نشد")).toBeInTheDocument();
  });
});
