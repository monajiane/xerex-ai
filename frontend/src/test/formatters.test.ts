/**
 * Persian date / number formatting (PROMPT.md 14.6).
 * Presentation values follow the locale; technical values stay Latin and stable.
 */
import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatDateTime,
  formatIsoUtc,
  formatNumber,
  formatRelativeTime,
  formatTechnicalNumber,
  toLatinDigits,
  toPersianDigits,
} from "@/i18n/formatters";

const SAMPLE = new Date("2026-09-18T10:30:00.000Z");

describe("numeral handling", () => {
  it("converts digits in both directions", () => {
    expect(toPersianDigits("2026")).toBe("۲۰۲۶");
    expect(toLatinDigits("۲۰۲۶")).toBe("2026");
  });

  it("uses Persian digits for presentation when requested", () => {
    expect(formatNumber(1234, { locale: "fa", numeralStyle: "persian" })).toMatch(/[۰-۹]/);
  });

  it("uses Latin digits for presentation in latin style", () => {
    expect(formatNumber(1234, { locale: "fa", numeralStyle: "latin" })).toBe("1,234");
  });

  it("always keeps technical numbers Latin and grouped", () => {
    expect(formatTechnicalNumber(1_234_567)).toBe("1,234,567");
  });
});

describe("Jalali dates", () => {
  it("formats a Persian calendar date for the Persian locale", () => {
    const formatted = formatDate(SAMPLE, { locale: "fa", numeralStyle: "persian" });
    // Persian month names never appear in Gregorian output.
    expect(formatted).toMatch(/[۰-۹]/);
    expect(formatted).toMatch(/شهریور|مهر/);
  });

  it("keeps Gregorian formatting for English", () => {
    const formatted = formatDate(SAMPLE, { locale: "en", numeralStyle: "latin" });
    expect(formatted).toContain("Sep");
  });

  it("exposes ISO-8601 UTC for technical contexts and exports", () => {
    expect(formatIsoUtc(SAMPLE)).toBe("2026-09-18T10:30:00Z");
  });

  it("honours an explicit timezone", () => {
    const tehran = formatDateTime(SAMPLE, {
      locale: "fa",
      numeralStyle: "latin",
      timeZone: "Asia/Tehran",
    });
    const utc = formatDateTime(SAMPLE, { locale: "fa", numeralStyle: "latin", timeZone: "UTC" });
    expect(tehran).not.toBe(utc);
  });
});

describe("relative time", () => {
  it("renders Persian relative time", () => {
    const threeMinutesAgo = new Date(SAMPLE.getTime() - 3 * 60_000);
    const label = formatRelativeTime(threeMinutesAgo, "fa", SAMPLE);
    expect(label).toMatch(/[۰-۹]/);
    expect(label).toContain("دقیقه");
  });

  it("handles missing values without crashing", () => {
    expect(formatRelativeTime(null, "fa")).toBe("تا کنون انجام نشده");
    expect(formatRelativeTime(null, "en")).toBe("never");
  });
});
