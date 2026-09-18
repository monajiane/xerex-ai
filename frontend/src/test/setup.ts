/** Vitest setup: jest-dom matchers and a Persian-first i18n instance. */
import "@testing-library/jest-dom/vitest";

import "@/i18n";
import { applyDocumentLocale } from "@/i18n";

applyDocumentLocale("fa");
