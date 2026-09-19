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
export type HealthStatusValue =
  | "healthy"
  | "degraded"
  | "rate_limited"
  | "down"
  | "unknown";
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
  /** No owner account exists yet. */
  requires_bootstrap: boolean;
  /** Effective XEREX_BOOTSTRAP_ENABLED value for this deployment. */
  bootstrap_enabled: boolean;
  admin_user_count: number;
  /** requires_bootstrap && bootstrap_enabled — what the panel acts on. */
  bootstrap_allowed: boolean;
  /** Feature milestone the backend is running (shown on pre-auth screens). */
  milestone?: string;
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

export interface RoutingCatalogItem {
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
  items: RoutingCatalogItem[];
  implemented: boolean;
  milestone: string;
}

/* -------------------------------------------------------------------------- */
/* M2 — providers, credentials                                                */
/* -------------------------------------------------------------------------- */

export interface MessageResponse {
  status: string;
}

export interface Provider {
  id: string;
  slug: string;
  name: string;
  kind: ProviderKind;
  base_url: string;
  description: string | null;
  enabled: boolean;
  priority: number;
  weight: number;
  timeout_ms: number;
  max_retries: number;
  health_status: HealthStatusValue;
  credential_count: number;
  model_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProviderCreateInput {
  name: string;
  kind: ProviderKind;
  base_url: string;
  slug?: string | null;
  description?: string | null;
  enabled?: boolean;
  priority?: number;
  weight?: number;
  timeout_ms?: number;
  max_retries?: number;
}

export type ProviderUpdateInput = Partial<Omit<ProviderCreateInput, "kind" | "slug">>;

export interface ProviderListParams {
  page?: number;
  page_size?: number;
  search?: string;
  kind?: ProviderKind;
  enabled?: boolean;
  order_by?: string;
}

export interface Credential {
  id: string;
  provider_id: string;
  label: string;
  status: CredentialStatus;
  /** Masked display hint — the API never returns the secret itself. */
  key_hint: string;
  last_verified_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
}

/** Outcome of «آزمایش اتصال» / credential verification. */
export interface ProviderTestResult {
  provider_id: string;
  credential_id: string | null;
  ok: boolean;
  latency_ms: number;
  status_code: number | null;
  error_code: string | null;
  detail: string | null;
  model_count: number | null;
}

export interface ProviderDeleteImpact {
  provider_id: string;
  name: string;
  credential_count: number;
  model_count: number;
  endpoint_count: number;
}

/* -------------------------------------------------------------------------- */
/* M3 — models, discovery, playground                                         */
/* -------------------------------------------------------------------------- */

export interface Model {
  id: string;
  provider_id: string;
  name: string;
  display_name: string | null;
  context_window: number | null;
  max_output_tokens: number | null;
  input_price_per_1m: number | null;
  output_price_per_1m: number | null;
  capabilities: Record<string, unknown> | null;
  enabled: boolean;
  deprecated: boolean;
  discovered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelWriteInput {
  display_name?: string | null;
  context_window?: number | null;
  max_output_tokens?: number | null;
  input_price_per_1m?: number | null;
  output_price_per_1m?: number | null;
  capabilities?: Record<string, unknown> | null;
  enabled?: boolean;
  deprecated?: boolean;
}

export interface ModelCreateInput extends ModelWriteInput {
  provider_id: string;
  name: string;
}

export interface ModelListParams {
  page?: number;
  page_size?: number;
  search?: string;
  provider_id?: string;
  enabled?: boolean;
  deprecated?: boolean;
  order_by?: string;
}

export interface ModelDiscoveryResult {
  provider_id: string;
  provider_name: string;
  discovered: number;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  models: Model[];
}

export interface ModelTestRequest {
  model_id: string;
  prompt: string;
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
}

export interface ModelTestResult {
  model_id: string;
  provider_id: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  output_text: string;
  finish_reason: string | null;
  /** `null` means the call succeeded; otherwise a stable upstream error code. */
  error_code: string | null;
}

export interface ModelEndpoint {
  id: string;
  model_id: string;
  provider_id: string | null;
  credential_id: string | null;
  path: string;
  method: string;
  streaming_supported: boolean;
  param_map: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelEndpointInput {
  path: string;
  method?: string;
  streaming_supported?: boolean;
  enabled?: boolean;
  credential_id?: string | null;
}

/* -------------------------------------------------------------------------- */
/* M4 — downstream API keys and the gateway                                   */
/* -------------------------------------------------------------------------- */

export type ApiKeyScope = "chat" | "embeddings" | "models";

export interface ApiKey {
  id: string;
  name: string;
  /** Display prefix, e.g. `xrx_live_8f2a`. */
  prefix: string;
  /** Masked display form, e.g. `xrx_live_8f2a…`. */
  masked: string;
  scopes: string[];
  rate_limit_per_min: number;
  quota_tokens: number | null;
  enabled: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Returned exactly once by the create call; the secret is never retrievable again. */
export interface ApiKeyCreated extends ApiKey {
  secret: string;
}

export interface ApiKeyCreateInput {
  name: string;
  scopes?: string[];
  rate_limit_per_min?: number;
  quota_tokens?: number | null;
  expires_at?: string | null;
}

export interface ApiKeyUpdateInput {
  name?: string;
  scopes?: string[];
  rate_limit_per_min?: number;
  quota_tokens?: number | null;
  enabled?: boolean;
  expires_at?: string | null;
}

export interface ApiKeyUsage {
  api_key_id: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  error_count: number;
  last_used_at: string | null;
  quota_tokens: number | null;
  quota_remaining_tokens: number | null;
}

export interface ApiKeyListParams {
  page?: number;
  page_size?: number;
  search?: string;
  enabled?: boolean;
  include_revoked?: boolean;
}

/* -------------------------------------------------------------------------- */
/* M5 — routing rules, simulation and upstream health                          */
/* -------------------------------------------------------------------------- */

export interface RoutingRule {
  id: string;
  name: string;
  strategy: RoutingStrategyValue;
  match_conditions: Record<string, unknown> | null;
  target_model_ids: string[];
  fallback_chain: string[];
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface RoutingRuleInput {
  name: string;
  strategy?: RoutingStrategyValue;
  match_conditions?: Record<string, unknown> | null;
  target_model_ids?: string[];
  fallback_chain?: string[];
  enabled?: boolean;
  priority?: number;
}

export interface RoutingSimulationRequest {
  model: string;
  strategy?: RoutingStrategyValue;
  requested_tokens?: number;
}

export interface RoutingCandidate {
  model_id: string | null;
  model_name: string | null;
  provider_id: string | null;
  provider_name: string | null;
  credential_id: string | null;
  endpoint_id: string | null;
  score: number;
  eligible: boolean;
  latency_ms: number | null;
  price_per_1m: number | null;
  estimated_cost: number | null;
  /** Stable English tokens (`provider_priority=1`, `excluded_health_down`). */
  reasons: string[];
}

export interface RoutingSimulationResult {
  model: string;
  strategy: RoutingStrategyValue;
  rule_id: string | null;
  rule_name: string | null;
  candidates: RoutingCandidate[];
  selected_model_id: string | null;
  selected_provider_id: string | null;
  explanation: string[];
}

/** M5 shape of one provider's observed health (the dashboard has its own summary row). */
export interface ProviderHealthDetailRow {
  provider_id: string;
  name: string;
  slug: string;
  enabled: boolean;
  status: HealthStatusValue;
  last_checked_at: string | null;
  latency_ms: number | null;
  error_code: string | null;
  requests: number;
  errors: number;
  error_rate: number;
  avg_latency_ms: number | null;
  uptime_percent: number | null;
  credential_count: number;
  model_count: number;
}

export interface HealthObservation {
  id: string;
  target_type: string;
  target_id: string;
  provider_id: string | null;
  credential_id: string | null;
  model_id: string | null;
  endpoint_id: string | null;
  status: HealthStatusValue;
  latency_ms: number | null;
  status_code: number | null;
  error_code: string | null;
  checked_at: string;
}

export interface HealthCheckRun {
  checked: number;
  statuses: Record<string, number>;
  duration_ms: number;
  started_at: string;
  failures: { provider_id: string; status: string; error_code: string | null }[];
}

/* -------------------------------------------------------------------------- */
/* M6 — usage analytics, request logs and exports                              */
/* -------------------------------------------------------------------------- */

export type UsageInterval = "hour" | "day" | "week" | "month";
export type UsageDimension = "provider" | "model" | "api_key";

export interface UsageFilterParams {
  /** Inclusive ISO-8601 start date (the panel converts Jalali at the edge). */
  date_from?: string;
  date_to?: string;
  provider_id?: string;
  model_id?: string;
  api_key_id?: string;
}

export interface UsageTotals {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  p95_latency_ms: number;
  avg_latency_ms: number | null;
  error_rate: number;
  error_count: number;
}

export interface UsagePoint {
  bucket: string;
  requests: number;
  tokens: number;
  cost: number;
  error_rate: number;
  /** Average for this interval; the window-wide p95 lives in `UsageTotals`. */
  avg_latency_ms: number;
}

export interface UsageSeries {
  interval: UsageInterval;
  points: UsagePoint[];
}

export interface UsageSummary {
  totals: UsageTotals;
  series: UsageSeries;
  generated_at: string;
  range_start: string;
  range_end: string;
}

export interface UsageBreakdownRow {
  key: string;
  label: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  errors: number;
  avg_latency_ms: number | null;
  error_rate: number;
}

export interface UsageBreakdown {
  dimension: UsageDimension;
  items: UsageBreakdownRow[];
}

export type RequestLogState = "pending" | "succeeded" | "failed";

export interface RequestLogEntry {
  id: string;
  request_id: string;
  api_key_name: string | null;
  provider_name: string | null;
  model_name: string | null;
  status_code: number;
  error_code: string | null;
  latency_ms: number;
  total_tokens: number;
  streaming: boolean;
  state: RequestLogState;
  attempt_count: number;
  created_at: string;
}

export interface RequestAttempt {
  id: string;
  attempt_number: number;
  is_final: boolean;
  retryable: boolean;
  provider_name: string | null;
  model_name: string | null;
  credential_label: string | null;
  endpoint_path: string | null;
  status_code: number;
  error_code: string | null;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  streaming: boolean;
  created_at: string;
}

export interface RequestLogDetail {
  request: RequestLogEntry;
  attempts: RequestAttempt[];
}

export interface RequestLogParams extends UsageFilterParams {
  state?: RequestLogState;
  error_code?: string;
  search?: string;
  page?: number;
  page_size?: number;
}
