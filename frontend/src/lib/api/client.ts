/**
 * HTTP client.
 *
 * Design notes:
 *  - Browser code only ever calls relative URLs (`/api/v1/...`); the dev server
 *    and the production reverse proxy forward them to the API. This keeps the
 *    sandbox preview host, cookies and CORS simple.
 *  - The backend answers with a stable English error envelope. The client turns it
 *    into an `ApiError` carrying `code`, `requestId` and `details`; the Persian
 *    message is produced by the i18n layer, never by the API.
 *  - The refresh token lives in an HttpOnly cookie, the access token in memory.
 */

import type { ErrorEnvelope, TokenPair } from "./types";

export const API_BASE_URL = "/api/v1";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly details: Record<string, unknown> | null;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    requestId?: string | null;
    details?: Record<string, unknown> | null;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId ?? null;
    this.details = params.details ?? null;
  }

  /** True for errors the UI should present as "session expired". */
  get isAuthError(): boolean {
    return (
      this.status === 401 ||
      ["authentication_required", "token_expired", "token_invalid", "token_revoked"].includes(
        this.code,
      )
    );
  }
}

type TokenListener = (tokens: TokenPair | null) => void;

class TokenStore {
  private tokens: TokenPair | null = null;
  private readonly listeners = new Set<TokenListener>();

  get(): TokenPair | null {
    return this.tokens;
  }

  set(tokens: TokenPair | null): void {
    this.tokens = tokens;
    this.listeners.forEach((listener) => listener(tokens));
  }

  subscribe(listener: TokenListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const tokenStore = new TokenStore();

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  skipAuthRetry?: boolean;
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as ErrorEnvelope;
  } catch {
    payload = null;
  }
  return new ApiError({
    code: payload?.error?.code ?? "http_error",
    message: payload?.error?.message ?? `Request failed with status ${response.status}`,
    status: response.status,
    requestId: payload?.error?.request_id ?? response.headers.get("X-Request-ID"),
    details: payload?.error?.details ?? null,
  });
}

async function refreshSession(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      tokenStore.set(null);
      return false;
    }
    const session = (await response.json()) as { tokens: TokenPair };
    tokenStore.set(session.tokens);
    return true;
  } catch {
    tokenStore.set(null);
    return false;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, skipAuthRetry = false } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const accessToken = tokenStore.get()?.access_token;
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ code: "network_error", message: "Network request failed", status: 0 });
  }

  if (response.status === 401 && !skipAuthRetry && !path.startsWith("/auth/login")) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, skipAuthRetry: true });
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Server-Sent Events request («پاسخ جریانی»).
 *
 * Streaming must not be buffered, so this cannot use the JSON helpers above: the
 * caller receives the raw `Response` and consumes the body reader. The token comes
 * from the same in-memory store, and a 401 is surfaced as an `ApiError` so the UI
 * shows the Persian "session expired" state instead of an empty answer.
 */
export async function streamRequest(path: string, body: unknown): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  };
  const accessToken = tokenStore.get()?.access_token;
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      credentials: "include",
    });
  } catch {
    throw new ApiError({ code: "network_error", message: "Network request failed", status: 0 });
  }
  if (!response.ok) throw await parseError(response);
  return response;
}

/** Reads an SSE stream and yields each decoded JSON event (skips `[DONE]`). */
export async function* readEventStream(
  response: Response,
): AsyncGenerator<Record<string, unknown>, void, void> {
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((entry) => entry.startsWith("data:"));
      if (!line) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        yield JSON.parse(payload) as Record<string, unknown>;
      } catch {
        // A partial frame is dropped rather than rendered as broken text.
      }
    }
  }
}

/**
 * Downloads a file (usage export) through the same authenticated transport as the JSON
 * helpers: a bare `<a href>` would skip the bearer token, and the panel must not put
 * tokens in URLs. The browser receives a Blob and saves it under the server-provided name.
 */
export async function downloadRequest(path: string, fallbackName: string): Promise<string> {
  const headers: Record<string, string> = { Accept: "*/*" };
  const accessToken = tokenStore.get()?.access_token;
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method: "GET", headers, credentials: "include" });
  } catch {
    throw new ApiError({ code: "network_error", message: "Network request failed", status: 0 });
  }
  if (response.status === 401) {
    const refreshed = await refreshSession();
    if (!refreshed) throw await parseError(response);
    return downloadRequest(path, fallbackName);
  }
  if (!response.ok) throw await parseError(response);

  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match?.[1] ?? fallbackName;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return filename;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  refreshSession,
};
