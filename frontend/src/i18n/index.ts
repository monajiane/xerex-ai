/**
 * i18n bootstrap.
 *
 * Architecture (PROMPT.md 14.5):
 *  - every top-level section of `fa.ts` / `en.ts` is an i18next namespace;
 *  - Persian is the default **and** the fallback language;
 *  - adding a language = adding one file next to `fa.ts` / `en.ts` and listing it
 *    in `resources` below — no component changes;
 *  - `dir` is derived from the active locale (fa → rtl, en → ltr).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import fa from "./fa";
import en from "./en";

export type SupportedLocale = "fa" | "en";

export const resources = {
  fa,
  en,
} as const;

export const DEFAULT_LOCALE: SupportedLocale = "fa";
export const RTL_LOCALES: SupportedLocale[] = ["fa"];

export const NAMESPACES = Object.keys(fa) as Array<keyof typeof fa>;

export const LANGUAGE_STORAGE_KEY = "xerex.locale";

export function dirForLocale(locale: SupportedLocale): "rtl" | "ltr" {
  return RTL_LOCALES.includes(locale) ? "rtl" : "ltr";
}

export function isSupportedLocale(value: string | null | undefined): value is SupportedLocale {
  return value === "fa" || value === "en";
}

export function readStoredLocale(): SupportedLocale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return isSupportedLocale(stored) ? stored : DEFAULT_LOCALE;
}

/** Keeps `<html lang>` / `<html dir>` in sync with the active locale. */
export function applyDocumentLocale(locale: SupportedLocale): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.lang = locale;
  root.dir = dirForLocale(locale);
}

if (!i18n.isInitialized) {
  void i18n.use(initReactI18next).init({
    resources,
    lng: readStoredLocale(),
    fallbackLng: DEFAULT_LOCALE,
    defaultNS: "common",
    ns: NAMESPACES as string[],
    keySeparator: ".",
    nsSeparator: ":",
    interpolation: { escapeValue: false },
    returnNull: false,
  });
}

i18n.on("languageChanged", (locale) => {
  if (!isSupportedLocale(locale)) return;
  applyDocumentLocale(locale);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, locale);
  }
});

applyDocumentLocale((i18n.language as SupportedLocale) ?? DEFAULT_LOCALE);

export default i18n;
