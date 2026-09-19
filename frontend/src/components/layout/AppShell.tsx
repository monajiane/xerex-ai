/**
 * Application shell: sidebar (inline start → right edge in Persian), top bar and
 * the routed content area.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation } from "react-router-dom";

import { useDynamicTranslation } from "@/i18n/dynamic";
import { useCapabilities, useSystemInfo } from "@/lib/api/useCapabilities";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { findNavItem } from "@/app/navigation";

const COLLAPSE_STORAGE_KEY = "xerex.sidebarCollapsed";

export function AppShell() {
  const { t } = useTranslation(["nav", "common"]);
  const nav = useDynamicTranslation("nav");
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1",
  );
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, value ? "0" : "1");
      return !value;
    });
  };

  const systemInfo = useSystemInfo();
  const { milestone } = useCapabilities();
  const activeItem = findNavItem(location.pathname);
  const pageTitle = activeItem
    ? nav.t(activeItem.labelKey, { defaultValue: activeItem.labelKey })
    : t("dashboard");

  useEffect(() => {
    document.title = `${pageTitle} — Xerex AI`;
  }, [pageTitle]);

  return (
    <div className="flex min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[70] focus:rounded-md focus:bg-brand-600 focus:px-3 focus:py-2 focus:text-sm focus:text-white focus:start-3 focus:top-3"
      >
        {t("home")}
      </a>

      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMobileNav={() => setMobileOpen(true)} />
        <main id="main-content" className="flex-1 px-4 py-6 sm:px-6">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
        <footer className="border-t app-divide px-6 py-4 text-center text-[0.6875rem] app-muted">
          {t("common:build.footer", {
            milestone: milestone || "—",
            version: systemInfo.data?.version ?? "—",
          })}
        </footer>
      </div>
    </div>
  );
}

export default AppShell;
