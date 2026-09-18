import { useTranslation } from "react-i18next";

import { LoadingState } from "@/components/common/DataState";
import { useAuth } from "@/features/auth/AuthProvider";
import { AuthGate } from "@/features/auth/BootstrapPage";

/**
 * Route guard. RBAC itself is enforced by the API; this only decides what the
 * administrator can reach in the interface.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation("states");
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="grid min-h-screen place-items-center">
        <LoadingState label={t("loadingTitle")} />
      </div>
    );
  }

  if (status === "anonymous") return <AuthGate />;

  return <>{children}</>;
}

export default RequireAuth;
