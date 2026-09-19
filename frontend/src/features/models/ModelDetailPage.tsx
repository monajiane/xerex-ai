/**
 * Model detail («جزئیات مدل»).
 *
 * Three blocks the administrator needs together: the specification (state, pricing,
 * context window), the dispatch targets («نقاط اتصال مدل») and the playground.
 * Every technical value is LTR-isolated; every label comes from the i18n layer.
 */
import { useState } from "react";
import { ArrowRight, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/tooltip";
import { useToastHelpers } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth } from "@/features/auth/AuthProvider";
import { CapabilityBadges } from "@/features/models/ModelsPage";
import { EndpointsPanel } from "@/features/models/EndpointsPanel";
import { ModelFormDialog } from "@/features/models/ModelFormDialog";
import { PlaygroundPanel } from "@/features/models/PlaygroundPanel";
import { useProvidersLookup } from "@/features/providers/useProviders";
import { modelsApi } from "@/lib/api/endpoints";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function ModelDetailPage() {
  const { modelId = "" } = useParams<{ modelId: string }>();
  const { t } = useTranslation(["models", "common", "providers", "errors"]);
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { digits, dateTime, cost } = useLocale();
  const providers = useProvidersLookup();

  const canManage = isRole("owner", "admin");
  const canOperate = isRole("owner", "admin", "operator");

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const modelQuery = useQuery({
    queryKey: ["model", modelId],
    queryFn: ({ signal }) => modelsApi.get(modelId, signal),
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => modelsApi.update(modelId, { enabled }),
    onSuccess: async (_data, enabled) => {
      toast.success(enabled ? t("models:enabledDone") : t("models:disabledDone"));
      await queryClient.invalidateQueries({ queryKey: ["model", modelId] });
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const deprecateMutation = useMutation({
    mutationFn: (deprecated: boolean) => modelsApi.update(modelId, { deprecated }),
    onSuccess: async (_data, deprecated) => {
      toast.success(deprecated ? t("models:deprecatedDone") : t("models:restoredDone"));
      await queryClient.invalidateQueries({ queryKey: ["model", modelId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => modelsApi.remove(modelId),
    onSuccess: async () => {
      toast.success(t("models:delete.done"));
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      navigate("/models");
    },
  });

  if (modelQuery.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("models:detail.title")} />
        <LoadingState />
      </div>
    );
  }

  if (modelQuery.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("models:detail.title")} />
        <ErrorState error={modelQuery.error} onRetry={() => void modelQuery.refetch()} />
      </div>
    );
  }

  const model = modelQuery.data;
  const provider = providers.byId.get(model.provider_id);

  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/models"
        className="app-muted inline-flex w-fit items-center gap-1.5 text-xs hover:underline"
      >
        <ArrowRight className="size-3.5 rotate-180 rtl:rotate-0" aria-hidden="true" />
        {t("models:detail.back")}
      </Link>

      <PageHeader
        title={model.display_name ?? model.name}
        description={provider ? provider.name : undefined}
        badge={
          <>
            <StatusBadge domain="modelState" value={model.enabled ? "enabled" : "disabled"} />
            {model.deprecated ? <Badge tone="warning">{t("models:stateDeprecated")}</Badge> : null}
            <Badge tone="neutral">
              <Ltr mono>{model.name}</Ltr>
            </Badge>
          </>
        }
        actions={
          canManage ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditOpen(true)}>
                {t("common:actions.edit")}
              </Button>
              <Tooltip content={t("models:delete.title")}>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t("models:delete.title")}
                  onClick={() => setDeleteOpen(true)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </Tooltip>
            </>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("models:detail.specs")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <DetailRow label={t("models:detail.provider")}>
              <Link to={`/providers/${model.provider_id}`} className="hover:underline">
                {provider?.name ?? model.provider_id}
              </Link>
            </DetailRow>
            <DetailRow label={t("models:detail.contextWindow")}>
              {model.context_window ? digits(model.context_window) : t("common:notAvailable")}
            </DetailRow>
            <DetailRow label={t("models:detail.maxOutputTokens")}>
              {model.max_output_tokens ? digits(model.max_output_tokens) : t("common:notAvailable")}
            </DetailRow>
            <DetailRow label={t("models:detail.inputPrice")}>
              {model.input_price_per_1m !== null
                ? t("models:detail.pricePerMillion", { price: model.input_price_per_1m })
                : t("models:detail.priceUnknown")}
            </DetailRow>
            <DetailRow label={t("models:detail.outputPrice")}>
              {model.output_price_per_1m !== null
                ? t("models:detail.pricePerMillion", { price: model.output_price_per_1m })
                : t("models:detail.priceUnknown")}
            </DetailRow>
            <DetailRow label={t("models:detail.capabilities")}>
              <CapabilityBadges capabilities={model.capabilities} />
            </DetailRow>
            <DetailRow label={t("models:detail.discoveredAt")}>
              {model.discovered_at ? dateTime(model.discovered_at) : t("common:notAvailable")}
            </DetailRow>
            <DetailRow label={t("models:detail.updatedAt")}>{dateTime(model.updated_at)}</DetailRow>
            <DetailRow label={t("models:detail.id")} className="sm:col-span-2">
              <Ltr mono className="break-all">
                {model.id}
              </Ltr>
            </DetailRow>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("models:form.sectionState")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <Switch
                checked={model.enabled}
                label={t("models:form.enabled")}
                disabled={!canManage || toggleMutation.isPending}
                onCheckedChange={(checked) => toggleMutation.mutate(checked)}
              />
              <span className="text-xs">{t("models:form.enabled")}</span>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                checked={model.deprecated}
                label={t("models:form.deprecated")}
                disabled={!canManage || deprecateMutation.isPending}
                onCheckedChange={(checked) => deprecateMutation.mutate(checked)}
              />
              <span className="text-xs">{t("models:form.deprecated")}</span>
            </div>
            <p className="app-muted text-[0.6875rem] leading-relaxed">
              {t("models:form.deprecatedHint")}
            </p>
            {model.input_price_per_1m !== null || model.output_price_per_1m !== null ? (
              <p className="app-muted text-[0.6875rem] leading-relaxed">
                {t("models:playground.costHint")}
                {model.input_price_per_1m !== null ? (
                  <>
                    {" "}
                    <Ltr mono>{cost(model.input_price_per_1m)}</Ltr>
                  </>
                ) : null}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <EndpointsPanel model={model} />
      <PlaygroundPanel model={model} canRun={canOperate} />

      {editOpen ? (
        <ModelFormDialog onClose={() => setEditOpen(false)} model={model} />
      ) : null}

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => deleteMutation.mutate()}
        loading={deleteMutation.isPending}
        title={t("models:delete.title")}
        message={t("models:delete.message", { name: model.display_name ?? model.name })}
        details={[t("models:delete.impact")]}
        confirmLabel={t("models:delete.confirm")}
      />

      {providers.providers.length === 0 && providers.isError ? (
        <EmptyState title={t("providers:empty")} />
      ) : null}
    </div>
  );
}

function DetailRow({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="app-muted mb-1 text-[0.6875rem]">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export default ModelDetailPage;
