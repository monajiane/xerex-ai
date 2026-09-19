/**
 * Provider registry («ارائه‌دهندگان»).
 *
 * Four UI states are mandatory (PROMPT.md 14.7): loading, empty, error and the
 * loaded table. Every destructive row action opens a Persian confirmation dialog
 * that states the real impact — the counts come from `GET /providers/{id}/delete-impact`,
 * not from a guess.
 */
import { useMemo, useState } from "react";
import { Boxes, MoreHorizontal, Pencil, PlugZap, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Menu } from "@/components/ui/menu";
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
import { Tooltip } from "@/components/ui/tooltip";
import { useToastHelpers } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { useAuth } from "@/features/auth/AuthProvider";
import { ProviderFormDialog } from "@/features/providers/ProviderFormDialog";
import { providersApi } from "@/lib/api/endpoints";
import type { Provider, ProviderKind, ProviderTestResult } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

const KIND_OPTIONS: ProviderKind[] = [
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "qwen",
  "openai_compatible",
];

export function ProvidersPage() {
  const { t } = useTranslation(["providers", "common", "errors"]);
  const enums = useDynamicTranslation("enums");
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { digits } = useLocale();

  const canManage = isRole("owner", "admin");
  const canOperate = isRole("owner", "admin", "operator");

  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<ProviderKind | "">("");
  const [stateFilter, setStateFilter] = useState<"" | "true" | "false">("");
  const [orderBy, setOrderBy] = useState("priority");
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Provider | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);
  const [testTarget, setTestTarget] = useState<Provider | null>(null);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);

  const params = useMemo(
    () => ({
      page: 1,
      page_size: 50,
      search: search.trim() || undefined,
      kind: kindFilter || undefined,
      enabled: stateFilter === "" ? undefined : stateFilter === "true",
      order_by: orderBy,
    }),
    [search, kindFilter, stateFilter, orderBy],
  );

  const providersQuery = useQuery({
    queryKey: ["providers", params],
    queryFn: ({ signal }) => providersApi.list(params, signal),
  });

  const impactQuery = useQuery({
    queryKey: ["provider-delete-impact", deleteTarget?.id],
    queryFn: ({ signal }) => providersApi.deleteImpact(deleteTarget!.id, signal),
    enabled: deleteTarget !== null,
  });

  const deleteMutation = useMutation({
    mutationFn: (provider: Provider) => providersApi.remove(provider.id),
    onSuccess: async () => {
      toast.success(t("providers:delete.done"));
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (provider: Provider) =>
      providersApi.update(provider.id, { enabled: !provider.enabled }),
    onSuccess: async (_data, provider) => {
      toast.success(provider.enabled ? t("providers:disabledDone") : t("providers:enabledDone"));
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: (provider: Provider) => providersApi.test(provider.id),
    onSuccess: async (result) => {
      setTestResult(result);
      if (result.ok) toast.success(t("providers:test.ok"));
      else if (result.error_code === "credential_missing") toast.error(t("providers:test.needCredential"));
      else toast.error(t("providers:test.failed"));
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  function runTest(provider: Provider) {
    setTestResult(null);
    setTestTarget(provider);
    testMutation.mutate(provider);
  }

  const impact = impactQuery.data;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("providers:title")}
        description={t("providers:subtitle")}
        actions={
          canManage ? (
            <Button
              size="sm"
              onClick={() => {
                setEditTarget(null);
                setFormOpen(true);
              }}
            >
              <Plus aria-hidden="true" />
              {t("providers:addProvider")}
            </Button>
          ) : null
        }
      />

      <Card>
        <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative min-w-0 flex-1">
            <label className="sr-only" htmlFor="provider-search">
              {t("common:actions.search")}
            </label>
            <input
              id="provider-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("providers:searchPlaceholder")}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              aria-label={t("providers:filterKind")}
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value as ProviderKind | "")}
              className="w-auto min-w-40"
            >
              <option value="">{t("providers:allKinds")}</option>
              {KIND_OPTIONS.map((kind) => (
                <option key={kind} value={kind}>
                  {enums.t(`providerKind.${kind}`, { defaultValue: kind })}
                </option>
              ))}
            </Select>
            <Select
              aria-label={t("providers:filterState")}
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value as "" | "true" | "false")}
              className="w-auto min-w-32"
            >
              <option value="">{t("providers:allStates")}</option>
              <option value="true">{t("common:status.enabled")}</option>
              <option value="false">{t("common:status.disabled")}</option>
            </Select>
            <Select
              aria-label={t("providers:orderBy")}
              value={orderBy}
              onChange={(event) => setOrderBy(event.target.value)}
              className="w-auto min-w-32"
            >
              <option value="priority">{t("providers:sortPriority")}</option>
              <option value="name">{t("providers:sortName")}</option>
              <option value="-created_at">{t("providers:sortNewest")}</option>
            </Select>
            {search || kindFilter || stateFilter ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setKindFilter("");
                  setStateFilter("");
                }}
              >
                {t("providers:clearFilters")}
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {providersQuery.isPending ? <LoadingState /> : null}
      {providersQuery.isError ? (
        <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />
      ) : null}

      {providersQuery.data ? (
        providersQuery.data.items.length === 0 ? (
          <EmptyState
            title={t("providers:empty")}
            hint={t("providers:emptyHint")}
            action={
              canManage ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setEditTarget(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus aria-hidden="true" />
                  {t("providers:addProvider")}
                </Button>
              ) : null
            }
          />
        ) : (
          <Card className="overflow-hidden">
            <CardContent className="px-0 py-0">
              <TableWrapper className="rounded-none border-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("providers:table.name")}</TableHead>
                      <TableHead>{t("providers:table.kind")}</TableHead>
                      <TableHead>{t("providers:table.baseUrl")}</TableHead>
                      <TableHead>{t("providers:table.health")}</TableHead>
                      <TableHead>{t("providers:table.credentials")}</TableHead>
                      <TableHead>{t("providers:table.models")}</TableHead>
                      <TableHead>{t("providers:table.priority")}</TableHead>
                      <TableHead>{t("providers:table.state")}</TableHead>
                      <TableHead>{t("providers:table.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {providersQuery.data.items.map((provider) => (
                      <TableRow key={provider.id}>
                        <TableCell>
                          <Link
                            to={`/providers/${provider.id}`}
                            className="font-medium text-brand-700 hover:underline dark:text-brand-300"
                          >
                            {provider.name}
                          </Link>
                          <div className="app-muted text-[0.6875rem]">
                            <Ltr mono>{provider.slug}</Ltr>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge tone="brand">
                            {enums.t(`providerKind.${provider.kind}`, { defaultValue: provider.kind })}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-56">
                          <Ltr mono className="block truncate text-xs app-muted" title={provider.base_url}>
                            {provider.base_url}
                          </Ltr>
                        </TableCell>
                        <TableCell>
                          <StatusBadge domain="healthStatus" value={provider.health_status} showRawValue />
                        </TableCell>
                        <TableCell className="text-xs">{digits(provider.credential_count)}</TableCell>
                        <TableCell className="text-xs">{digits(provider.model_count)}</TableCell>
                        <TableCell className="text-xs">{digits(provider.priority)}</TableCell>
                        <TableCell>
                          <Badge tone={provider.enabled ? "success" : "neutral"}>
                            {provider.enabled
                              ? t("common:status.enabled")
                              : t("common:status.disabled")}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {canOperate ? (
                              <Tooltip content={t("providers:test.action")}>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={t("providers:test.action")}
                                  onClick={() => runTest(provider)}
                                >
                                  <PlugZap aria-hidden="true" />
                                </Button>
                              </Tooltip>
                            ) : null}
                            {canManage ? (
                              <Menu
                                menuLabel={t("providers:table.actions")}
                                trigger={({ open, toggle }) => (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={t("providers:table.actions")}
                                    aria-expanded={open}
                                    onClick={toggle}
                                  >
                                    <MoreHorizontal aria-hidden="true" />
                                  </Button>
                                )}
                                items={[
                                  {
                                    label: t("common:actions.edit"),
                                    icon: <Pencil aria-hidden="true" />,
                                    onSelect: () => {
                                      setEditTarget(provider);
                                      setFormOpen(true);
                                    },
                                  },
                                  {
                                    label: provider.enabled
                                      ? t("common:actions.disable")
                                      : t("common:actions.enable"),
                                    icon: <PlugZap aria-hidden="true" />,
                                    onSelect: () => toggleMutation.mutate(provider),
                                  },
                                  {
                                    label: t("common:actions.delete"),
                                    icon: <Trash2 aria-hidden="true" />,
                                    tone: "danger",
                                    onSelect: () => setDeleteTarget(provider),
                                  },
                                ]}
                              />
                            ) : null}
                            <Button
                              variant="link"
                              size="sm"
                              onClick={() => navigate(`/providers/${provider.id}`)}
                            >
                              {t("common:actions.details")}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableWrapper>
            </CardContent>
          </Card>
        )
      ) : null}

      {formOpen ? (
        <ProviderFormDialog onClose={() => setFormOpen(false)} provider={editTarget} />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title={t("providers:delete.title")}
        message={t("providers:delete.message", { name: deleteTarget?.name ?? "" })}
        details={
          impact
            ? [
                t("providers:delete.impact", {
                  credentials: digits(impact.credential_count),
                  models: digits(impact.model_count),
                }),
                ...(impact.endpoint_count > 0
                  ? [t("providers:delete.impactEndpoints", { endpoints: digits(impact.endpoint_count) })]
                  : []),
              ]
            : undefined
        }
        confirmLabel={t("providers:delete.confirm")}
      />

      {testTarget ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border app-divide px-4 py-3 text-xs"
        >
          <p className="flex items-center gap-2 font-medium">
            <Boxes className="size-4" aria-hidden="true" />
            {t("providers:test.title")}
            <span className="app-muted font-normal">
              {testTarget.name} · <Ltr mono>{testTarget.slug}</Ltr>
            </span>
          </p>
          {testMutation.isPending ? (
            <p className="app-muted mt-1">{t("providers:test.running")}</p>
          ) : testResult ? (
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className={testResult.ok ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"}>
                {testResult.ok ? t("providers:test.ok") : t("providers:test.failed")}
              </span>
              <span className="app-muted">
                {t("providers:test.latency")}: {digits(testResult.latency_ms)} {t("common:units.ms")}
              </span>
              {testResult.status_code ? (
                <span className="app-muted">
                  {t("providers:test.statusCode")}: <Ltr mono>{testResult.status_code}</Ltr>
                </span>
              ) : null}
              {testResult.error_code ? (
                <span className="app-muted">
                  {t("errors:errorCode")}: <Ltr mono>{testResult.error_code}</Ltr>
                </span>
              ) : null}
              {typeof testResult.model_count === "number" ? (
                <span className="app-muted">
                  {t("providers:test.models")}: {digits(testResult.model_count)}
                </span>
              ) : null}
            </p>
          ) : (
            <p className="app-muted mt-1">{t("providers:test.needCredential")}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default ProvidersPage;
