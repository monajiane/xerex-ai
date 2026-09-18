/**
 * Guards the localization architecture (PROMPT.md 14.5 / 14.10):
 *  - `fa` and `en` expose exactly the same key set;
 *  - Persian is the default and the fallback language;
 *  - visible Persian copy never contains Finglish or untranslated English labels;
 *  - Persian copy uses the approved terminology.
 */
import { describe, expect, it } from "vitest";

import fa from "@/i18n/fa";
import en from "@/i18n/en";
import {
  DEFAULT_LOCALE,
  NAMESPACES,
  dirForLocale,
  isSupportedLocale,
} from "@/i18n";

type Tree = Record<string, unknown>;

function collectKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object") return collectKeys(value as Tree, path);
    return [path];
  });
}

function collectStrings(tree: Tree): Array<[string, string]> {
  return Object.entries(tree).flatMap(([key, value]): Array<[string, string]> => {
    if (value && typeof value === "object") return collectStrings(value as Tree);
    return typeof value === "string" ? [[key, value]] : [];
  });
}

describe("i18n architecture", () => {
  it("keeps the Persian and English key sets identical", () => {
    expect(collectKeys(en as unknown as Tree).sort()).toEqual(
      collectKeys(fa as unknown as Tree).sort(),
    );
  });

  it("defaults to Persian and falls back to Persian", () => {
    expect(DEFAULT_LOCALE).toBe("fa");
    expect(isSupportedLocale("fa")).toBe(true);
    expect(isSupportedLocale("de")).toBe(false);
  });

  it("maps locales to the correct writing direction", () => {
    expect(dirForLocale("fa")).toBe("rtl");
    expect(dirForLocale("en")).toBe("ltr");
  });

  it("exposes one namespace per module section", () => {
    expect(NAMESPACES).toContain("dashboard");
    expect(NAMESPACES).toContain("errors");
    expect(NAMESPACES).toContain("enums");
    expect(NAMESPACES.length).toBeGreaterThanOrEqual(10);
  });
});

describe("Persian copy", () => {
  const persianStrings = collectStrings(fa as unknown as Tree);

  it("has no empty values", () => {
    const empty = persianStrings.filter(([, value]) => value.trim().length === 0);
    expect(empty).toEqual([]);
  });

  it("contains no Finglish or untranslated English labels", () => {
    // Whole English words that must never appear inside Persian UI copy.
    const forbidden = [
      /\bDashboard\b/,
      /\bProviders\b/,
      /\bModels\b/,
      /\bSettings\b/,
      /\bEnabled\b/,
      /\bDisabled\b/,
      /\bStatus\b/,
      /\bHealth\b/,
      /\bRouting\b/,
      /\bUsage\b/,
      /\bLogs\b/,
      /\bUsers\b/,
      /\bدیتا\b/,
      /\bفانکشن\b/,
    ];
    // Technical exceptions that are intentionally Latin inside Persian sentences.
    const allowed = new Set([
      "enums.providerKind.openai",
      "enums.providerKind.anthropic",
      "enums.providerKind.google",
      "enums.providerKind.deepseek",
      "enums.providerKind.qwen",
      "enums.providerKind.openai_compatible",
      "common.language.en",
      "auth.emailPlaceholder",
      "roadmap.endpoint.milestone",
      "common.build.milestone",
      "dashboard.subtitle",
    ]);

    const violations = persianStrings
      .filter(([key]) => !allowed.has(key))
      .filter(([, value]) => forbidden.some((pattern) => pattern.test(value)))
      .map(([key]) => key);

    expect(violations).toEqual([]);
  });

  it("uses the approved terminology for core concepts", () => {
    expect(fa.nav.providers).toBe("ارائه‌دهندگان");
    expect(fa.nav.models).toBe("مدل‌ها");
    expect(fa.nav.apiKeys).toBe("کلیدهای API");
    expect(fa.nav.credentials).toBe("اطلاعات احراز هویت");
    expect(fa.nav.health).toBe("سلامت سیستم");
    expect(fa.nav.routing).toBe("مسیریابی");
    expect(fa.nav.usage).toBe("مصرف");
    expect(fa.nav.settings).toBe("تنظیمات");
    expect(fa.nav.logs).toBe("گزارش‌ها");
    expect(fa.common.status.enabled).toBe("فعال");
    expect(fa.common.status.disabled).toBe("غیرفعال");
  });

  it("keeps product names untranslated in both languages", () => {
    expect(fa.enums.providerKind.google).toBe("Gemini");
    expect(fa.enums.providerKind.deepseek).toBe("DeepSeek");
    expect(en.enums.providerKind.google).toBe("Gemini");
  });
});
