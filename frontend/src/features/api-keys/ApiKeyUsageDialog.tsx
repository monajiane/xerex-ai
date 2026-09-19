/**
 * Consumption of one key («مصرف کلید»).
 *
 * Numbers come from the per-attempt usage records, so the dialog can honestly show
 * requests, tokens, cost and error count even when the key has never received a
 * successful upstream answer.
 */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Dialog } from "@/components/ui/dialog";
import { ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { apiKeysApi } from "@/lib/api/endpoints";
import type { ApiKey } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

export interface ApiKeyUsageDialogProps {
  apiKey: ApiKey | null;
  onClose: () => void;
}

export function ApiKeyUsageDialog({ apiKey, onClose }: ApiKeyUsageDialogProps) {
  const { t } = useTranslation(["apiKeys", "common"]);
  const { n, digits, cost, dateTime, relative } = useLocale();

  const usageQuery = useQuery({
    queryKey: ["api-key-usage", apiKey?.id],
    queryFn: ({ signal }) => apiKeysApi.usage(apiKey!.id, signal),
    enabled: apiKey !== null,
  });

  const rows = usageQuery.data
    ? [
        { label: t("apiKeys:usage.requests"), value: digits(usageQuery.data.requests) },
        { label: t("apiKeys:usage.inputTokens"), value: digits(usageQuery.data.input_tokens) },
        { label: t("apiKeys:usage.outputTokens"), value: digits(usageQuery.data.output_tokens) },
        { label: t("apiKeys:usage.totalTokens"), value: digits(usageQuery.data.total_tokens) },
        { label: t("apiKeys:usage.cost"), value: cost(usageQuery.data.cost) },
        { label: t("apiKeys:usage.errors"), value: digits(usageQuery.data.error_count) },
      ]
    : [];

  return (
    <Dialog
      open={apiKey !== null}
      onClose={onClose}
      title={t("apiKeys:usage.title")}
      description={apiKey?.name}
      footer={null}
    >
      {usageQuery.isPending ? (
        <LoadingState />
      ) : usageQuery.isError ? (
        <ErrorState error={usageQuery.error} onRetry={() => void usageQuery.refetch()} />
      ) : usageQuery.data ? (
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            {rows.map((row) => (
              <div key={row.label} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <dt className="text-xs text-slate-500 dark:text-slate-400">{row.label}</dt>
                <dd className="mt-1 font-semibold">
                  <Ltr>{row.value}</Ltr>
                </dd>
              </div>
            ))}
          </dl>

          <div className="flex flex-col gap-1 text-sm">
            {usageQuery.data.quota_tokens === null ? (
              <span className="text-slate-500 dark:text-slate-400">{t("apiKeys:usage.noQuota")}</span>
            ) : (
              <span>
                {t("apiKeys:usage.remaining")}:{" "}
                <Ltr className="font-semibold">
                  {n(usageQuery.data.quota_remaining_tokens ?? 0)}
                </Ltr>{" "}
                / <Ltr>{n(usageQuery.data.quota_tokens)}</Ltr>
              </span>
            )}
            <span className="text-slate-500 dark:text-slate-400">
              {t("apiKeys:table.lastUsed")}:{" "}
              {usageQuery.data.last_used_at
                ? `${relative(usageQuery.data.last_used_at)} — ${dateTime(usageQuery.data.last_used_at)}`
                : t("common:time.never")}
            </span>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-900">
            <p className="font-medium">{t("apiKeys:intro.title")}</p>
            <p className="mt-1 text-slate-600 dark:text-slate-300">{t("apiKeys:intro.hint")}</p>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              <span>{t("apiKeys:intro.baseUrl")}:</span>
              <Ltr className="font-mono">
                {typeof window === "undefined" ? "/v1" : `${window.location.origin}/v1`}
              </Ltr>
            </p>
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}

export default ApiKeyUsageDialog;
