/**
 * System health.
 *
 * Live data from `GET /api/v1/health`: component statuses, latency and versions.
 * Status values stay English in the API and are rendered with Persian labels here.
 */
import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrapper,
} from "@/components/ui/table";
import { ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { systemApi } from "@/lib/api/endpoints";
import { useSystemInfo } from "@/lib/api/useCapabilities";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function HealthPage() {
  const { t } = useTranslation(["health", "common"]);
  const healthNs = useDynamicTranslation("health");
  const { dateTime, duration, relative, uptime, n, timezone } = useLocale();

  const healthQuery = useQuery({
    queryKey: ["system", "health"],
    queryFn: ({ signal }) => systemApi.health(signal),
    refetchInterval: 30_000,
  });
  const infoQuery = useSystemInfo();

  const health = healthQuery.data;
  const status = health?.status ?? "unknown";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("health:title")}
        description={t("health:subtitle")}
        badge={<StatusBadge domain="healthStatus" value={status} showRawValue />}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void healthQuery.refetch()}
            loading={healthQuery.isFetching}
          >
            <RefreshCw aria-hidden="true" />
            {t("health:checkNow")}
          </Button>
        }
      />

      {status === "degraded" ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          {t("health:degradedHint")}
        </p>
      ) : null}
      {status === "down" ? (
        <p
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs leading-relaxed text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100"
        >
          {t("health:downtimeHint")}
        </p>
      ) : null}

      {healthQuery.isPending ? <LoadingState /> : null}
      {healthQuery.isError ? (
        <ErrorState error={healthQuery.error} onRetry={() => void healthQuery.refetch()} />
      ) : null}

      {health ? (
        <Card>
          <CardHeader>
            <div className="text-start">
              <CardTitle>{t("health:components")}</CardTitle>
              <CardDescription>
                {t("health:checkedAt")}: <Ltr mono>{dateTime(health.checked_at)}</Ltr> ·{" "}
                {t("health:lastCheck")}: <Ltr mono>{relative(health.checked_at)}</Ltr>
              </CardDescription>
            </div>
            <Badge tone="neutral">
              <span>{t("health:runtime")}</span>
              <Ltr mono>{uptime(health.uptime_seconds)}</Ltr>
            </Badge>
          </CardHeader>
          <CardContent className="px-0 py-0">
            <TableWrapper className="rounded-none border-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("health:component")}</TableHead>
                    <TableHead>{t("common:status.label")}</TableHead>
                    <TableHead>{t("health:latency")}</TableHead>
                    <TableHead>{t("health:version")}</TableHead>
                    <TableHead>{t("health:required")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {health.components.map((component) => (
                    <TableRow key={component.name}>
                      <TableCell className="font-medium">
                        {healthNs.exists(`componentNames.${component.name}`) ? (
                          healthNs.t(`componentNames.${component.name}`)
                        ) : (
                          <Ltr mono>{component.name}</Ltr>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge domain="healthStatus" value={component.status} showRawValue />
                      </TableCell>
                      <TableCell>
                        {component.latency_ms === null ? (
                          <span className="app-muted">—</span>
                        ) : (
                          duration(component.latency_ms)
                        )}
                      </TableCell>
                      <TableCell>
                        <Ltr mono className="text-xs">
                          {component.version ?? "—"}
                        </Ltr>
                      </TableCell>
                      <TableCell>
                        {component.required === null ? (
                          <span className="app-muted">—</span>
                        ) : component.required ? (
                          <Badge tone="brand">{t("health:required")}</Badge>
                        ) : (
                          <Badge tone="neutral">{t("health:optional")}</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrapper>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("health:serviceInfo")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-xs">
            <InfoRow label={t("common:build.version")} value={infoQuery.data?.version ?? "—"} />
            <InfoRow
              label={t("health:milestones.milestone")}
              value={infoQuery.data?.milestone ?? "—"}
            />
            <InfoRow
              label={t("health:milestones.environment")}
              value={infoQuery.data?.environment ?? "—"}
            />
            <InfoRow
              label={t("health:milestones.startedAt")}
              value={infoQuery.data ? dateTime(infoQuery.data.started_at) : "—"}
            />
            <InfoRow
              label={t("health:runtime")}
              value={infoQuery.data ? uptime(infoQuery.data.uptime_seconds) : "—"}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-start">
              <CardTitle>{t("common:language.label")}</CardTitle>
              <CardDescription>{t("health:monitoringNote")}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-xs">
            <InfoRow
              label={t("health:componentNames.api")}
              value={infoQuery.data?.api_version ?? "v1"}
            />
            <InfoRow
              label={t("common:language.fa")}
              value={infoQuery.data?.localization.default_locale ?? "fa"}
            />
            <InfoRow
              label={t("common:language.label")}
              value={n(infoQuery.data?.localization.supported_locales.length ?? 0)}
            />
            <InfoRow label={t("common:build.serverTime")} value={timezone} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b app-divide pb-2 last:border-0">
      <span className="app-muted">{label}</span>
      <Ltr mono>{value}</Ltr>
    </div>
  );
}

export default HealthPage;
