/**
 * Route table.
 *
 * Every admin module of PROMPT.md 5 has a real page. Pages are **lazy-loaded** (M7): the
 * first paint only ships the shell, the dashboard and the shared UI kit, and each module
 * arrives as its own chunk when it is opened. That keeps the initial bundle small for an
 * administrator on a slow link, and it is why `<Suspense>` renders the same Persian
 * «در حال دریافت اطلاعات» state the pages use for their own loading state.
 */
import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { LoadingState } from "@/components/common/DataState";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { DashboardPage } from "@/features/dashboard/DashboardPage";

const ProvidersPage = lazy(() => import("@/features/providers/ProvidersPage"));
const ProviderDetailPage = lazy(() => import("@/features/providers/ProviderDetailPage"));
const CredentialsPage = lazy(() => import("@/features/providers/CredentialsPage"));
const ModelsPage = lazy(() => import("@/features/models/ModelsPage"));
const ModelDetailPage = lazy(() => import("@/features/models/ModelDetailPage"));
const ApiKeysPage = lazy(() => import("@/features/api-keys/ApiKeysPage"));
const RoutingPage = lazy(() => import("@/features/routing/RoutingPage"));
const HealthPage = lazy(() => import("@/features/health/HealthPage"));
const UsagePage = lazy(() => import("@/features/usage/UsagePage"));
const RequestLogsPage = lazy(() => import("@/features/logs/RequestLogsPage"));
const AuditLogsPage = lazy(() => import("@/features/audit/AuditLogsPage"));
const UsersPage = lazy(() => import("@/features/users/UsersPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const NotFoundPage = lazy(() => import("@/features/system/NotFoundPage"));

export function App() {
  return (
    <Routes>
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/providers/:providerId" element={<ProviderDetailPage />} />
        <Route path="/credentials" element={<CredentialsPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/models/:modelId" element={<ModelDetailPage />} />
        <Route path="/api-keys" element={<ApiKeysPage />} />
        <Route path="/routing" element={<RoutingPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/usage" element={<UsagePage />} />
        <Route path="/logs" element={<RequestLogsPage />} />
        <Route path="/audit-logs" element={<AuditLogsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/** Wraps the routed content so a lazy chunk shows the shared Persian loading state. */
export function AppRoutes() {
  return (
    <Suspense fallback={<LoadingState />}>
      <App />
    </Suspense>
  );
}

export default AppRoutes;
