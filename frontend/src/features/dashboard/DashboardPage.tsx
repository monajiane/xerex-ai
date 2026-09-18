/**
 * Dashboard.
 *
 * Every figure comes from the API and is read from the real database. While no
 * provider is connected the API returns honest zeros plus
 * `has_provider_data = false`, and the panel shows explicit empty states instead
 * of demo traffic (M1 brief: no fake provider/model data).
 */
import { Activity, AlertTriangle, Coins, Cpu, Gauge, KeyRound, Timer, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { dashboardApi } from "@/lib/api/endpoints";
import { useSystemInfo } from "@/lib/api/useCapabilities";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function DashboardPage() {
  const { t } = useTranslation(["dashboard", "common", "enums", "health"]);
  const { n, pct, tech, duration, cost, relative } = useLocale();

  const summaryQuery = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: ({ signal }) => dashboardApi.summary(signal),
    refetchInterval: 60_000,
  });

  const systemInfo = useSystemInfo();
  const summary = summaryQuery.data;
  const metrics = new Map((summary?.metrics ?? []).map((metric) => [metric.key, metric]));

  const window = summary?.window ?? "24h";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("dashboard:title")}
        description={t("dashboard:subtitle", { window })}
        actions={
          <Badge tone="neutral">
            <Ltr mono>{summary?.system_status ?? "—"}</Ltr>
          </Badge>
        }
      />

      {summaryQuery.isPending ? <LoadingState /> : null}
      {summaryQuery.isError ? (
        <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />
      ) : null}

      {summary ? (
        <>
          <section aria-label={t("dashboard:sectionKpi")} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard
              label={t("dashboard:kpi.requests")}
              value={n(metrics.get("requests")?.value ?? 0)}
              technicalValue={tech(metrics.get("requests")?.value ?? 0)}
              icon={Activity}
            />
            <StatCard
              label={t("dashboard:kpi.tokens")}
              value={n(metrics.get("tokens")?.value ?? 0)}
              technicalValue={tech(metrics.get("tokens")?.value ?? 0)}
              icon={Cpu}
            />
            <StatCard
              label={t("dashboard:kpi.cost")}
              value={cost(metrics.get("cost")?.value ?? 0)}
              icon={Coins}
            />
            <StatCard
              label={t("dashboard:kpi.p95Latency")}
              value={duration(metrics.get("p95_latency_ms")?.value ?? 0)}
              available={metrics.get("p95_latency_ms")?.available ?? false}
              emptyLabel={t("dashboard:kpi.noSamples")}
              icon={Timer}
            />
            <StatCard
              label={t("dashboard:kpi.errorRate")}
              value={pct(metrics.get("error_rate")?.value ?? 0)}
              available={metrics.get("error_rate")?.available ?? false}
              emptyLabel={t("dashboard:kpi.noSamples")}
              icon={AlertTriangle}
            />
            <StatCard
              label={t("dashboard:kpi.activeProviders")}
              value={n(metrics.get("active_providers")?.value ?? 0)}
              icon={Gauge}
            />
          </section>

          <section className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="text-start">
                  <CardTitle>{t("dashboard:sectionProviderHealth")}</CardTitle>
                  <CardDescription>{t("dashboard:honestyNote")}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {summary.provider_health.length === 0 ? (
                  <EmptyState
                    title={t("dashboard:empty.providers")}
                    hint={t("dashboard:empty.providersHint")}
                  />
                ) : (
                  <ul className="flex flex-col divide-y app-divide">
                    {summary.provider_health.map((row) => (
                      <li key={row.provider_id} className="flex items-center justify-between gap-3 py-2">
                        <span className="flex items-center gap-2">
                          <StatusBadge domain="healthStatus" value={row.status} />
                          <span className="text-sm">{row.name}</span>
                        </span>
                        <span className="app-muted text-xs">{relative(row.checked_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="text-start">
                  <CardTitle>{t("dashboard:sectionPlatformState")}</CardTitle>
                  <CardDescription>
                    {t("common:build.milestoneValue", {
                      milestone: systemInfo.data?.milestone ?? "M1",
                    })}
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <PlatformRow
                  icon={Users}
                  label={t("dashboard:platform.adminUsers")}
                  value={tech(summary.counts.admin_users ?? 0)}
                />
                <PlatformRow
                  icon={KeyRound}
                  label={t("dashboard:platform.apiKeys")}
                  value={tech(summary.counts.api_keys ?? 0)}
                />
                <PlatformRow
                  icon={Gauge}
                  label={t("dashboard:platform.providers")}
                  value={tech(summary.counts.providers ?? 0)}
                />
                <PlatformRow
                  icon={Cpu}
                  label={t("dashboard:platform.models")}
                  value={tech(summary.counts.models ?? 0)}
                />
              </CardContent>
            </Card>
          </section>

          <Card>
            <CardHeader>
              <div className="text-start">
                <CardTitle>{t("dashboard:sectionTopModels")}</CardTitle>
                <CardDescription>{t("dashboard:empty.usageHint")}</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {summary.top_models.length === 0 ? (
                <EmptyState
                  title={t("dashboard:empty.usage")}
                  hint={t("dashboard:empty.usageHint")}
                />
              ) : (
                <ul className="flex flex-col divide-y app-divide">
                  {summary.top_models.map((row) => (
                    <li key={`${row.model_name}-${row.provider_name}`} className="flex items-center justify-between gap-3 py-2">
                      <span className="flex items-center gap-2">
                        <Ltr mono className="text-sm">
                          {row.model_name}
                        </Ltr>
                        <Badge tone="neutral">
                          <Ltr mono>{row.provider_name}</Ltr>
                        </Badge>
                      </span>
                      <span className="app-muted text-xs">
                        <Ltr mono>{tech(row.requests)}</Ltr> {t("common:units.requests")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function PlatformRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border app-divide px-3 py-2">
      <span className="flex items-center gap-2 text-xs">
        <Icon className="size-3.5 app-muted" aria-hidden="true" />
        {label}
      </span>
      <Ltr mono className="text-sm font-semibold">
        {value}
      </Ltr>
    </div>
  );
}

export default DashboardPage;
