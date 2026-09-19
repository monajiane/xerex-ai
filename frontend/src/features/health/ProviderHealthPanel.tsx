/**
 * Upstream health («بررسی سلامت» — provider level, M5).
 *
 * What is shown is what was observed: the last stored check per provider, the observed
 * latency, the 24-hour error rate and uptime computed from the stored observations. A
 * provider that was never checked reads «نامشخص» — the panel never invents a healthy
 * status to fill a table cell.
 */
import { useState } from "react";
import { Activity, ListChecks } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrapper,
} from "@/components/ui/table";
import { useToastHelpers } from "@/components/ui/toast";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth } from "@/features/auth/AuthProvider";
import { healthApi } from "@/lib/api/endpoints";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function ProviderHealthPanel() {
  const { t } = useTranslation(["health", "providers", "common", "errors"]);
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const { digits, duration, relative, dateTime, pct } = useLocale();

  const canRunChecks = isRole("owner", "admin", "operator");
  const [historyProvider, setHistoryProvider] = useState("");

  const providersQuery = useQuery({
    queryKey: ["health", "providers"],
    queryFn: ({ signal }) => healthApi.providers(signal),
    refetchInterval: 60_000,
  });
  const historyQuery = useQuery({
    queryKey: ["health", "observations", historyProvider],
    queryFn: ({ signal }) =>
      healthApi.observations(
        { provider_id: historyProvider || undefined, limit: 25 },
        signal,
      ),
  });

  const runMutation = useMutation({
    mutationFn: () => healthApi.run(),
    onSuccess: async (result) => {
      const failed = result.checked - (result.statuses.healthy ?? 0);
      toast.success(
        `${t("health:run.done", { checked: digits(result.checked) })}` +
          (failed > 0 ? ` — ${t("health:run.withFailures", { failed: digits(failed) })}` : ""),
      );
      await queryClient.invalidateQueries({ queryKey: ["health"] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const rows = providersQuery.data ?? [];
  const observations = historyQuery.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <div className="text-start">
            <CardTitle className="flex items-center gap-2">
              <Activity aria-hidden="true" className="size-4" />
              {t("health:providers.title")}
            </CardTitle>
            <CardDescription>{t("health:providers.subtitle")}</CardDescription>
          </div>
          {canRunChecks ? (
            <Button
              size="sm"
              variant="secondary"
              loading={runMutation.isPending}
              onClick={() => runMutation.mutate()}
            >
              <ListChecks aria-hidden="true" />
              {t("health:run.button")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="px-0 py-0">
          {providersQuery.isPending ? (
            <div className="p-4">
              <LoadingState />
            </div>
          ) : providersQuery.isError ? (
            <div className="p-4">
              <ErrorState
                error={providersQuery.error}
                onRetry={() => void providersQuery.refetch()}
              />
            </div>
          ) : rows.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title={t("health:providers.empty")}
                hint={t("health:providers.emptyHint")}
              />
            </div>
          ) : (
            <TableWrapper className="rounded-none border-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("providers:table.name")}</TableHead>
                    <TableHead>{t("common:status.label")}</TableHead>
                    <TableHead>{t("health:lastCheck")}</TableHead>
                    <TableHead>{t("health:latency")}</TableHead>
                    <TableHead>{t("health:providers.errorRate")}</TableHead>
                    <TableHead>{t("health:providers.requests")}</TableHead>
                    <TableHead>{t("health:uptime")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.provider_id}>
                      <TableCell>
                        <span className="flex flex-col">
                          <span className="font-medium">{row.name}</span>
                          <Ltr className="font-mono text-xs text-slate-500 dark:text-slate-400">
                            {row.slug}
                          </Ltr>
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="flex flex-col gap-1">
                          <StatusBadge domain="healthStatus" value={row.status} showRawValue />
                          {row.error_code ? (
                            <Ltr className="font-mono text-[0.625rem] text-rose-600 dark:text-rose-400">
                              {row.error_code}
                            </Ltr>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs">
                        {row.last_checked_at ? (
                          <span className="flex flex-col">
                            <span>{relative(row.last_checked_at)}</span>
                            <Ltr className="app-muted font-mono text-[0.625rem]">
                              {dateTime(row.last_checked_at)}
                            </Ltr>
                          </span>
                        ) : (
                          <span className="text-slate-500 dark:text-slate-400">
                            {t("common:time.never")}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Ltr className="font-mono text-xs">
                          {row.latency_ms === null
                            ? t("common:notAvailable")
                            : duration(row.latency_ms)}
                        </Ltr>
                      </TableCell>
                      <TableCell>
                        <Ltr className="font-mono text-xs">{pct(row.error_rate * 100)}</Ltr>
                      </TableCell>
                      <TableCell>
                        <Ltr className="font-mono text-xs">{digits(row.requests)}</Ltr>
                      </TableCell>
                      <TableCell>
                        {row.uptime_percent === null ? (
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {t("common:notAvailable")}
                          </span>
                        ) : (
                          <Ltr className="font-mono text-xs">{pct(row.uptime_percent)}</Ltr>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrapper>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-start">
            <CardTitle>{t("health:history.title")}</CardTitle>
            <CardDescription>{t("health:history.subtitle")}</CardDescription>
          </div>
          <Select
            aria-label={t("health:history.filter")}
            className="max-w-48"
            value={historyProvider}
            onChange={(event) => setHistoryProvider(event.target.value)}
          >
            <option value="">{t("health:history.allProviders")}</option>
            {rows.map((row) => (
              <option key={row.provider_id} value={row.provider_id}>
                {row.name}
              </option>
            ))}
          </Select>
        </CardHeader>
        <CardContent>
          {historyQuery.isPending ? (
            <LoadingState />
          ) : historyQuery.isError ? (
            <ErrorState error={historyQuery.error} onRetry={() => void historyQuery.refetch()} />
          ) : observations.length === 0 ? (
            <EmptyState title={t("health:history.empty")} hint={t("health:history.emptyHint")} />
          ) : (
            <ul className="flex flex-col gap-2">
              {observations.map((observation) => (
                <li
                  key={observation.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700"
                >
                  <span className="flex items-center gap-2">
                    <StatusBadge domain="healthStatus" value={observation.status} />
                    <Badge tone="neutral">{observation.target_type}</Badge>
                    {observation.error_code ? (
                      <Ltr className="font-mono text-xs text-slate-500 dark:text-slate-400">
                        {observation.error_code}
                      </Ltr>
                    ) : null}
                  </span>
                  <span className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                    {observation.latency_ms === null ? null : (
                      <Ltr className="font-mono">{duration(observation.latency_ms)}</Ltr>
                    )}
                    <Ltr className="font-mono">{dateTime(observation.checked_at)}</Ltr>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ProviderHealthPanel;
