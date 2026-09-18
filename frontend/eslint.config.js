import js from "@eslint/js";
import i18next from "eslint-plugin-i18next";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

/**
 * ESLint (flat config).
 *
 * The `i18next/no-literal-string` rule is the CI guard behind PROMPT.md 14.5: a
 * user-visible string added directly in JSX fails the build instead of shipping an
 * untranslated label. The `fa.ts` / `en.ts` resources are the only place where UI
 * copy may live.
 */
export default tseslint.config(
  { ignores: ["dist", "node_modules", "coverage"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks, i18next },
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { window: "readonly", document: "readonly", console: "readonly" },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "i18next/no-literal-string": [
        "error",
        {
          mode: "jsx-text-only",
          "jsx-attributes": {
            include: ["aria-label", "title", "placeholder", "alt"],
            exclude: ["className", "data-testid", "role", "type", "id", "dir", "lang", "to", "key", "href"],
          },
          message:
            "User-visible text must come from the i18n layer (src/i18n/fa.ts). See PROMPT.md 14.5.",
        },
      ],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    // Translation resources and tests contain literal strings by design.
    files: ["src/i18n/*.ts", "src/test/**", "**/*.test.{ts,tsx}"],
    rules: { "i18next/no-literal-string": "off" },
  },
);
