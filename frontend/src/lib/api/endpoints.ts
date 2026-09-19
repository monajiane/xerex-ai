/** Typed API calls. Endpoints that are not implemented yet simply do not exist here. */

import { api, downloadRequest, streamRequest } from "./client";
import type {
  AdminUser,
  HealthCheckRun,
  HealthObservation,
  ProviderHealthDetailRow,
  RoutingRule,
  RoutingRuleInput,
  RoutingSimulationRequest,
  RoutingSimulationResult,
  ApiKey,
  ApiKeyCreateInput,
  ApiKeyCreated,
  ApiKeyListParams,
  ApiKeyUpdateInput,
  ApiKeyUsage,
  AuditLogEntry,
  Credential,
  MessageResponse,
  AuthenticatedSession,
  RequestLogDetail,
  RequestLogEntry,
  RequestLogParams,
  UsageBreakdown,
  UsageDimension,
  UsageFilterParams,
  UsageInterval,
  UsageSummary,
  BootstrapStatus,
  DashboardSummary,
  Page,
  ProviderCatalog,
  ProviderCreateInput,
  ProviderDeleteImpact,
  ProviderListParams,
  ProviderTestResult,
  ProviderUpdateInput,
  Provider,
  Model,
  ModelCreateInput,
  ModelDiscoveryResult,
  ModelEndpoint,
  ModelEndpointInput,
  ModelListParams,
  ModelTestRequest,
  ModelTestResult,
  ModelWriteInput,
  ReadinessResponse,
  RoadmapResponse,
  RoutingStrategyCatalog,
  SettingsBundle,
  SettingItem,
  SystemInfo,
  UserStatus,
  AdminRole,
} from "./types";

export const authApi = {
  bootstrapStatus: () => api.get<BootstrapStatus>("/auth/bootstrap-status"),
  bootstrap: (body: { email: string; password: string; full_name?: string }) =>
    api.post<AuthenticatedSession>("/auth/bootstrap", body),
  login: (body: { email: string; password: string }) =>
    api.post<AuthenticatedSession>("/auth/login", body),
  logout: () => api.post<{ status: string }>("/auth/logout"),
  me: () => api.get<AdminUser>("/auth/me"),
};

export const systemApi = {
  health: (signal?: AbortSignal) => api.get<ReadinessResponse>("/health", signal),
  info: (signal?: AbortSignal) => api.get<SystemInfo>("/system/info", signal),
  roadmap: (signal?: AbortSignal) => api.get<RoadmapResponse>("/system/roadmap", signal),
  providerCatalog: () => api.get<ProviderCatalog>("/catalog/providers"),
  routingCatalog: () => api.get<RoutingStrategyCatalog>("/catalog/routing-strategies"),
};

export const dashboardApi = {
  summary: (signal?: AbortSignal) => api.get<DashboardSummary>("/dashboard/summary", signal),
};

export const usersApi = {
  list: (params: { page?: number; page_size?: number } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    const suffix = query.toString() ? `?${query}` : "";
    return api.get<Page<AdminUser>>(`/admin-users${suffix}`, signal);
  },
  create: (body: { email: string; password: string; full_name?: string; role: AdminRole }) =>
    api.post<AdminUser>("/admin-users", body),
  update: (id: string, body: { full_name?: string; role?: AdminRole; status?: UserStatus }) =>
    api.patch<AdminUser>(`/admin-users/${id}`, body),
};

export const auditApi = {
  list: (params: { page?: number; page_size?: number } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    query.set("page", String(params.page ?? 1));
    query.set("page_size", String(params.page_size ?? 50));
    return api.get<Page<AuditLogEntry>>(`/audit-logs?${query}`, signal);
  },
};

export const settingsApi = {
  bundle: (signal?: AbortSignal) => api.get<SettingsBundle>("/settings", signal),
  update: (key: string, value: unknown) =>
    api.put<SettingItem>(`/settings/${encodeURIComponent(key)}`, { value }),
};

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  return query.toString() ? `?${query}` : "";
}

/** Provider & credential administration (M2). */
export const providersApi = {
  list: (params: ProviderListParams = {}, signal?: AbortSignal) =>
    api.get<Page<Provider>>(`/providers${queryString({ ...params })}`, signal),
  get: (id: string, signal?: AbortSignal) => api.get<Provider>(`/providers/${id}`, signal),
  create: (body: ProviderCreateInput) => api.post<Provider>("/providers", body),
  update: (id: string, body: ProviderUpdateInput) => api.patch<Provider>(`/providers/${id}`, body),
  remove: (id: string) => api.delete<MessageResponse>(`/providers/${id}`),
  deleteImpact: (id: string, signal?: AbortSignal) =>
    api.get<ProviderDeleteImpact>(`/providers/${id}/delete-impact`, signal),
  /** Connectivity test («آزمایش اتصال»); a failure is a normal 200 result. */
  test: (id: string, credentialId?: string) =>
    api.post<ProviderTestResult>(
      `/providers/${id}/test${credentialId ? `?credential_id=${credentialId}` : ""}`,
    ),
  defaultCredential: (id: string, signal?: AbortSignal) =>
    api.get<Credential | null>(`/providers/${id}/default-credential`, signal),
  credentials: {
    list: (providerId: string, signal?: AbortSignal) =>
      api.get<Page<Credential>>(
        `/providers/${providerId}/credentials${queryString({ page_size: 100 })}`,
        signal,
      ),
    create: (providerId: string, body: { label: string; secret: string }) =>
      api.post<Credential>(`/providers/${providerId}/credentials`, body),
    update: (providerId: string, credentialId: string, body: { label?: string; status?: string }) =>
      api.patch<Credential>(`/providers/${providerId}/credentials/${credentialId}`, body),
    rotate: (providerId: string, credentialId: string, secret: string) =>
      api.post<Credential>(`/providers/${providerId}/credentials/${credentialId}/rotate`, {
        secret,
      }),
    verify: (providerId: string, credentialId: string) =>
      api.post<ProviderTestResult>(
        `/providers/${providerId}/credentials/${credentialId}/verify`,
      ),
    remove: (providerId: string, credentialId: string) =>
      api.delete<MessageResponse>(`/providers/${providerId}/credentials/${credentialId}`),
  },
};

/** Model registry, discovery and playground (M3). */
export const modelsApi = {
  list: (params: ModelListParams = {}, signal?: AbortSignal) =>
    api.get<Page<Model>>(`/models${queryString({ ...params })}`, signal),
  get: (id: string, signal?: AbortSignal) => api.get<Model>(`/models/${id}`, signal),
  create: (body: ModelCreateInput) => api.post<Model>("/models", body),
  update: (id: string, body: ModelWriteInput) => api.patch<Model>(`/models/${id}`, body),
  remove: (id: string) => api.delete<MessageResponse>(`/models/${id}`),
  /** «کشف مدل‌ها» — reconcile the provider catalogue with the registry. */
  discover: (body: { provider_id: string; overwrite_existing?: boolean }) =>
    api.post<ModelDiscoveryResult>("/models/discover", body),
  /** «آزمایش مدل» — one prompt through the real adapter. */
  test: (id: string, body: Omit<ModelTestRequest, "model_id">) =>
    api.post<ModelTestResult>(`/models/${id}/test`, { model_id: id, ...body }),
  testStream: (id: string, body: Omit<ModelTestRequest, "model_id">): Promise<Response> =>
    streamRequest(`/models/${id}/test/stream`, { model_id: id, ...body }),
  endpoints: {
    list: (modelId: string, signal?: AbortSignal) =>
      api.get<ModelEndpoint[]>(`/models/${modelId}/endpoints`, signal),
    create: (modelId: string, body: ModelEndpointInput) =>
      api.post<ModelEndpoint>(`/models/${modelId}/endpoints`, body),
    update: (modelId: string, endpointId: string, body: Partial<ModelEndpointInput>) =>
      api.patch<ModelEndpoint>(`/models/${modelId}/endpoints/${endpointId}`, body),
    remove: (modelId: string, endpointId: string) =>
      api.delete<MessageResponse>(`/models/${modelId}/endpoints/${endpointId}`),
  },
};

/** Downstream API keys («کلیدهای API») and their consumption. */
export const apiKeysApi = {
  list: (params: ApiKeyListParams = {}, signal?: AbortSignal) =>
    api.get<Page<ApiKey>>(`/api-keys${queryString({ ...params })}`, signal),
  get: (id: string, signal?: AbortSignal) => api.get<ApiKey>(`/api-keys/${id}`, signal),
  create: (body: ApiKeyCreateInput) => api.post<ApiKeyCreated>("/api-keys", body),
  update: (id: string, body: ApiKeyUpdateInput) => api.patch<ApiKey>(`/api-keys/${id}`, body),
  /** «ابطال» — stops the key working without losing its usage history. */
  revoke: (id: string) => api.post<ApiKey>(`/api-keys/${id}/revoke`),
  remove: (id: string) => api.delete<MessageResponse>(`/api-keys/${id}`),
  usage: (id: string, signal?: AbortSignal) => api.get<ApiKeyUsage>(`/api-keys/${id}/usage`, signal),
};

/** Routing rules and the dry-run simulator («مسیریابی», M5). */
export const routingApi = {
  strategies: (signal?: AbortSignal) =>
    api.get<{ items: RoutingStrategyCatalog["items"]; implemented: boolean; milestone: string }>(
      "/routing/strategies",
      signal,
    ),
  rules: {
    list: (signal?: AbortSignal) => api.get<RoutingRule[]>("/routing/rules", signal),
    create: (body: RoutingRuleInput) => api.post<RoutingRule>("/routing/rules", body),
    update: (id: string, body: Partial<RoutingRuleInput>) =>
      api.patch<RoutingRule>(`/routing/rules/${id}`, body),
    remove: (id: string) => api.delete<MessageResponse>(`/routing/rules/${id}`),
  },
  /** «شبیه‌سازی مسیریابی» — dry run, same engine as live traffic. */
  simulate: (body: RoutingSimulationRequest) =>
    api.post<RoutingSimulationResult>("/routing/simulate", body),
};

/** Upstream health observations («بررسی سلامت», M5). */
export const healthApi = {
  providers: (signal?: AbortSignal) =>
    api.get<ProviderHealthDetailRow[]>("/health/providers", signal),
  observations: (
    params: { provider_id?: string; target_type?: string; limit?: number } = {},
    signal?: AbortSignal,
  ) => api.get<HealthObservation[]>(`/health/observations${queryString({ ...params })}`, signal),
  run: (providerId?: string) =>
    api.post<HealthCheckRun>(`/health/checks${providerId ? `?provider_id=${providerId}` : ""}`),
};

/** Usage analytics, request logs and exports («مصرف» و «گزارش درخواست‌ها», M6). */
export const usageApi = {
  summary: (
    params: UsageFilterParams & { interval?: UsageInterval } = {},
    signal?: AbortSignal,
  ) => api.get<UsageSummary>(`/usage/summary${queryString({ ...params })}`, signal),
  breakdown: (params: UsageFilterParams & { dimension?: UsageDimension } = {}, signal?: AbortSignal) =>
    api.get<UsageBreakdown>(`/usage/breakdown${queryString({ ...params })}`, signal),
  requests: (params: RequestLogParams = {}, signal?: AbortSignal) =>
    api.get<Page<RequestLogEntry>>(`/usage/requests${queryString({ ...params })}`, signal),
  request: (requestId: string, signal?: AbortSignal) =>
    api.get<RequestLogDetail>(`/usage/requests/${encodeURIComponent(requestId)}`, signal),
  /** CSV is BOM-prefixed server-side; JSON keeps Persian text readable. */
  export: (format: "csv" | "json", params: UsageFilterParams = {}) =>
    downloadRequest(
      `/usage/export${queryString({ format, ...params })}`,
      `xerex-usage.${format}`,
    ),
  rebuildRollups: (day?: string) =>
    api.post<{ rows: number }>(`/usage/rollups/rebuild${day ? `?day=${day}` : ""}`),
};
