/** Typed API calls. Endpoints that are not implemented yet simply do not exist here. */

import { api } from "./client";
import type {
  AdminUser,
  AuditLogEntry,
  AuthenticatedSession,
  BootstrapStatus,
  DashboardSummary,
  Page,
  ProviderCatalog,
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
