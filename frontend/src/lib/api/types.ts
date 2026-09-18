/**
 * API contract types.
 *
 * These mirror the backend Pydantic schemas in `backend/app/schemas`. Field names
 * stay English (snake_case) on purpose: the Persian UI labels them through the
 * i18n layer, but the data contract never changes language (PROMPT.md 14.11).
 */

export type AdminRole = "owner" | "admin" | "operator" | "viewer";
export type UserStatus = "active" | "suspended" | "invited";
export type ProviderKind =
  | "openai"
  | "anthropic"
  | "google"
  | "deepseek"
  | "qwen"
  | "openai_compatible";
export type CredentialStatus = "unverified" | "active" | "invalid" | "revoked";
export type HealthStatusValue = "healthy" | "degraded" | "down" | "unknown";
export type OverallStatus = "healthy" | "degraded" | "down";
export type CapabilityState = "implemented" | "placeholder" | "planned";
export type RoutingStrategyValue =
  | "priority"
  | "weighted"
  | "round_robin"
  | "latency_aware"
  | "cost_aware"
  | "failover";
export type AuditActionValue =
  | "login_succeeded"
  | "login_failed"
  | "logout"
  | "token_refreshed"
  | "bootstrap_owner_created"
  | "settings_updated"
  | "user_created"
  | "user_updated"
  | "user_disabled";

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id?: string | null;
    details?: Record<string, unknown> | null;
  };
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  role: AdminRole;
  status: UserStatus;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
  expires_at: string;
}

export interface AuthenticatedSession {
  user: AdminUser;
  tokens: TokenPair;
}

export interface BootstrapStatus {
  requires_bootstrap: boolean;
  bootstrap_enabled: boolean;
  admin_user_count: number;
}

export interface ComponentHealth {
  name: string;
  status: HealthStatusValue;
  latency_ms: number | null;
  version: string | null;
  dialect: string | null;
  required: boolean | null;
  degraded_ok: boolean | null;
  error: string | null;
  detail: string | null;
}

export interface ReadinessResponse {
  status: OverallStatus;
  service: string;
  version: string;
  milestone: string;
  environment: string;
  checked_at: string;
  uptime_seconds: number;
  components: ComponentHealth[];
}

export interface MetricCard {
  key: string;
  value: number;
  unit: string | null;
  trend_percent: number | null;
  window: string;
  available: boolean;
}

export interface ProviderHealthRow {
  provider_id: string;
  name: string;
  status: string;
  latency_ms: number | null;
  error_rate: number | null;
  checked_at: string | null;
}

export interface TopModelRow {
  model_name: string;
  provider_name: string;
  requests: number;
  tokens: number;
}

export interface DashboardSummary {
  generated_at: string;
  window: string;
  metrics: MetricCard[];
  provider_health: ProviderHealthRow[];
  top_models: TopModelRow[];
  counts: Record<string, number>;
  has_provider_data: boolean;
  system_status: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: AuditActionValue;
  entity_type: string | null;
  entity_id: string | null;
  diff: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  request_id: string | null;
  created_at: string;
}

export interface SettingItem {
  key: string;
  value: unknown;
  description: string | null;
  updated_at: string | null;
  editable: boolean;
}

export interface SettingsBundle {
  items: SettingItem[];
  supported_locales: string[];
  default_locale: string;
}

export interface Capability {
  key: string;
  state: CapabilityState;
  milestone: string;
  api_prefix: string | null;
}

export interface PlannedEndpoint {
  method: string;
  path: string;
  summary: string;
  milestone: string;
  state: CapabilityState;
}

export interface RoadmapModule {
  key: string;
  milestone: string;
  state: CapabilityState;
  endpoints: PlannedEndpoint[];
}

export interface RoadmapResponse {
  current_milestone: string;
  modules: RoadmapModule[];
}

export interface LocalizationInfo {
  default_locale: string;
  supported_locales: string[];
  default_timezone: string;
}

export interface SystemInfo {
  name: string;
  version: string;
  milestone: string;
  environment: string;
  api_version: string;
  started_at: string;
  uptime_seconds: number;
  localization: LocalizationInfo;
  capabilities: Capability[];
}

export interface ProviderCatalogEntry {
  kind: ProviderKind;
  display_name: string;
  default_base_url: string;
  auth_scheme: string;
  supports_model_discovery: boolean;
  supports_streaming: boolean;
  supports_embeddings: boolean;
  implemented: boolean;
  notes: string;
  milestone: string;
}

export interface ProviderCatalog {
  items: ProviderCatalogEntry[];
  implemented: boolean;
  milestone: string;
}

export interface RoutingStrategyEntry {
  strategy: RoutingStrategyValue;
  requires_priority: boolean;
  requires_weight: boolean;
  uses_health: boolean;
  uses_latency: boolean;
  uses_cost: boolean;
  implemented: boolean;
  summary: string;
  milestone: string;
}

export interface RoutingStrategyCatalog {
  items: RoutingStrategyEntry[];
  implemented: boolean;
  milestone: string;
}
