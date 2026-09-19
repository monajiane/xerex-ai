/**
 * Smart routing («مسیریابی هوشمند», M5).
 *
 * The page answers two questions an operator actually has:
 *  - «کدام راهبرد برای این مدل اعمال می‌شود؟» — the rules table, ordered by priority,
 *    with the strategy catalogue and what each strategy needs;
 *  - «اگر همین حالا این درخواست برسد، کدام ارائه‌دهنده انتخاب می‌شود و چرا؟» — the
 *    simulator, which runs the same engine as live traffic and explains every candidate.
 *
 * Reason tokens come from the backend as stable English (`provider_priority=1`); the
 * translation below is the only place they become Persian.
 */
import { useMemo, useState } from "react";
import { FlaskConical, MoreHorizontal, Pencil, Plus, Route, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/input";
import { Menu } from "@/components/ui/menu";
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
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { useAuth } from "@/features/auth/AuthProvider";
import { RoutingRuleDialog } from "@/features/routing/RoutingRuleDialog";
import { RoutingSimulator } from "@/features/routing/RoutingSimulator";
import { routingApi } from "@/lib/api/endpoints";
import type { RoutingRule } from "@/lib/api/types";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function RoutingPage() {
  const { t } = useTranslation(["routing", "common", "errors"]);
  const enums = useDynamicTranslation("enums");
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const { digits } = useLocale();

  const canManage = isRole("owner", "admin");

  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<RoutingRule | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RoutingRule | null>(null);

  const strategiesQuery = useQuery({
    queryKey: ["routing", "strategies"],
    queryFn: ({ signal }) => routingApi.strategies(signal),
  });
  const rulesQuery = useQuery({
    queryKey: ["routing", "rules"],
    queryFn: ({ signal }) => routingApi.rules.list(signal),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["routing", "rules"] });
  };

  const toggleMutation = useMutation({
    mutationFn: ({ rule, enabled }: { rule: RoutingRule; enabled: boolean }) =>
      routingApi.rules.update(rule.id, { enabled }),
    onSuccess: async (_data, variables) => {
      toast.success(variables.enabled ? t("routing:rules.enabledDone") : t("routing:rules.disabledDone"));
      await invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (rule: RoutingRule) => routingApi.rules.remove(rule.id),
    onSuccess: async () => {
      toast.success(t("routing:rules.delete.done"));
      setDeleteTarget(null);
      await invalidate();
    },
  });

  const rules = rulesQuery.data ?? [];
  const strategies = strategiesQuery.data?.items ?? [];

  const strategyLabel = useMemo(
    () => (strategy: string) => enums.t(`strategy.${strategy}`, { defaultValue: strategy }),
    [enums],
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("routing:title")}
        description={t("routing:subtitle")}
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
              {t("routing:rules.add")}
            </Button>
          ) : null
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Route aria-hidden="true" className="size-4" />
            {t("routing:strategiesTitle")}
          </CardTitle>
          <CardDescription>{t("routing:strategiesHint")}</CardDescription>
        </CardHeader>
        <CardContent>
          {strategiesQuery.isPending ? (
            <LoadingState />
          ) : strategiesQuery.isError ? (
            <ErrorState error={strategiesQuery.error} onRetry={() => void strategiesQuery.refetch()} />
          ) : (
            <TableWrapper>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("routing:columns.strategy")}</TableHead>
                    <TableHead>{t("routing:columns.needs")}</TableHead>
                    <TableHead>{t("routing:columns.uses")}</TableHead>
                    <TableHead>{t("routing:columns.summary")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {strategies.map((spec) => (
                    <TableRow key={spec.strategy}>
                      <TableCell className="font-medium">{strategyLabel(spec.strategy)}</TableCell>
                      <TableCell className="text-sm">
                        {spec.requires_priority
                          ? t("routing:needs.priority")
                          : spec.requires_weight
                            ? t("routing:needs.weight")
                            : t("routing:needs.none")}
                      </TableCell>
                      <TableCell>
                        <span className="flex flex-wrap gap-1">
                          {spec.uses_health ? (
                            <Badge tone="info">{t("routing:uses.health")}</Badge>
                          ) : null}
                          {spec.uses_latency ? (
                            <Badge tone="info">{t("routing:uses.latency")}</Badge>
                          ) : null}
                          {spec.uses_cost ? (
                            <Badge tone="info">{t("routing:uses.cost")}</Badge>
                          ) : null}
                          {!spec.uses_health && !spec.uses_latency && !spec.uses_cost ? (
                            <Badge tone="neutral">{t("routing:uses.order")}</Badge>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-slate-600 dark:text-slate-300">
                        {spec.summary}
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
          <CardTitle>{t("routing:rules.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {rulesQuery.isPending ? (
            <LoadingState />
          ) : rulesQuery.isError ? (
            <ErrorState error={rulesQuery.error} onRetry={() => void rulesQuery.refetch()} />
          ) : rules.length === 0 ? (
            <EmptyState title={t("routing:rules.empty")} hint={t("routing:rules.emptyHint")} />
          ) : (
            <TableWrapper>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("routing:rules.table.name")}</TableHead>
                    <TableHead>{t("routing:rules.table.pattern")}</TableHead>
                    <TableHead>{t("routing:rules.table.strategy")}</TableHead>
                    <TableHead>{t("routing:rules.table.priority")}</TableHead>
                    {canManage ? <TableHead>{t("routing:rules.table.enabled")}</TableHead> : null}
                    <TableHead className="text-end">{t("routing:rules.table.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rules.map((rule) => {
                    const pattern = (rule.match_conditions?.model as string | undefined) ?? null;
                    return (
                      <TableRow key={rule.id}>
                        <TableCell className="font-medium">{rule.name}</TableCell>
                        <TableCell>
                          {pattern ? (
                            <Ltr className="font-mono text-xs">{pattern}</Ltr>
                          ) : (
                            <span className="text-sm text-slate-500 dark:text-slate-400">
                              {t("routing:rules.allModels")}
                            </span>
                          )}
                        </TableCell>
                        <TableCell>{strategyLabel(rule.strategy)}</TableCell>
                        <TableCell>
                          <Ltr className="font-mono text-xs">{digits(rule.priority)}</Ltr>
                        </TableCell>
                        {canManage ? (
                          <TableCell>
                            <Switch
                              checked={rule.enabled}
                              label={t("routing:rules.enabled")}
                              onCheckedChange={(enabled) => toggleMutation.mutate({ rule, enabled })}
                            />
                          </TableCell>
                        ) : null}
                        <TableCell className="text-end">
                          {canManage ? (
                            <Menu
                              menuLabel={t("routing:rules.table.actions")}
                              trigger={({ toggle, open }) => (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  aria-label={t("routing:rules.table.actions")}
                                  aria-expanded={open}
                                  onClick={toggle}
                                >
                                  <MoreHorizontal aria-hidden="true" />
                                </Button>
                              )}
                              items={[
                                {
                                  label: t("common:actions.edit"),
                                  icon: <Pencil aria-hidden="true" className="size-4" />,
                                  onSelect: () => {
                                    setEditTarget(rule);
                                    setFormOpen(true);
                                  },
                                },
                                {
                                  label: t("common:actions.delete"),
                                  icon: <Trash2 aria-hidden="true" className="size-4" />,
                                  tone: "danger",
                                  onSelect: () => setDeleteTarget(rule),
                                },
                              ]}
                            />
                          ) : null}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableWrapper>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FlaskConical aria-hidden="true" className="size-4" />
            {t("routing:simulate.title")}
          </CardTitle>
          <CardDescription>{t("routing:simulate.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <RoutingSimulator strategies={strategies} />
        </CardContent>
      </Card>

      {formOpen ? (
        <RoutingRuleDialog
          rule={editTarget}
          strategies={strategies}
          onClose={() => {
            setFormOpen(false);
            setEditTarget(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        title={t("routing:rules.delete.title")}
        message={t("routing:rules.delete.message", { name: deleteTarget?.name ?? "" })}
        details={[t("common:confirmDialog.irreversible")]}
        confirmLabel={t("routing:rules.delete.confirm")}
        loading={deleteMutation.isPending}
      />

    </div>
  );
}

export default RoutingPage;
