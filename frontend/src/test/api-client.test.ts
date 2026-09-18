/**
 * The client turns the API's stable English error envelope into an `ApiError`.
 * Persian wording is the UI's job, so the client must never invent messages.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, tokenStore } from "@/lib/api/client";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  tokenStore.set(null);
});

describe("api client", () => {
  it("returns parsed payloads on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok" })));
    await expect(api.get<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
  });

  it("maps the error envelope to a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "invalid_credentials",
              message: "Invalid email or password.",
              request_id: "req_test",
            },
          },
          { status: 401 },
        ),
      ),
    );

    const error = await api.get("/auth/me").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("invalid_credentials");
    expect((error as ApiError).requestId).toBe("req_test");
    expect((error as ApiError).isAuthError).toBe(true);
  });

  it("reports network failures with a dedicated code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.get("/health").catch((caught: unknown) => caught);
    expect((error as ApiError).code).toBe("network_error");
    expect((error as ApiError).status).toBe(0);
  });

  it("sends the access token it holds in memory", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    tokenStore.set({
      access_token: "access-token",
      token_type: "bearer",
      expires_in: 900,
      expires_at: "2026-09-18T10:45:00Z",
    });

    await api.get("/system/info");
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer access-token");
    expect(options.credentials).toBe("include");
  });
});
