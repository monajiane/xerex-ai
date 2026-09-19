/**
 * «گزارش درخواست‌ها» — request logs (M6).
 *
 * One row per client request; the detail view lists every upstream attempt so an
 * administrator can see what failover actually did. Technical values (request id,
 * provider/model names, endpoint path, error codes) are always inside LTR islands so
 * Persian text cannot corrupt them (PROMPT.md 14.4).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
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
import { CodeBlock } from "@/components/common/CodeBlock";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { modelsApi, providersApi, usageApi } from "@/lib/api/endpoints";
import type { Model, Provider, RequestLogEntry, RequestLogState } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";
import { parseJalaliInput, toJalaliInput } from "@/lib/locale/jalali";

const PAGE_SIZE = 20;

interface Filters {
  search: string;
  state: "" | RequestLogState;
  errorCode: string;
  from: string;
  to: string;
  providerId: string;
  modelId: string;
}

function defaultFilters(): Filters {
  return {
    search: "",
    state: "",
    errorCode: "",
    from: toJalaliInput(new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString()),
    to: toJalaliInput(new Date().toISOString()),
    providerId: "",
    modelId: "",
  };
}

export function RequestLogsPage() {
  const { t } = useTranslation(["logs", "common", "errors"]);
  const { n, tech, duration, dateTime, relative } = useLocale();

  const [draft, setDraft] = useState<Filters>(defaultFilters);
  const [applied, setApplied] = useState<Filters>(defaultFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<RequestLogEntry | null>(null);

  const fromIso = draft.from.trim() ? parseJalaliInput(draft.from) : null;
  const toIso = draft.to.trim() ? parseJalaliInput(draft.to) : null;
  const invalidRange =
    (draft.from.trim() !== "" && fromIso === null) || (draft.to.trim() !== "" && toIso === null);

  const appliedFrom = applied.from.trim() ? parseJalaliInput(applied.from) : null;
  const appliedTo = applied.to.trim() ? parseJalaliInput(applied.to) : null;

  const logsQuery = useQuery({
    queryKey: ["request-logs", applied, page],
    queryFn: ({ signal }) =>
      usageApi.requests(
        {
          date_from: appliedFrom ?? undefined,
          date_to: appliedTo ?? undefined,
          provider_id: applied.providerId || undefined,
          model_id: applied.modelId || undefined,
          state: applied.state || undefined,
          error_code: applied.errorCode.trim() || undefined,
          search: applied.search.trim() || undefined,
          page,
          page_size: PAGE_SIZE,
        },
        signal,
      ),
  });

  const providersQuery = useQuery({
    queryKey: ["providers", "logs-filter"],
    queryFn: ({ signal }) => providersApi.list({ page_size: 100 }, signal),
  });

  const modelsQuery = useQuery({
    queryKey: ["models", "logs-filter", draft.providerId],
    queryFn: ({ signal }) =>
      modelsApi.list({ page_size: 200, provider_id: draft.providerId || undefined }, signal),
  });

  const detailQuery = useQuery({
    queryKey: ["request-log-detail", selected?.request_id],
    queryFn: ({ signal }) => usageApi.request(selected!.request_id, signal),
    enabled: selected !== null,
  });

  const totalPages = logsQuery.data ? Math.max(1, Math.ceil(logsQuery.data.total / PAGE_SIZE)) : 1;

  const stateTone = (state: RequestLogState) =>
    state === "succeeded" ? "success" : state === "failed" ? "danger" : "warning";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("logs:title")} description={t("logs:subtitle")} />

      <Card>
        <CardHeader>
          <CardTitle>{t("logs:filters.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-search" className="text-xs font-medium">
                {t("logs:filters.search")}
              </label>
              <Input
                id="logs-search"
                value={draft.search}
                placeholder={t("logs:filters.searchPlaceholder")}
                onChange={(event) => setDraft({ ...draft, search: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-state" className="text-xs font-medium">
                {t("logs:filters.state")}
              </label>
              <Select
                id="logs-state"
                value={draft.state}
                onChange={(event) =>
                  setDraft({ ...draft, state: event.target.value as Filters["state"] })
                }
              >
                <option value="">{t("logs:filters.allStates")}</option>
                <option value="succeeded">{t("logs:state.succeeded")}</option>
                <option value="failed">{t("logs:state.failed")}</option>
                <option value="pending">{t("logs:state.pending")}</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-error-code" className="text-xs font-medium">
                {t("logs:filters.errorCode")}
              </label>
              <Input
                id="logs-error-code"
                technical
                value={draft.errorCode}
                placeholder={t("logs:filters.errorCodePlaceholder")}
                onChange={(event) => setDraft({ ...draft, errorCode: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-from" className="text-xs font-medium">
                {t("logs:filters.dateFrom")}
              </label>
              <Input
                id="logs-from"
                value={draft.from}
                invalid={invalidRange}
                inputMode="numeric"
                placeholder={t("logs:filters.datePlaceholder")}
                onChange={(event) => setDraft({ ...draft, from: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-to" className="text-xs font-medium">
                {t("logs:filters.dateTo")}
              </label>
              <Input
                id="logs-to"
                value={draft.to}
                invalid={invalidRange}
                inputMode="numeric"
                placeholder={t("logs:filters.datePlaceholder")}
                onChange={(event) => setDraft({ ...draft, to: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-provider" className="text-xs font-medium">
                {t("logs:filters.provider")}
              </label>
              <Select
                id="logs-provider"
                value={draft.providerId}
                onChange={(event) =>
                  setDraft({ ...draft, providerId: event.target.value, modelId: "" })
                }
              >
                <option value="">{t("logs:filters.all")}</option>
                {(providersQuery.data?.items ?? []).map((provider: Provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="logs-model" className="text-xs font-medium">
                {t("logs:filters.model")}
              </label>
              <Select
                id="logs-model"
                value={draft.modelId}
                onChange={(event) => setDraft({ ...draft, modelId: event.target.value })}
              >
                <option value="">{t("logs:filters.all")}</option>
                {(modelsQuery.data?.items ?? []).map((model: Model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          {invalidRange ? (
            <p className="text-xs text-rose-600 dark:text-rose-400" role="alert">
              {t("logs:filters.invalidDate")}
            </p>
          ) : null}
          <p className="app-muted text-xs">{t("logs:filters.dateHint")}</p>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={invalidRange}
              onClick={() => {
                setApplied(draft);
                setPage(1);
              }}
            >
              {t("logs:filters.apply")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                const cleared = defaultFilters();
                setDraft(cleared);
                setApplied(cleared);
                setPage(1);
              }}
            >
              {t("logs:filters.reset")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {logsQuery.isPending ? <LoadingState /> : null}
      {logsQuery.isError ? (
        <ErrorState error={logsQuery.error} onRetry={() => void logsQuery.refetch()} />
      ) : null}

      {logsQuery.data ? (
        logsQuery.data.items.length === 0 ? (
          <EmptyState title={t("logs:empty")} hint={t("logs:emptyHint")} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>
                {t("logs:pagination.total", { count: n(logsQuery.data.total) })}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-0 py-0">
              <TableWrapper className="rounded-none border-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("logs:table.time")}</TableHead>
                      <TableHead>{t("logs:table.requestId")}</TableHead>
                      <TableHead>{t("logs:table.provider")}</TableHead>
                      <TableHead>{t("logs:table.model")}</TableHead>
                      <TableHead>{t("logs:table.state")}</TableHead>
                      <TableHead>{t("logs:table.attempts")}</TableHead>
                      <TableHead>{t("logs:table.statusCode")}</TableHead>
                      <TableHead>{t("logs:table.tokens")}</TableHead>
                      <TableHead>{t("logs:table.latency")}</TableHead>
                      <TableHead>{t("logs:table.details")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {logsQuery.data.items.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell
                          className="whitespace-nowrap text-xs"
                          title={dateTime(entry.created_at)}
                        >
                          {relative(entry.created_at)}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Ltr mono>{entry.request_id}</Ltr>
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.provider_name ? (
                            <Ltr>{entry.provider_name}</Ltr>
                          ) : (
                            <span className="app-muted">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.model_name ? (
                            <Ltr>{entry.model_name}</Ltr>
                          ) : (
                            <span className="app-muted">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Badge tone={stateTone(entry.state)}>
                              {t(`logs:state.${entry.state}`)}
                            </Badge>
                            {entry.streaming ? (
                              <Badge tone="neutral">{t("logs:streaming")}</Badge>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell
                          title={t("logs:attemptsCount", { count: n(entry.attempt_count) })}
                        >
                          {n(entry.attempt_count)}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Ltr mono>{tech(entry.status_code)}</Ltr>
                          {entry.error_code ? (
                            <div className="mt-1">
                              <Ltr mono className="text-rose-600 dark:text-rose-400">
                                {entry.error_code}
                              </Ltr>
                            </div>
                          ) : null}
                        </TableCell>
                        <TableCell>{n(entry.total_tokens)}</TableCell>
                        <TableCell>{duration(entry.latency_ms)}</TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm" onClick={() => setSelected(entry)}>
                            {t("logs:table.details")}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableWrapper>

              <div className="flex items-center justify-between gap-3 border-t app-divide px-5 py-3">
                <span className="app-muted text-xs">
                  {t("logs:pagination.page", { page: n(page), total: n(totalPages) })}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    {t("logs:pagination.previous")}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((current) => current + 1)}
                  >
                    {t("logs:pagination.next")}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )
      ) : null}

      <Dialog
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={t("logs:detail.title")}
        description={selected ? t("logs:detail.subtitle", { requestId: selected.request_id }) : undefined}
      >
        {detailQuery.isPending ? <LoadingState /> : null}
        {detailQuery.isError ? (
          <ErrorState error={detailQuery.error} onRetry={() => void detailQuery.refetch()} />
        ) : null}
        {detailQuery.data ? (
          <div className="flex flex-col gap-4 text-xs">
            <div className="flex flex-col gap-2">
              <DetailRow label={t("logs:detail.state")}>
                <Badge tone={stateTone(detailQuery.data.request.state)}>
                  {t(`logs:state.${detailQuery.data.request.state}`)}
                </Badge>
              </DetailRow>
              <DetailRow label={t("logs:detail.statusCode")}>
                <Ltr mono>{tech(detailQuery.data.request.status_code)}</Ltr>
              </DetailRow>
              <DetailRow label={t("logs:detail.errorCode")}>
                {detailQuery.data.request.error_code ? (
                  <Ltr mono>{detailQuery.data.request.error_code}</Ltr>
                ) : (
                  "—"
                )}
              </DetailRow>
              <DetailRow label={t("logs:detail.latency")}>
                {duration(detailQuery.data.request.latency_ms)}
              </DetailRow>
              <DetailRow label={t("logs:detail.tokens")}>
                {n(detailQuery.data.request.total_tokens)}
              </DetailRow>
              <DetailRow label={t("logs:table.key")}>
                {detailQuery.data.request.api_key_name ?? "—"}
              </DetailRow>
              <DetailRow label={t("logs:table.time")}>
                {dateTime(detailQuery.data.request.created_at)}
              </DetailRow>
            </div>

            <div className="flex flex-col gap-2">
              <div>
                <p className="font-medium">{t("logs:detail.attempts")}</p>
                <p className="app-muted mt-1 leading-relaxed">{t("logs:detail.attemptsHint")}</p>
              </div>

              {detailQuery.data.attempts.length === 0 ? (
                <EmptyState title={t("logs:detail.noAttempts")} />
              ) : (
                detailQuery.data.attempts.map((attempt) => (
                  <div
                    key={attempt.id}
                    className="flex flex-col gap-2 rounded-lg border app-divide p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {t("logs:detail.attempt", { number: n(attempt.attempt_number) })}
                      </span>
                      {attempt.is_final ? (
                        <Badge tone="brand">{t("logs:detail.finalAttempt")}</Badge>
                      ) : null}
                      {attempt.retryable ? (
                        <Badge tone="warning">{t("logs:detail.retryableAttempt")}</Badge>
                      ) : null}
                      <Ltr mono className="ms-auto">
                        {tech(attempt.status_code)}
                      </Ltr>
                    </div>
                    <DetailRow label={t("logs:detail.provider")}>
                      <Ltr>{attempt.provider_name ?? "—"}</Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.model")}>
                      <Ltr>{attempt.model_name ?? "—"}</Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.endpoint")}>
                      <Ltr mono>{attempt.endpoint_path ?? "—"}</Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.credential")}>
                      <Ltr>{attempt.credential_label ?? "—"}</Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.errorCode")}>
                      {attempt.error_code ? <Ltr mono>{attempt.error_code}</Ltr> : "—"}
                    </DetailRow>
                    <DetailRow label={t("logs:detail.tokens")}>
                      <Ltr mono>
                        {tech(attempt.input_tokens)} / {tech(attempt.output_tokens)}
                      </Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.cost")}>
                      <Ltr mono>{tech(attempt.cost, 6)}</Ltr>
                    </DetailRow>
                    <DetailRow label={t("logs:detail.latency")}>
                      {duration(attempt.latency_ms)}
                    </DetailRow>
                  </div>
                ))
              )}
            </div>

            <div className="flex flex-col gap-2">
              <p className="font-medium">{t("logs:detail.raw")}</p>
              <p className="app-muted leading-relaxed">{t("logs:detail.rawHint")}</p>
              <CodeBlock
                value={JSON.stringify(detailQuery.data, null, 2)}
                language="json"
                maxHeight="18rem"
                copyLabel={t("logs:detail.copy")}
                copiedLabel={t("logs:detail.copied")}
              />
            </div>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b app-divide pb-2 last:border-0">
      <span className="app-muted">{label}</span>
      <span className="text-end">{children}</span>
    </div>
  );
}

export default RequestLogsPage;
