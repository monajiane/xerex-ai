/**
 * Makes translation keys type-safe: `t("title")` inside a namespace, or
 * `t("common:actions.save")` across namespaces, only compiles when the key exists
 * in `fa.ts`. A missing key is a build error rather than a runtime surprise.
 */
import type { FaResources } from "./fa";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: FaResources;
    returnNull: false;
    keySeparator: ".";
    nsSeparator: ":";
  }
}
