/**
 * Model registry («مدل‌ها»).
 *
 * Capability badges, pricing and state come from the stored rows; nothing is
 * guessed. «کشف مدل‌ها» and «آزمایش مدل» are the two operational actions, and every
 * destructive row action opens a Persian confirmation dialog.
 */
import { useMemo, useState } from "react";
import { Cpu, FlaskConical, MoreHorizontal, Pencil, Plus, Radar, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
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
import { useAuth } from "@/features/auth/AuthProvider";
import { DiscoveryDialog } from "@/features/models/DiscoveryDialog";
import { ModelFormDialog } from "@/features/models/ModelFormDialog";
import { useProvidersLookup } from "@/features/providers/useProviders";
import { modelsApi } from "@/lib/api/endpoints";
import type { Model } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

type StateFilter = "" | "enabled" | "disabled" | "deprecated";

export function ModelsPage() {
  const { t } = useTranslation(["models", "common", "providers", "errors"]);
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const { digits } = useLocale();
  const providers = useProvidersLookup();

  const canManage = isRole("owner", "admin");
  const canOperate = isRole("owner", "admin", "operator");

  const [search, setSearch] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("");
  const [orderBy, setOrderBy] = useState("name");
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Model | null>(null);
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Model | null>(null);

  const params = useMemo(
    () => ({
      page: 1,
      page_size: 100,
      search: search.trim() || undefined,
      provider_id: providerFilter || undefined,
      enabled: stateFilter === "enabled" ? true : stateFilter === "disabled" ? false : undefined,
      deprecated: stateFilter === "deprecated" ? true : undefined,
      order_by: orderBy,
    }),
    [search, providerFilter, stateFilter, orderBy],
  );

  const modelsQuery = useQuery({
    queryKey: ["models", params],
    queryFn: ({ signal }) => modelsApi.list(params, signal),
  });

  const deleteMutation = useMutation({
    mutationFn: (model: Model) => modelsApi.remove(model.id),
    onSuccess: async () => {
      toast.success(t("models:delete.done"));
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ model, enabled }: { model: Model; enabled: boolean }) =>
      modelsApi.update(model.id, { enabled }),
    onSuccess: async (_data, variables) => {
      toast.success(variables.enabled ? t("models:enabledDone") : t("models:disabledDone"));
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const deprecateMutation = useMutation({
    mutationFn: ({ model, deprecated }: { model: Model; deprecated: boolean }) =>
      modelsApi.update(model.id, { deprecated }),
    onSuccess: async (_data, variables) => {
      toast.success(variables.deprecated ? t("models:deprecatedDone") : t("models:restoredDone"));
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const models = modelsQuery.data?.items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("models:title")}
        description={t("models:subtitle")}
        actions={
          canManage ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setDiscoveryOpen(true)}>
                <Radar aria-hidden="true" />
                {t("models:discover.action")}
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  setEditTarget(null);
                  setFormOpen(true);
                }}
              >
                <Plus aria-hidden="true" />
                {t("models:addModel")}
              </Button>
            </>
          ) : null
        }
      />

      <Card>
        <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="min-w-0 flex-1">
            <label className="sr-only" htmlFor="model-search">
              {t("common:actions.search")}
            </label>
            <input
              id="model-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("models:searchPlaceholder")}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              aria-label={t("models:filterProvider")}
              value={providerFilter}
              onChange={(event) => setProviderFilter(event.target.value)}
              className="w-auto min-w-40"
            >
              <option value="">{t("models:allProviders")}</option>
              {providers.providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label={t("models:filterState")}
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value as StateFilter)}
              className="w-auto min-w-36"
            >
              <option value="">{t("models:allStates")}</option>
              <option value="enabled">{t("models:stateEnabled")}</option>
              <option value="disabled">{t("models:stateDisabled")}</option>
              <option value="deprecated">{t("models:stateDeprecated")}</option>
            </Select>
            <Select
              aria-label={t("models:orderBy")}
              value={orderBy}
              onChange={(event) => setOrderBy(event.target.value)}
              className="w-auto min-w-32"
            >
              <option value="name">{t("models:sortName")}</option>
              <option value="provider">{t("models:sortProvider")}</option>
              <option value="-created_at">{t("models:sortNewest")}</option>
            </Select>
            {search || providerFilter || stateFilter ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setProviderFilter("");
                  setStateFilter("");
                }}
              >
                {t("models:clearFilters")}
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {modelsQuery.isPending ? <LoadingState /> : null}
      {modelsQuery.isError ? (
        <ErrorState error={modelsQuery.error} onRetry={() => void modelsQuery.refetch()} />
      ) : null}

      {modelsQuery.data ? (
        models.length === 0 ? (
          <EmptyState
            title={t("models:empty")}
            hint={t("models:emptyHint")}
            action={
              canManage ? (
                <Button variant="secondary" size="sm" onClick={() => setDiscoveryOpen(true)}>
                  <Radar aria-hidden="true" />
                  {t("models:discover.action")}
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
                      <TableHead>{t("models:table.name")}</TableHead>
                      <TableHead>{t("models:table.provider")}</TableHead>
                      <TableHead>{t("models:table.capabilities")}</TableHead>
                      <TableHead>{t("models:table.contextWindow")}</TableHead>
                      <TableHead>{t("models:table.pricing")}</TableHead>
                      <TableHead>{t("models:table.state")}</TableHead>
                      <TableHead>{t("models:table.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {models.map((model) => (
                      <TableRow key={model.id}>
                        <TableCell>
                          <Link
                            to={`/models/${model.id}`}
                            className="font-medium text-brand-700 hover:underline dark:text-brand-300"
                          >
                            {model.display_name ?? model.name}
                          </Link>
                          <div className="app-muted text-[0.6875rem]">
                            <Ltr mono>{model.name}</Ltr>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs">{providers.nameOf(model.provider_id)}</TableCell>
                        <TableCell>
                          <CapabilityBadges capabilities={model.capabilities} />
                        </TableCell>
                        <TableCell className="text-xs">
                          {model.context_window ? digits(model.context_window) : t("common:notAvailable")}
                        </TableCell>
                        <TableCell className="text-xs">
                          {model.input_price_per_1m === null && model.output_price_per_1m === null ? (
                            <span className="app-muted">{t("models:detail.priceUnknown")}</span>
                          ) : (
                            <span className="flex flex-col">
                              <span>
                                {t("models:detail.inputPrice")}:{" "}
                                <Ltr mono>
                                  {model.input_price_per_1m !== null
                                    ? `$${model.input_price_per_1m}`
                                    : "—"}
                                </Ltr>
                              </span>
                              <span>
                                {t("models:detail.outputPrice")}:{" "}
                                <Ltr mono>
                                  {model.output_price_per_1m !== null
                                    ? `$${model.output_price_per_1m}`
                                    : "—"}
                                </Ltr>
                              </span>
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1">
                            <StatusBadge
                              domain="modelState"
                              value={model.enabled ? "enabled" : "disabled"}
                            />
                            {model.deprecated ? (
                              <Badge tone="warning">{t("models:stateDeprecated")}</Badge>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {canOperate ? (
                              <Tooltip content={t("models:detail.playground")}>
                                <Link
                                  to={`/models/${model.id}`}
                                  aria-label={t("models:detail.playground")}
                                  className="inline-flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                                >
                                  <FlaskConical className="size-4" aria-hidden="true" />
                                </Link>
                              </Tooltip>
                            ) : null}
                            {canManage ? (
                              <Menu
                                menuLabel={t("models:table.actions")}
                                trigger={({ open, toggle }) => (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={t("models:table.actions")}
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
                                      setEditTarget(model);
                                      setFormOpen(true);
                                    },
                                  },
                                  {
                                    label: model.enabled
                                      ? t("common:actions.disable")
                                      : t("common:actions.enable"),
                                    icon: <Cpu aria-hidden="true" />,
                                    onSelect: () =>
                                      toggleMutation.mutate({ model, enabled: !model.enabled }),
                                  },
                                  {
                                    label: model.deprecated
                                      ? t("models:restoredDone")
                                      : t("models:deprecatedDone"),
                                    onSelect: () =>
                                      deprecateMutation.mutate({
                                        model,
                                        deprecated: !model.deprecated,
                                      }),
                                  },
                                  {
                                    label: t("common:actions.delete"),
                                    icon: <Trash2 aria-hidden="true" />,
                                    tone: "danger",
                                    onSelect: () => setDeleteTarget(model),
                                  },
                                ]}
                              />
                            ) : null}
                            <Link
                              to={`/models/${model.id}`}
                              className="rounded-lg px-2 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-900/40"
                            >
                              {t("common:actions.details")}
                            </Link>
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
        <ModelFormDialog
          onClose={() => setFormOpen(false)}
          model={editTarget}
          providerId={providerFilter || undefined}
        />
      ) : null}

      {discoveryOpen ? (
        <DiscoveryDialog
          onClose={() => setDiscoveryOpen(false)}
          providerId={providerFilter || undefined}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title={t("models:delete.title")}
        message={t("models:delete.message", {
          name: deleteTarget?.display_name ?? deleteTarget?.name ?? "",
        })}
        details={[t("models:delete.impact")]}
        confirmLabel={t("models:delete.confirm")}
      />
    </div>
  );
}

/** Capability badges are derived from the stored flags — no hard-coded feature list. */
export function CapabilityBadges({
  capabilities,
}: {
  capabilities: Record<string, unknown> | null;
}) {
  const { t } = useTranslation("models");
  const entries = Object.entries(capabilities ?? {}).filter(([, value]) => Boolean(value));
  if (entries.length === 0) {
    return <span className="app-muted text-xs">{t("detail.noCapabilities")}</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {entries.map(([key]) => (
        <Badge key={key} tone="info">
          <Ltr mono>{key}</Ltr>
        </Badge>
      ))}
    </span>
  );
}

export default ModelsPage;
