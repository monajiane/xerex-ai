/**
 * Jalali ⇄ Gregorian conversion for the date filters.
 *
 * The API speaks ISO-8601 (Gregorian) — that is the technical contract. Persian users
 * think and filter in Jalali dates («۱۴۰۳/۰۵/۱۲»), so conversion happens **here**, at
 * the boundary, and nowhere else. The arithmetic is the standard Jalali algorithm; the
 * tests pin the leap-year and new-year boundaries that matter for filters.
 *
 * Digit conversion is shared with the formatters — one table, one behaviour.
 */
import { toLatinDigits, toPersianDigits } from "@/i18n/formatters";

function div(a: number, b: number): number {
  return Math.floor(a / b);
}

/** Gregorian → Jalali (Jalaali-js algorithm, MIT). */
export function toJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const gDaysInMonth = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let jy = gy <= 1600 ? 0 : 979;
  gy -= gy <= 1600 ? 621 : 1600;
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    365 * gy +
    div(gy2 + 3, 4) -
    div(gy2 + 99, 100) +
    div(gy2 + 399, 400) -
    80 +
    gd +
    gDaysInMonth.slice(0, gm - 1).reduce((total, days) => total + days, 0);
  jy += 33 * div(days, 12053);
  days %= 12053;
  jy += 4 * div(days, 1461);
  days %= 1461;
  jy += div(days - 1, 365);
  if (days > 365) days = (days - 1) % 365;
  days = days < 186 ? days : days - 186 + (days > 336 ? 0 : 0);
  const jm = 1 + div(days, 31);
  const jd = 1 + (days % 31);
  return [jy, jm, jd];
}

/** Jalali → Gregorian. */
export function toGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  let gy = jy <= 979 ? 621 : 1600;
  jy -= jy <= 979 ? 0 : 979;
  let days =
    365 * jy +
    div(jy, 33) * 8 +
    div((jy % 33) + 3, 4) +
    78 +
    jd +
    (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  gy += 400 * div(days, 146097);
  days %= 146097;
  if (days > 36524) {
    gy += 100 * div(--days, 36524);
    days %= 36524;
    if (days >= 365) days++;
  }
  gy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    gy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  let gd = days + 1;
  const isLeap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
  const monthDays = [0, 31, isLeap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gm = 0;
  while (gm < 13 && gd > monthDays[gm]) {
    gd -= monthDays[gm];
    gm++;
  }
  return [gy, gm, gd];
}

const pad = (value: number): string => String(value).padStart(2, "0");

/** `1403/05/12` (Persian digits by default) for display in the panel. */
export function formatJalali(
  isoDate: string | null | undefined,
  { persianDigits = true }: { persianDigits?: boolean } = {},
): string {
  if (!isoDate) return "—";
  const [year, month, day] = isoDate.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "—";
  const [jy, jm, jd] = toJalali(year, month, day);
  const formatted = `${jy}/${pad(jm)}/${pad(jd)}`;
  return persianDigits ? toPersianDigits(formatted) : formatted;
}

/** `1403/05/12` or `۱۴۰۳/۰۵/۱۲` → `2024-08-02`. Returns `null` when unusable. */
export function parseJalaliInput(value: string): string | null {
  const normalised = toLatinDigits(value.trim()).replace(/[-.]/g, "/");
  const match = /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(normalised);
  if (!match) return null;
  const [jy, jm, jd] = [Number(match[1]), Number(match[2]), Number(match[3])];
  if (jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
  const [gy, gm, gd] = toGregorian(jy, jm, jd);
  return `${gy}-${pad(gm)}-${pad(gd)}`;
}

/** ISO date → Jalali input value in Latin digits (what the text field holds). */
export function toJalaliInput(isoDate: string | null | undefined): string {
  return formatJalali(isoDate, { persianDigits: false });
}

/** Today in Jalali, as the panel's default filter value. */
export function todayJalali(): string {
  return formatJalali(new Date().toISOString(), { persianDigits: false });
}
