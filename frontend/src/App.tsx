/**
 * Route table.
 *
 * Modules that are not implemented yet render `<PlaceholderModule>`, which shows
 * the milestone and the planned API contract instead of fabricated data.
 */
import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { PlaceholderModule } from "@/components/common/PlaceholderModule";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { AuditLogsPage } from "@/features/audit/AuditLogsPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { HealthPage } from "@/features/health/HealthPage";
import { NotFoundPage } from "@/features/system/NotFoundPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { UsersPage } from "@/features/users/UsersPage";

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
        <Route path="/providers" element={<PlaceholderModule moduleKey="providers" />} />
        <Route
          path="/credentials"
          element={<PlaceholderModule moduleKey="credentials" roadmapKey="provider_credentials" />}
        />
        <Route path="/models" element={<PlaceholderModule moduleKey="models" />} />
        <Route
          path="/api-keys"
          element={<PlaceholderModule moduleKey="apiKeys" roadmapKey="api_keys" />}
        />
        <Route path="/routing" element={<PlaceholderModule moduleKey="routing" />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/usage" element={<PlaceholderModule moduleKey="usage" />} />
        <Route path="/logs" element={<PlaceholderModule moduleKey="logs" roadmapKey="request_logs" />} />
        <Route path="/audit-logs" element={<AuditLogsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default App;
