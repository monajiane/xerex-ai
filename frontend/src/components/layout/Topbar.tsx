/**
 * Top bar: page context, live system status, theme, language and account menu.
 *
 * Mixed Persian/English content is handled explicitly here: the environment and
 * milestone identifiers are rendered inside `<Ltr>` islands so they stay readable
 * between Persian words (PROMPT.md 14.7).
 */
import { Languages, LogOut, Menu as MenuIcon, Moon, Monitor, Sun, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Menu } from "@/components/ui/menu";
import { Ltr } from "@/components/common/Ltr";
import { useAuth } from "@/features/auth/AuthProvider";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { useCapabilities } from "@/lib/api/useCapabilities";
import { useLocale } from "@/lib/locale/LocaleProvider";
import { useTheme, type ThemePreference } from "@/lib/theme/ThemeProvider";

interface TopbarProps {
  onOpenMobileNav: () => void;
}

export function Topbar({ onOpenMobileNav }: TopbarProps) {
  const { t } = useTranslation(["common", "layout", "nav"]);
  const enums = useDynamicTranslation("enums");
  const { locale, setLocale, dateTime } = useLocale();
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuth();
  const { milestone } = useCapabilities();
  const env = (import.meta.env.MODE ?? "development") as string;

  const themeIcons: Record<ThemePreference, typeof Sun> = {
    light: Sun,
    dark: Moon,
    system: Monitor,
  };
  const ThemeIcon = themeIcons[theme];

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b app-divide bg-white/95 px-4 py-3 backdrop-blur dark:bg-slate-900/95">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onOpenMobileNav}
        aria-label={t("nav:openMenu")}
      >
        <MenuIcon aria-hidden="true" />
      </Button>

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Badge tone="brand">
          <span>{t("build.milestone")}</span>
          <Ltr mono>{milestone || "M1"}</Ltr>
        </Badge>
        <Badge tone="neutral" className="hidden sm:inline-flex">
          <span>{t("build.environment")}</span>
          <Ltr mono>{env}</Ltr>
        </Badge>
        <span className="app-muted hidden truncate text-[0.6875rem] xl:inline">
          {t("build.serverTime")}: <Ltr mono>{dateTime(new Date())}</Ltr>
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(locale === "fa" ? "en" : "fa")}
          aria-label={t("language.switchTo", {
            language: locale === "fa" ? t("language.en") : t("language.fa"),
          })}
        >
          <Languages aria-hidden="true" />
          <Ltr className="hidden sm:inline">{locale === "fa" ? "EN" : "FA"}</Ltr>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={t("theme.label")}
          title={t("theme.label")}
        >
          <ThemeIcon aria-hidden="true" />
        </Button>

        {user ? (
          <Menu
            menuLabel={t("layout:userMenu.profile")}
            trigger={({ toggle }) => (
              <button
                type="button"
                onClick={toggle}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <span className="grid size-7 place-items-center rounded-full bg-brand-100 text-[0.6875rem] font-bold text-brand-700 dark:bg-brand-900/60 dark:text-brand-100">
                  {user.full_name?.slice(0, 1) ?? user.email.slice(0, 1).toUpperCase()}
                </span>
                <span className="hidden text-start text-xs sm:block">
                  <span className="block font-medium">{user.full_name ?? user.email}</span>
                  <span className="app-muted block text-[0.625rem]">
                    {enums.t(`role.${user.role}`, { defaultValue: user.role })}
                  </span>
                </span>
                <UserRound className="size-4 app-muted sm:hidden" aria-hidden="true" />
              </button>
            )}
            items={[
              {
                label: `${t("layout:userMenu.signedInAs")} ${user.email}`,
                onSelect: () => undefined,
                disabled: true,
              },
              {
                label: t("layout:userMenu.signOut"),
                onSelect: () => void logout(),
                icon: <LogOut className="size-3.5 rtl:-scale-x-100" aria-hidden="true" />,
                tone: "danger" as const,
              },
            ]}
          />
        ) : null}
      </div>
    </header>
  );
}

export default Topbar;
