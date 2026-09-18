/**
 * Locale & numeral preferences.
 *
 * Presentation values follow the administrator's language and numeral style;
 * technical values are always formatted with Latin digits (PROMPT.md 14.6) — the
 * `t` helpers below are only used for human-readable output.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  type Locale,
  type NumeralStyle,
  formatCost,
  formatDate,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  formatTechnicalNumber,
  formatUptime,
  toPersianDigits,
} from "@/i18n/formatters";
import { isSupportedLocale } from "@/i18n";

const NUMERAL_STORAGE_KEY = "xerex.numeralStyle";
const TIMEZONE_STORAGE_KEY = "xerex.timezone";
const DEFAULT_TIMEZONE = "Asia/Tehran";

interface LocaleContextValue {
  locale: Locale;
  numeralStyle: NumeralStyle;
  timezone: string;
  setLocale: (locale: Locale) => void;
  setNumeralStyle: (style: NumeralStyle) => void;
  setTimezone: (timezone: string) => void;
  /** Human readable number for the current locale. */
  n: (value: number, maximumFractionDigits?: number) => string;
  /** Percentage from a 0..1 ratio. */
  pct: (ratio: number) => string;
  /** Token counts and ids: Latin digits, always safe inside an LTR container. */
  tech: (value: number, fractionDigits?: number) => string;
  duration: (ms: number) => string;
  uptime: (seconds: number) => string;
  date: (value: string | number | Date | null | undefined) => string;
  dateTime: (value: string | number | Date | null | undefined) => string;
  relative: (value: string | number | Date | null | undefined) => string;
  cost: (amount: number, currencyLabel?: string) => string;
  digits: (value: string | number) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readStored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  if (typeof window === "undefined") return fallback;
  const stored = window.localStorage.getItem(key);
  return stored && (allowed as readonly string[]).includes(stored) ? (stored as T) : fallback;
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const [numeralStyle, setNumeralStyleState] = useState<NumeralStyle>(() =>
    readStored<NumeralStyle>(NUMERAL_STORAGE_KEY, ["persian", "latin"], "persian"),
  );
  const [timezone, setTimezoneState] = useState<string>(
    () =>
      (typeof window !== "undefined" && window.localStorage.getItem(TIMEZONE_STORAGE_KEY)) ||
      DEFAULT_TIMEZONE,
  );

  const locale: Locale = isSupportedLocale(i18n.language) ? i18n.language : "fa";

  const setLocale = useCallback(
    (next: Locale) => {
      void i18n.changeLanguage(next);
    },
    [i18n],
  );

  const setNumeralStyle = useCallback((style: NumeralStyle) => {
    setNumeralStyleState(style);
    window.localStorage.setItem(NUMERAL_STORAGE_KEY, style);
  }, []);

  const setTimezone = useCallback((next: string) => {
    setTimezoneState(next);
    window.localStorage.setItem(TIMEZONE_STORAGE_KEY, next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "fa" ? "rtl" : "ltr";
  }, [locale]);

  const value = useMemo<LocaleContextValue>(() => {
    const base = { locale, numeralStyle };
    return {
      locale,
      numeralStyle,
      timezone,
      setLocale,
      setNumeralStyle,
      setTimezone,
      n: (v, maximumFractionDigits = 0) => formatNumber(v, { ...base, maximumFractionDigits }),
      pct: (ratio) => formatPercent(ratio, base),
      tech: (v, fractionDigits = 0) => formatTechnicalNumber(v, fractionDigits),
      duration: (ms) => formatDuration(ms, base),
      uptime: (seconds) => formatUptime(seconds, locale),
      date: (v) => formatDate(v, base),
      dateTime: (v) => formatDateTime(v, { ...base, timeZone: timezone }),
      relative: (v) => formatRelativeTime(v, locale),
      cost: (amount, currencyLabel) => formatCost(amount, { ...base, currencyLabel }),
      digits: (v) => (numeralStyle === "persian" ? toPersianDigits(String(v)) : String(v)),
    };
  }, [locale, numeralStyle, setLocale, setNumeralStyle, setTimezone, timezone]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used inside <LocaleProvider>");
  return context;
}
