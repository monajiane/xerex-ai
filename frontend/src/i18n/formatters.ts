/**
 * Locale-aware formatting (PROMPT.md section 14.6).
 *
 * Two families of values exist and they are formatted differently on purpose:
 *
 *  - **Presentation values** (percentages, counts, dates, costs) follow the
 *    administrator's locale: Jalali (Solar Hijri) dates, Persian digits when the
 *    "Persian numerals" setting is on.
 *  - **Technical values** (API keys, ids, model names, IPs, HTTP codes, token
 *    counts in technical views, logs) always use Latin digits and are rendered
 *    through LTR isolation containers, never reordered by the bidi algorithm.
 */

export type Locale = "fa" | "en";
export type NumeralStyle = "persian" | "latin";

export const LOCALE_TAGS: Record<Locale, string> = {
  fa: "fa-IR-u-ca-persian",
  en: "en-US",
};

const PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"] as const;

function localeTag(locale: Locale, numeralStyle: NumeralStyle): string {
  const base = LOCALE_TAGS[locale];
  if (numeralStyle === "latin") {
    // nu-latn keeps the Jalali calendar but renders Latin digits.
    return base.includes("-u-") ? `${base}-nu-latn` : `${base}-u-nu-latn`;
  }
  return base;
}

/** Converts every ASCII digit of a string to Persian digits. */
export function toPersianDigits(value: string): string {
  return value.replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

/** Converts Persian/Arabic-Indic digits back to ASCII digits. */
export function toLatinDigits(value: string): string {
  return value
    .replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660));
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export interface PresentationNumberOptions {
  locale: Locale;
  numeralStyle: NumeralStyle;
  maximumFractionDigits?: number;
  minimumFractionDigits?: number;
}

/** Number for on-screen presentation (dashboards, counters, tables). */
export function formatNumber(value: number, options: PresentationNumberOptions): string {
  if (!isFiniteNumber(value)) return "—";
  return new Intl.NumberFormat(localeTag(options.locale, options.numeralStyle), {
    maximumFractionDigits: options.maximumFractionDigits ?? 0,
    minimumFractionDigits: options.minimumFractionDigits,
  }).format(value);
}

/**
 * Number for technical contexts: always Latin digits, always grouped, and shown
 * inside an LTR container by the caller.
 */
export function formatTechnicalNumber(value: number, fractionDigits = 0): string {
  if (!isFiniteNumber(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(value);
}

/** Compact technical formatting for large token counts: 1.2M / 845K. */
export function formatCompact(value: number): string {
  if (!isFiniteNumber(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatPercent(ratio: number, options: PresentationNumberOptions): string {
  if (!isFiniteNumber(ratio)) return "—";
  return new Intl.NumberFormat(localeTag(options.locale, options.numeralStyle), {
    style: "percent",
    maximumFractionDigits: 2,
  }).format(ratio);
}

export function formatDuration(ms: number, options: PresentationNumberOptions): string {
  if (!isFiniteNumber(ms)) return "—";
  if (ms < 1000) {
    return `${formatNumber(Math.round(ms), options)} ${options.locale === "fa" ? "میلی‌ثانیه" : "ms"}`;
  }
  return `${formatNumber(ms / 1000, { ...options, maximumFractionDigits: 2 })}${
    options.locale === "fa" ? " ثانیه" : " s"
  }`;
}

/** Short uptime label: 2 روز و 4 ساعت. */
export function formatUptime(seconds: number, locale: Locale): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const unit = (value: number, fa: string, en: string) =>
    locale === "fa" ? `${toPersianDigits(String(value))} ${fa}` : `${value} ${en}`;
  if (days > 0) return `${unit(days, "روز", "d")} ${unit(hours, "ساعت", "h")}`;
  if (hours > 0) return `${unit(hours, "ساعت", "h")} ${unit(minutes, "دقیقه", "m")}`;
  return unit(minutes, "دقیقه", "m");
}

/** Jalali (fa) or Gregorian (en) date, e.g. «۲۷ شهریور ۱۴۰۵». */
export function formatDate(
  value: string | number | Date | null | undefined,
  options: PresentationNumberOptions,
): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(localeTag(options.locale, options.numeralStyle), {
    dateStyle: "medium",
  }).format(date);
}

export function formatDateTime(
  value: string | number | Date | null | undefined,
  options: PresentationNumberOptions & { timeZone?: string },
): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(localeTag(options.locale, options.numeralStyle), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: options.timeZone,
  }).format(date);
}

/** ISO-8601 in UTC — used for technical contexts, exports and tooltips. */
export function formatIsoUtc(value: string | number | Date | null | undefined): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().replace(".000", "");
}

const RELATIVE_UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
  ["second", 1_000],
];

/** «۳ دقیقه پیش» for "last checked". */
export function formatRelativeTime(
  value: string | number | Date | null | undefined,
  locale: Locale,
  now: Date = new Date(),
): string {
  if (!value) return locale === "fa" ? "تا کنون انجام نشده" : "never";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diff = date.getTime() - now.getTime();
  const absolute = Math.abs(diff);
  if (absolute < 5_000) return locale === "fa" ? "همین حالا" : "just now";
  const formatter = new Intl.RelativeTimeFormat(locale === "fa" ? "fa-IR" : "en-US", {
    numeric: "auto",
  });
  for (const [unit, ms] of RELATIVE_UNITS) {
    if (absolute >= ms || unit === "second") {
      return formatter.format(Math.round(diff / ms), unit);
    }
  }
  return "—";
}

/** Cost with an explicit currency, never a bare ambiguous number. */
export function formatCost(
  amount: number,
  options: PresentationNumberOptions & { currency?: string; currencyLabel?: string },
): string {
  const formatted = new Intl.NumberFormat(localeTag(options.locale, options.numeralStyle), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  }).format(amount);
  const label = options.currencyLabel ?? options.currency ?? (options.locale === "fa" ? "دلار" : "USD");
  return `${formatted} ${label}`;
}

/** Locale-aware URL/identifier trimming without breaking LTR rendering. */
export function truncateMiddle(value: string, maxLength = 32): string {
  if (value.length <= maxLength) return value;
  const half = Math.floor((maxLength - 1) / 2);
  return `${value.slice(0, half)}…${value.slice(-half)}`;
}

export const formatters = {
  toPersianDigits,
  toLatinDigits,
  formatNumber,
  formatTechnicalNumber,
  formatCompact,
  formatPercent,
  formatDuration,
  formatUptime,
  formatDate,
  formatDateTime,
  formatIsoUtc,
  formatRelativeTime,
  formatCost,
  truncateMiddle,
};

export default formatters;
