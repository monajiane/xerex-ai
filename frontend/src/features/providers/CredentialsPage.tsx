/**
 * Credentials module («اطلاعات احراز هویت»).
 *
 * Credentials always belong to a provider, so this page is a provider picker plus
 * the very same panel used on the provider detail page — one implementation, no
 * duplicated credential logic.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { CredentialsPanel } from "@/features/providers/CredentialsPanel";
import { providersApi } from "@/lib/api/endpoints";

export function CredentialsPage() {
  const { t } = useTranslation(["credentials", "common", "providers", "errors"]);
  const enums = useDynamicTranslation("enums");
  const [providerId, setProviderId] = useState("");

  const providersQuery = useQuery({
    queryKey: ["providers", "credentials-picker"],
    queryFn: ({ signal }) =>
      providersApi.list({ page: 1, page_size: 100, order_by: "name" }, signal),
  });

  const providers = providersQuery.data?.items ?? [];
  // Derived selection: the first provider is used until the administrator picks
  // another one — no effect, so no cascading render when the list arrives.
  const selectedId = providerId || providers[0]?.id || "";
  const selected = providers.find((provider) => provider.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("credentials:title")} description={t("credentials:subtitle")} />

      {providersQuery.isPending ? <LoadingState /> : null}
      {providersQuery.isError ? (
        <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />
      ) : null}

      {providersQuery.data && providers.length === 0 ? (
        <EmptyState
          title={t("credentials:noProviders")}
          action={
            <Link
              to="/providers"
              className="rounded-lg border border-brand-200 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:border-brand-800 dark:text-brand-200 dark:hover:bg-brand-900/40"
            >
              {t("providers:addProvider")}
            </Link>
          }
        />
      ) : null}

      {providers.length > 0 ? (
        <>
          <Card>
            <CardContent className="py-4">
              <Field
                label={t("credentials:selectProvider")}
                htmlFor="credentials-provider"
                hint={t("credentials:selectProviderHint")}
              >
                <Select
                  id="credentials-provider"
                  value={selectedId}
                  onChange={(event) => setProviderId(event.target.value)}
                >
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name} — {provider.kind}
                    </option>
                  ))}
                </Select>
              </Field>
              {selected ? (
                <p className="app-muted mt-3 flex flex-wrap items-center gap-2 text-[0.6875rem]">
                  <span>
                    {t("providers:detail.baseUrl")}: <Ltr mono>{selected.base_url}</Ltr>
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>
                    {enums.t(`providerKind.${selected.kind}`, { defaultValue: selected.kind })}
                  </span>
                  <span aria-hidden="true">·</span>
                  <Link to={`/providers/${selected.id}`} className="hover:underline">
                    {t("providers:detail.title")}
                  </Link>
                </p>
              ) : null}
            </CardContent>
          </Card>

          {selected ? <CredentialsPanel provider={selected} /> : null}
        </>
      ) : null}
    </div>
  );
}

export default CredentialsPage;
