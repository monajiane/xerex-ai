/**
 * Navigation sidebar.
 *
 * In Persian (RTL) the sidebar naturally sits on the right because the shell uses
 * the document writing direction — no directional utility is used anywhere.
 */
import { ChevronLeft, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { NAV_ITEMS, NAV_SECTIONS, type NavItem } from "@/app/navigation";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { useCapabilities } from "@/lib/api/useCapabilities";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  const { t } = useTranslation(["common", "nav"]);
  const nav = useDynamicTranslation("nav");
  const { isImplemented, planOf } = useCapabilities();

  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const planned = !isImplemented(item.capability);
    const label = nav.t(item.labelKey, { defaultValue: item.labelKey });

    const link = (
      <NavLink
        key={item.key}
        to={item.path}
        onClick={onCloseMobile}
        className={({ isActive }) =>
          cn(
            "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
            isActive
              ? "bg-brand-50 font-medium text-brand-700 dark:bg-brand-900/40 dark:text-brand-100"
              : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            collapsed && "justify-center px-2",
          )
        }
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        {!collapsed ? <span className="truncate">{label}</span> : null}
        {!collapsed && planned ? (
          <Badge tone="neutral" className="ms-auto">
            {planOf(item.capability)}
          </Badge>
        ) : null}
      </NavLink>
    );

    return collapsed ? (
      <Tooltip key={item.key} content={label}>
        {link}
      </Tooltip>
    ) : (
      link
    );
  };

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      ) : null}

      <aside
        aria-label={t("nav:openMenu")}
        className={cn(
          "z-50 flex shrink-0 flex-col border-e app-divide bg-white transition-[width,transform] dark:bg-slate-900",
          collapsed ? "w-[4.5rem]" : "w-64",
          "max-lg:fixed max-lg:inset-y-0 max-lg:start-0",
          mobileOpen ? "max-lg:translate-x-0" : "max-lg:hidden",
        )}
      >
        <div className="flex items-center gap-2 border-b app-divide px-3 py-4">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-600 text-sm font-bold text-white">
            XR
          </span>
          {!collapsed ? (
            <div className="min-w-0 text-start">
              <p className="truncate text-sm font-bold">{t("appName")}</p>
              <p className="app-muted truncate text-[0.6875rem]">{t("panel")}</p>
            </div>
          ) : null}
          <button
            type="button"
            onClick={onCloseMobile}
            className="ms-auto rounded-md p-1 app-muted hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"
            aria-label={t("actions.close")}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV_SECTIONS.map((section) => (
            <div key={section.key} className="mb-4">
              {!collapsed ? (
                <p className="app-muted px-3 pb-1.5 text-[0.6875rem] font-medium">
                  {nav.t(section.labelKey, { defaultValue: section.labelKey })}
                </p>
              ) : null}
              <div className="flex flex-col gap-0.5">
                {NAV_ITEMS.filter((item) => item.section === section.key).map(renderItem)}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t app-divide p-2">
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs app-muted hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label={collapsed ? t("nav:expand") : t("nav:collapse")}
          >
            {/* A chevron is a directional icon, so it is mirrored in RTL. */}
            <ChevronLeft className="size-4 rtl:-scale-x-100" aria-hidden="true" />
            {!collapsed ? <span>{t("nav:collapse")}</span> : null}
          </button>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
