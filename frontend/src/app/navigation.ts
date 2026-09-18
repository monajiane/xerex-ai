/**
 * Navigation model.
 *
 * Persian labels come from the `nav` namespace; the `capability` key maps to the
 * backend capability flags so a planned module is visibly marked as «در گام بعدی»
 * instead of pretending to be functional.
 */
import {
  Activity,
  BarChart3,
  Boxes,
  Cpu,
  FileClock,
  KeyRound,
  LayoutDashboard,
  Route,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  key: string;
  path: string;
  labelKey: string;
  icon: LucideIcon;
  section: "overview" | "gateway" | "insights" | "administration";
  /** Capability key returned by `GET /system/info`. */
  capability: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    key: "dashboard",
    path: "/",
    labelKey: "dashboard",
    icon: LayoutDashboard,
    section: "overview",
    capability: "dashboard",
  },
  {
    key: "providers",
    path: "/providers",
    labelKey: "providers",
    icon: Boxes,
    section: "gateway",
    capability: "providers",
  },
  {
    key: "credentials",
    path: "/credentials",
    labelKey: "credentials",
    icon: KeyRound,
    section: "gateway",
    capability: "provider_credentials",
  },
  {
    key: "models",
    path: "/models",
    labelKey: "models",
    icon: Cpu,
    section: "gateway",
    capability: "models",
  },
  {
    key: "apiKeys",
    path: "/api-keys",
    labelKey: "apiKeys",
    icon: ShieldCheck,
    section: "gateway",
    capability: "api_keys",
  },
  {
    key: "routing",
    path: "/routing",
    labelKey: "routing",
    icon: Route,
    section: "gateway",
    capability: "routing",
  },
  {
    key: "health",
    path: "/health",
    labelKey: "health",
    icon: Activity,
    section: "insights",
    capability: "health",
  },
  {
    key: "usage",
    path: "/usage",
    labelKey: "usage",
    icon: BarChart3,
    section: "insights",
    capability: "usage",
  },
  {
    key: "logs",
    path: "/logs",
    labelKey: "logs",
    icon: ScrollText,
    section: "insights",
    capability: "request_logs",
  },
  {
    key: "auditLogs",
    path: "/audit-logs",
    labelKey: "auditLogs",
    icon: FileClock,
    section: "insights",
    capability: "audit_logs",
  },
  {
    key: "users",
    path: "/users",
    labelKey: "users",
    icon: Users,
    section: "administration",
    capability: "admin_users",
  },
  {
    key: "settings",
    path: "/settings",
    labelKey: "settings",
    icon: Settings,
    section: "administration",
    capability: "settings",
  },
];

export const NAV_SECTIONS: Array<{ key: NavItem["section"]; labelKey: string }> = [
  { key: "overview", labelKey: "sectionOverview" },
  { key: "gateway", labelKey: "sectionGateway" },
  { key: "insights", labelKey: "sectionInsights" },
  { key: "administration", labelKey: "sectionAdministration" },
];

export function findNavItem(pathname: string): NavItem | undefined {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  return NAV_ITEMS.find((item) => item.path === normalized);
}
