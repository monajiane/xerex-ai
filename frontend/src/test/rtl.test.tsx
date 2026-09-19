/**
 * RTL and bidi guarantees (PROMPT.md 14.2 / 14.4 / 14.10):
 *  - the document root is `lang="fa" dir="rtl"`;
 *  - technical values are isolated as LTR runs;
 *  - the codebase uses logical utilities only (no `ml-`, `pr-`, `left-`, …).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Ltr } from "@/components/common/Ltr";
import { CodeBlock } from "@/components/common/CodeBlock";
import { applyDocumentLocale } from "@/i18n";

const SOURCE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function walk(directory: string): string[] {
  return readdirSync(directory).flatMap((entry: string) => {
    const fullPath = join(directory, entry);
    if (statSync(fullPath).isDirectory()) {
      if (entry === "test") return [];
      return walk(fullPath);
    }
    return /\.(tsx|ts)$/.test(entry) ? [fullPath] : [];
  });
}

describe("layout resilience at 1280px and 1920px", () => {
  it("keeps every table inside a horizontal scroll container", () => {
    // A long technical value (an endpoint path, a model id) must widen the table, not
    // the page: every <Table> in the panel is wrapped in <TableWrapper>, which scrolls.
    const offenders: string[] = [];
    for (const file of walk(SOURCE_ROOT)) {
      const content = readFileSync(file, "utf8");
      if (!content.includes("<Table>")) continue;
      const tables = content.split("<Table>").length - 1;
      const wrappers = content.split("<TableWrapper").length - 1;
      if (wrappers < tables) offenders.push(`${file.replace(SOURCE_ROOT, "")}: ${tables} tables`);
    }
    expect(offenders).toEqual([]);
  });

  it("keeps long Persian and long technical values from overflowing the layout", () => {
    // The shell clips its content column (`min-w-0`) so a wide child cannot push the
    // sidebar off screen; the table primitive scrolls instead of overflowing.
    const shell = readFileSync(join(SOURCE_ROOT, "components/layout/AppShell.tsx"), "utf8");
    expect(shell).toContain("min-w-0");

    const table = readFileSync(join(SOURCE_ROOT, "components/ui/table.tsx"), "utf8");
    expect(table).toContain("overflow-x-auto");

    // Long technical labels are rendered inside LTR islands, which keeps a 512-character
    // model name from reordering the Persian text around it.
    const usage = readFileSync(join(SOURCE_ROOT, "features/usage/UsagePage.tsx"), "utf8");
    expect(usage).toContain("<Ltr>{row.label}</Ltr>");
    const logs = readFileSync(join(SOURCE_ROOT, "features/logs/RequestLogsPage.tsx"), "utf8");
    expect(logs).toContain("<Ltr mono>{entry.request_id}</Ltr>");
  });
});

describe("document direction", () => {
  it("sets Persian and RTL on the document root", () => {
    applyDocumentLocale("fa");
    expect(document.documentElement.lang).toBe("fa");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("switches direction with the locale", () => {
    applyDocumentLocale("en");
    expect(document.documentElement.dir).toBe("ltr");
    applyDocumentLocale("fa");
  });
});

describe("LTR isolation islands", () => {
  it("marks inline technical values as isolated LTR runs", () => {
    render(<Ltr data-testid="value">xrx_live_8f2a…</Ltr>);
    const element = screen.getByTestId("value");
    expect(element).toHaveAttribute("dir", "ltr");
    expect(element).toHaveAttribute("lang", "en");
    expect(element.className).toContain("ltr-isolate");
  });

  it("keeps an API key intact inside a Persian sentence", () => {
    render(
      <p>
        کلید API: <Ltr data-testid="key">xrx_live_8f2a_secret</Ltr>
      </p>,
    );
    const key = screen.getByTestId("key");
    expect(key.textContent).toBe("xrx_live_8f2a_secret");
    expect(key).toHaveAttribute("dir", "ltr");
  });

  it("uses an isolated block for JSON and logs", () => {
    render(<CodeBlock value='{"provider_id":"p1"}' />);
    const code = screen.getByText(/"provider_id"/, { selector: "code" });
    const pre = code.closest("pre");
    expect(pre).toHaveAttribute("dir", "ltr");
    expect(pre?.className).toContain("ltr-block");
  });
});

describe("logical CSS utilities", () => {
  const FORBIDDEN = [
    /(?<![\w-])ml-\d/,
    /(?<![\w-])mr-\d/,
    /(?<![\w-])pl-\d/,
    /(?<![\w-])pr-\d/,
    /(?<![\w-])left-\d/,
    /(?<![\w-])right-\d/,
    /(?<![\w-])text-left\b/,
    /(?<![\w-])text-right\b/,
  ];

  it("never uses physical left/right utilities", () => {
    const violations: string[] = [];
    for (const file of walk(SOURCE_ROOT)) {
      const content = readFileSync(file, "utf8");
      content.split("\n").forEach((line: string, index: number) => {
        // `unicode-bidi`/CSS files and comments are not class names.
        if (line.trimStart().startsWith("*") || line.trimStart().startsWith("//")) return;
        for (const pattern of FORBIDDEN) {
          if (pattern.test(line)) {
            violations.push(`${file.replace(SOURCE_ROOT, "")}:${index + 1} → ${line.trim()}`);
          }
        }
      });
    }
    expect(violations).toEqual([]);
  });
});
