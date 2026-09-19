/**
 * «مصرف» — usage analytics (M6).
 *
 * Persian-first rules honoured here:
 *  - the date filter is Jalali (`۱۴۰۵/۰۶/۲۸`), while the API contract stays ISO-8601;
 *  - numbers in the metric cards are Persian where they are human-readable, and Latin
 *    inside technical containers (request ids, model names, percentages of codes);
 *  - every export goes through the authenticated transport, never a bare link.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
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
import { PageHeader } from "@/components/common/PageHeader";
import { apiKeysApi, modelsApi, providersApi, usageApi } from "@/lib/api/endpoints";
import type {
  ApiKey,
  Model,
  Provider,
  UsageDimension,
  UsageFilterParams,
  UsageInterval,
} from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";
import { formatJalali, parseJalaliInput, toJalaliInput } from "@/lib/locale/jalali";
import { useAuth } from "@/features/auth/AuthProvider";

interface RangeInput {
  from: string;
  to: string;
}

function isoRange(range: RangeInput): { params: UsageFilterParams; invalid: boolean } {
  const from = range.from.trim() ? parseJalaliInput(range.from) : null;
  const to = range.to.trim() ? parseJalaliInput(range.to) : null;
  const invalid = (range.from.trim() !== "" && from === null) || (range.to.trim() !== "" && to === null);
  return {
    params: {
      date_from: from ?? undefined,
      date_to: to ?? undefined,
    },
    invalid,
  };
}

function presetRange(days: number): RangeInput {
  const end = new Date();
  const start = new Date(end.getTime() - (days - 1) * 24 * 60 * 60 * 1000);
  return { from: toJalaliInput(start.toISOString()), to: toJalaliInput(end.toISOString()) };
}

export function UsagePage() {
  const { t } = useTranslation(["usage", "common", "errors"]);
  const { n, pct, tech, cost, duration, dateTime } = useLocale();
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  const [range, setRange] = useState<RangeInput>(() => presetRange(7));
  const [applied, setApplied] = useState<RangeInput>(() => presetRange(7));
  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKeyId, setApiKeyId] = useState("");
  const [interval, setInterval] = useState<UsageInterval>("day");
  const [dimension, setDimension] = useState<UsageDimension>("provider");

  const canExport = isRole("owner", "admin", "operator", "viewer");
  const canRebuild = isRole("owner", "admin");

  // Validation follows what the administrator is typing; the queries follow what was
  // applied, so a half-typed date never triggers a request with a wrong window.
  const typed = useMemo(() => isoRange(range), [range]);
  const { params: iso } = useMemo(() => isoRange(applied), [applied]);
  const filters = useMemo(
    () => ({
      ...iso,
      provider_id: providerId || undefined,
      model_id: modelId || undefined,
      api_key_id: apiKeyId || undefined,
    }),
    [iso, providerId, modelId, apiKeyId],
  );
  const invalid = typed.invalid;

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", filters, interval],
    queryFn: ({ signal }) => usageApi.summary({ ...filters, interval }, signal),
  });

  const breakdownQuery = useQuery({
    queryKey: ["usage-breakdown", filters, dimension],
    queryFn: ({ signal }) => usageApi.breakdown({ ...filters, dimension }, signal),
  });

  const providersQuery = useQuery({
    queryKey: ["providers", "usage-filter"],
    queryFn: ({ signal }) => providersApi.list({ page_size: 100 }, signal),
  });

  const modelsQuery = useQuery({
    queryKey: ["models", "usage-filter", providerId],
    queryFn: ({ signal }) =>
      modelsApi.list({ page_size: 200, provider_id: providerId || undefined }, signal),
  });

  const apiKeysQuery = useQuery({
    queryKey: ["api-keys", "usage-filter"],
    queryFn: ({ signal }) => apiKeysApi.list({ page_size: 100 }, signal),
  });

  const exportMutation = useMutation({
    mutationFn: (format: "csv" | "json") => usageApi.export(format, filters),
    onSuccess: (filename) => toast.success(t("usage:export.done", { name: filename })),
    onError: () => toast.error(t("usage:export.failed")),
  });

  const rollupMutation = useMutation({
    mutationFn: () => usageApi.rebuildRollups(),
    onSuccess: () => {
      toast.success(t("usage:export.rollupsDone"));
      void queryClient.invalidateQueries({ queryKey: ["usage-summary"] });
    },
  });

  const totals = summaryQuery.data?.totals;
  const points = summaryQuery.data?.series.points ?? [];
  const maxRequests = points.reduce((max, point) => Math.max(max, point.requests), 0);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("usage:title")} description={t("usage:subtitle")} />

      <Card>
        <CardHeader>
          <CardTitle>{t("usage:filters.title")}</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setRange(presetRange(1))}>
              {t("usage:filters.presetToday")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setRange(presetRange(7))}>
              {t("usage:filters.preset7")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setRange(presetRange(30))}>
              {t("usage:filters.preset30")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setRange(presetRange(90))}>
              {t("usage:filters.preset90")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="usage-from" className="text-xs font-medium">{t("usage:filters.from")}</label>
              <Input
                id="usage-from"
                value={range.from}
                invalid={invalid}
                inputMode="numeric"
                placeholder={t("usage:filters.datePlaceholder")}
                onChange={(event) => setRange({ ...range, from: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="usage-to" className="text-xs font-medium">{t("usage:filters.to")}</label>
              <Input
                id="usage-to"
                value={range.to}
                invalid={invalid}
                inputMode="numeric"
                placeholder={t("usage:filters.datePlaceholder")}
                onChange={(event) => setRange({ ...range, to: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="usage-provider" className="text-xs font-medium">{t("usage:filters.provider")}</label>
              <Select
                id="usage-provider"
                value={providerId}
                onChange={(event) => {
                  setProviderId(event.target.value);
                  setModelId("");
                }}
              >
                <option value="">{t("usage:filters.all")}</option>
                {(providersQuery.data?.items ?? []).map((provider: Provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="usage-model" className="text-xs font-medium">{t("usage:filters.model")}</label>
              <Select
                id="usage-model"
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
              >
                <option value="">{t("usage:filters.all")}</option>
                {(modelsQuery.data?.items ?? []).map((model: Model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="usage-api-key" className="text-xs font-medium">{t("usage:filters.apiKey")}</label>
              <Select
                id="usage-api-key"
                value={apiKeyId}
                onChange={(event) => setApiKeyId(event.target.value)}
              >
                <option value="">{t("usage:filters.all")}</option>
                {(apiKeysQuery.data?.items ?? []).map((key: ApiKey) => (
                  <option key={key.id} value={key.id}>
                    {key.name}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {invalid ? (
            <p className="text-xs text-rose-600 dark:text-rose-400" role="alert">
              {t("usage:filters.invalidDate")}
            </p>
          ) : null}
          <p className="app-muted text-xs">{t("usage:filters.hint")}</p>

          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={invalid} onClick={() => setApplied(range)}>
              {t("usage:filters.apply")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                const empty = { from: "", to: "" };
                setRange(empty);
                setApplied(empty);
                setProviderId("");
                setModelId("");
                setApiKeyId("");
              }}
            >
              {t("usage:filters.reset")}
            </Button>
            <div className="ms-auto flex flex-wrap items-center gap-2">
              <label className="app-muted flex items-center gap-2 text-xs" htmlFor="usage-interval">
                {t("usage:filters.interval")}
              </label>
              <Select
                id="usage-interval"
                className="w-32"
                value={interval}
                onChange={(event) => setInterval(event.target.value as UsageInterval)}
              >
                <option value="hour">{t("usage:filters.intervalHour")}</option>
                <option value="day">{t("usage:filters.intervalDay")}</option>
                <option value="week">{t("usage:filters.intervalWeek")}</option>
                <option value="month">{t("usage:filters.intervalMonth")}</option>
              </Select>
            </div>
          </div>

          {applied.from || applied.to ? (
            <p className="app-muted text-xs">
              {t("usage:filters.activeRange", {
                range: `${formatJalali(iso.date_from ?? undefined)} — ${formatJalali(
                  iso.date_to ?? undefined,
                )}`,
              })}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {summaryQuery.isPending ? <LoadingState /> : null}
      {summaryQuery.isError ? (
        <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />
      ) : null}

      {totals && summaryQuery.data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label={t("usage:totals.requests")}
              value={n(totals.requests)}
              hint={t("usage:totals.requestsHint")}
            />
            <MetricCard
              label={t("usage:totals.tokens")}
              value={n(totals.total_tokens)}
              hint={`${t("usage:totals.inputTokens")}: ${n(totals.input_tokens)} • ${t(
                "usage:totals.outputTokens",
              )}: ${n(totals.output_tokens)}`}
            />
            <MetricCard
              label={t("usage:totals.latency")}
              value={duration(totals.avg_latency_ms ?? 0)}
              hint={`${t("usage:totals.p95")}: ${duration(totals.p95_latency_ms)}`}
            />
            <MetricCard
              label={t("usage:totals.cost")}
              value={cost(totals.cost)}
              hint={`${t("usage:totals.errors")}: ${n(totals.error_count)} • ${t(
                "usage:totals.errorRate",
              )}: ${pct(totals.error_rate)}`}
              tone={totals.error_count > 0 ? "warning" : "default"}
            />
          </div>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>{t("usage:series.title")}</CardTitle>
                <p className="app-muted mt-1 text-xs">{t("usage:series.subtitle")}</p>
              </div>
              <p className="app-muted text-xs">
                {t("usage:states.generatedAt", { time: dateTime(summaryQuery.data.generated_at) })}
              </p>
            </CardHeader>
            <CardContent className="px-0 py-0">
              {points.length === 0 ? (
                <div className="p-6">
                  <EmptyState
                    title={t("usage:series.empty")}
                    hint={t("usage:states.noActivityHint")}
                  />
                </div>
              ) : (
                <TableWrapper className="rounded-none border-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("usage:series.bucket")}</TableHead>
                        <TableHead>{t("usage:series.requests")}</TableHead>
                        <TableHead>{t("usage:series.tokens")}</TableHead>
                        <TableHead>{t("usage:series.cost")}</TableHead>
                        <TableHead>{t("usage:series.latency")}</TableHead>
                        <TableHead>{t("usage:series.errors")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {points.map((point) => (
                        <TableRow key={point.bucket}>
                          <TableCell className="whitespace-nowrap text-xs">
                            {dateTime(point.bucket)}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>{n(point.requests)}</span>
                              <span
                                aria-hidden
                                className="bg-brand-500/70 h-1.5 rounded-full"
                                style={{
                                  width: `${maxRequests ? Math.max(4, (point.requests / maxRequests) * 72) : 0}px`,
                                }}
                              />
                            </div>
                          </TableCell>
                          <TableCell>{n(point.tokens)}</TableCell>
                          <TableCell>{cost(point.cost)}</TableCell>
                          <TableCell>{duration(point.avg_latency_ms)}</TableCell>
                          <TableCell className="text-xs">{pct(point.error_rate)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableWrapper>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}

      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("usage:breakdown.title")}</CardTitle>
            <p className="app-muted mt-1 text-xs">{t("usage:breakdown.subtitle")}</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="app-muted text-xs" htmlFor="usage-dimension">
              {t("usage:breakdown.dimension")}
            </label>
            <Select
              id="usage-dimension"
              className="w-36"
              value={dimension}
              onChange={(event) => setDimension(event.target.value as UsageDimension)}
            >
              <option value="provider">{t("usage:breakdown.byProvider")}</option>
              <option value="model">{t("usage:breakdown.byModel")}</option>
              <option value="api_key">{t("usage:breakdown.byKey")}</option>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="px-0 py-0">
          {breakdownQuery.isPending ? (
            <div className="p-6">
              <LoadingState />
            </div>
          ) : null}
          {breakdownQuery.isError ? (
            <div className="p-6">
              <ErrorState
                error={breakdownQuery.error}
                onRetry={() => void breakdownQuery.refetch()}
              />
            </div>
          ) : null}
          {breakdownQuery.data ? (
            breakdownQuery.data.items.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title={t("usage:breakdown.empty")}
                  hint={t("usage:breakdown.emptyHint")}
                />
              </div>
            ) : (
              <TableWrapper className="rounded-none border-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("usage:breakdown.label")}</TableHead>
                      <TableHead>{t("usage:breakdown.requests")}</TableHead>
                      <TableHead>{t("usage:breakdown.tokens")}</TableHead>
                      <TableHead>{t("usage:breakdown.cost")}</TableHead>
                      <TableHead>{t("usage:breakdown.latency")}</TableHead>
                      <TableHead>{t("usage:breakdown.errors")}</TableHead>
                      <TableHead>{t("usage:breakdown.errorRate")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {breakdownQuery.data.items.map((row) => (
                      <TableRow key={row.key}>
                        <TableCell>
                          <Ltr>{row.label}</Ltr>
                        </TableCell>
                        <TableCell>{n(row.requests)}</TableCell>
                        <TableCell>
                          {n(row.total_tokens)}
                          <span className="app-muted ms-2 text-xs">
                            {tech(row.input_tokens)} / {tech(row.output_tokens)}
                          </span>
                        </TableCell>
                        <TableCell>{cost(row.cost)}</TableCell>
                        <TableCell>{duration(row.avg_latency_ms ?? 0)}</TableCell>
                        <TableCell>
                          <Badge tone={row.errors > 0 ? "danger" : "neutral"}>
                            {n(row.errors)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">{pct(row.error_rate)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableWrapper>
            )
          ) : null}
        </CardContent>
      </Card>

      {canExport ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("usage:export.csv")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate("csv")}
            >
              {t("usage:export.csv")}
            </Button>
            <Button
              variant="outline"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate("json")}
            >
              {t("usage:export.json")}
            </Button>
            {canRebuild ? (
              <Button
                variant="ghost"
                disabled={rollupMutation.isPending}
                onClick={() => rollupMutation.mutate()}
                title={t("usage:export.rollupsHint")}
              >
                {t("usage:export.rollups")}
              </Button>
            ) : null}
            <p className="app-muted text-xs">
              {t("usage:export.csvHint")} {t("usage:export.jsonHint")}
            </p>
          </CardContent>
        </Card>
      ) : null}

      {summaryQuery.data ? (
        <p className="app-muted text-xs">
          {t("usage:states.rangeNote", {
            range: `${formatJalali(iso.date_from ?? summaryQuery.data!.range_start)} — ${formatJalali(
              iso.date_to ?? summaryQuery.data!.range_end,
            )}`,
          })}
        </p>
      ) : null}
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "warning";
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 pt-5">
        <span className="app-muted text-xs">{label}</span>
        <span
          className={
            tone === "warning"
              ? "text-xl font-semibold text-amber-600 dark:text-amber-400"
              : "text-xl font-semibold"
          }
        >
          {value}
        </span>
        {hint ? <span className="app-muted text-xs">{hint}</span> : null}
      </CardContent>
    </Card>
  );
}

export default UsagePage;
