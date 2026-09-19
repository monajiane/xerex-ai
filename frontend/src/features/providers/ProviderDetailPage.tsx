/**
 * Provider detail («جزئیات ارائه‌دهنده»).
 *
 * Groups what the administrator needs in one place: identity, routing options,
 * the connectivity test and the credential panel. Everything technical is rendered
 * LTR-isolated; every label comes from the i18n layer.
 */
import { useState } from "react";
import { ArrowRight, PlugZap, Trash2 } from "lucide-react";
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
import { useDynamicTranslation } from "@/i18n/dynamic";
import { useAuth } from "@/features/auth/AuthProvider";
import { CredentialsPanel, isMissingProvider } from "@/features/providers/CredentialsPanel";
import { ProviderFormDialog } from "@/features/providers/ProviderFormDialog";
import { providersApi } from "@/lib/api/endpoints";
import { useLocale } from "@/lib/locale/LocaleProvider";

export function ProviderDetailPage() {
  const { providerId = "" } = useParams<{ providerId: string }>();
  const { t } = useTranslation(["providers", "common", "errors"]);
  const enums = useDynamicTranslation("enums");
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { dateTime, digits } = useLocale();

  const canManage = isRole("owner", "admin");
  const canOperate = isRole("owner", "admin", "operator");

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const providerQuery = useQuery({
    queryKey: ["provider", providerId],
    queryFn: ({ signal }) => providersApi.get(providerId, signal),
  });

  const impactQuery = useQuery({
    queryKey: ["provider-delete-impact", providerId],
    queryFn: ({ signal }) => providersApi.deleteImpact(providerId, signal),
    enabled: deleteOpen,
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => providersApi.update(providerId, { enabled }),
    onSuccess: async (_data, enabled) => {
      toast.success(enabled ? t("providers:enabledDone") : t("providers:disabledDone"));
      await queryClient.invalidateQueries({ queryKey: ["provider", providerId] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => providersApi.test(providerId),
    onSuccess: async (result) => {
      if (result.ok) toast.success(t("providers:test.ok"));
      else if (result.error_code === "credential_missing")
        toast.error(t("providers:test.needCredential"));
      else toast.error(t("providers:test.failed"));
      await queryClient.invalidateQueries({ queryKey: ["provider", providerId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => providersApi.remove(providerId),
    onSuccess: async () => {
      toast.success(t("providers:delete.done"));
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      navigate("/providers");
    },
  });

  const impact = impactQuery.data;

  if (providerQuery.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("providers:detail.title")} />
        <LoadingState />
      </div>
    );
  }

  if (providerQuery.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("providers:detail.title")} />
        {isMissingProvider(providerQuery.error) ? (
          <EmptyState
            title={t("providers:notFound")}
            action={
              <Button variant="secondary" size="sm" onClick={() => navigate("/providers")}>
                {t("providers:detail.back")}
              </Button>
            }
          />
        ) : (
          <ErrorState error={providerQuery.error} onRetry={() => void providerQuery.refetch()} />
        )}
      </div>
    );
  }

  const provider = providerQuery.data;

  return (
    <div className="flex flex-col gap-6">
      <Link
        to="/providers"
        className="app-muted inline-flex w-fit items-center gap-1.5 text-xs hover:underline"
      >
        {/* Directional icon: points back toward the start edge in RTL. */}
        <ArrowRight className="size-3.5 rotate-180 rtl:rotate-0" aria-hidden="true" />
        {t("providers:detail.back")}
      </Link>

      <PageHeader
        title={provider.name}
        description={provider.description ?? undefined}
        badge={
          <>
            <Badge tone="brand">
              {enums.t(`providerKind.${provider.kind}`, { defaultValue: provider.kind })}
            </Badge>
            <StatusBadge domain="healthStatus" value={provider.health_status} showRawValue />
            <Badge tone={provider.enabled ? "success" : "neutral"}>
              {provider.enabled ? t("common:status.enabled") : t("common:status.disabled")}
            </Badge>
          </>
        }
        actions={
          <>
            {canOperate ? (
              <Tooltip content={t("providers:test.action")}>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => testMutation.mutate()}
                  loading={testMutation.isPending}
                >
                  <PlugZap aria-hidden="true" />
                  {t("providers:test.action")}
                </Button>
              </Tooltip>
            ) : null}
            {canManage ? (
              <>
                <Button variant="ghost" size="sm" onClick={() => setEditOpen(true)}>
                  {t("common:actions.edit")}
                </Button>
                <Tooltip content={t("providers:delete.title")}>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("providers:delete.title")}
                    onClick={() => setDeleteOpen(true)}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </Tooltip>
              </>
            ) : null}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("providers:detail.overview")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <DetailRow label={t("providers:detail.baseUrl")}>
              <Ltr mono className="break-all">
                {provider.base_url}
              </Ltr>
            </DetailRow>
            <DetailRow label={t("providers:detail.slug")}>
              <Ltr mono>{provider.slug}</Ltr>
            </DetailRow>
            <DetailRow label={t("providers:detail.priority")}>{digits(provider.priority)}</DetailRow>
            <DetailRow label={t("providers:detail.weight")}>{digits(provider.weight)}</DetailRow>
            <DetailRow label={t("providers:detail.timeout")}>
              {digits(provider.timeout_ms)} {t("common:units.ms")}
            </DetailRow>
            <DetailRow label={t("providers:detail.maxRetries")}>
              {digits(provider.max_retries)}
            </DetailRow>
            <DetailRow label={t("providers:detail.credentials")}>
              {digits(provider.credential_count)}
            </DetailRow>
            <DetailRow label={t("providers:detail.models")}>{digits(provider.model_count)}</DetailRow>
            <DetailRow label={t("providers:detail.createdAt")}>{dateTime(provider.created_at)}</DetailRow>
            <DetailRow label={t("providers:detail.updatedAt")}>{dateTime(provider.updated_at)}</DetailRow>
            <DetailRow label={t("providers:detail.id")} className="sm:col-span-2">
              <Ltr mono className="break-all">
                {provider.id}
              </Ltr>
            </DetailRow>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("providers:form.enabled")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Switch
              checked={provider.enabled}
              label={t("providers:form.enabled")}
              disabled={!canManage || toggleMutation.isPending}
              onCheckedChange={(checked) => toggleMutation.mutate(checked)}
            />
            <p className="app-muted text-xs leading-relaxed">{t("providers:form.enabledHint")}</p>
          </CardContent>
        </Card>
      </div>

      <CredentialsPanel provider={provider} />

      {editOpen ? (
        <ProviderFormDialog onClose={() => setEditOpen(false)} provider={provider} />
      ) : null}

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => deleteMutation.mutate()}
        loading={deleteMutation.isPending}
        title={t("providers:delete.title")}
        message={t("providers:delete.message", { name: provider.name })}
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

export default ProviderDetailPage;
