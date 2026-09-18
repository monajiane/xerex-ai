/**
 * Escapes hatch for keys that only exist at runtime.
 *
 * Most UI copy uses statically typed keys (`t("title")`) — a missing key is then a
 * compile error. Some values, however, arrive from the API as stable English
 * *values* and have to be looked up dynamically: error codes, enum values
 * (`healthy`, `owner`, `login_failed`) and roadmap module keys.
 *
 * `useDynamicTranslation` keeps those lookups honest: it falls back to the
 * provided default (or the raw value) instead of rendering a raw key path.
 */
import { useCallback } from "react";
import { useTranslation } from "react-i18next";

export interface DynamicTranslation {
  /** Translate a runtime key; `defaultValue` is returned when the key is missing. */
  t: (key: string, options?: { defaultValue?: string; [key: string]: unknown }) => string;
  exists: (key: string) => boolean;
}

export function useDynamicTranslation(namespace: string): DynamicTranslation {
  // The namespace name is dynamic on purpose, so the typed overload is bypassed.
  const { t, i18n } = useTranslation(namespace as never);

  const exists = useCallback((key: string) => i18n.exists(`${namespace}:${key}`), [i18n, namespace]);

  const translate = useCallback(
    (key: string, options?: { defaultValue?: string; [key: string]: unknown }) => {
      if (!exists(key)) return options?.defaultValue ?? "";
      const raw = (t as unknown as (k: string, o?: Record<string, unknown>) => unknown)(key, {
        ...options,
        defaultValue: options?.defaultValue ?? key,
      });
      return typeof raw === "string" ? raw : String(raw ?? "");
    },
    [exists, t],
  );

  return { t: translate, exists };
}
