/**
 * Credential management for one provider («اطلاعات احراز هویت»).
 *
 * Security rules enforced here as well as in the API:
 *  - a stored secret is never read back; the table shows the masked `key_hint`;
 *  - replacing a key is an explicit «چرخش کلید» action, never an edit;
 *  - a failed verification shows the stable English error code in an LTR badge
 *    and the Persian explanation from the `errors` namespace.
 */
import { useState } from "react";
import { Ban, KeyRound, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
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
import { EmptyState, ErrorState, LoadingState, useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth } from "@/features/auth/AuthProvider";
import { providersApi } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { Credential, Provider, ProviderTestResult } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

export interface CredentialsPanelProps {
  provider: Provider;
}

export function CredentialsPanel({ provider }: CredentialsPanelProps) {
  const { t } = useTranslation(["credentials", "common", "errors", "providers"]);
    const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const { dateTime, relative, digits } = useLocale();

  const canManage = isRole("owner", "admin");
  const canOperate = isRole("owner", "admin", "operator");

  const [createOpen, setCreateOpen] = useState(false);
  const [rotateTarget, setRotateTarget] = useState<Credential | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Credential | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Credential | null>(null);
  const [form, setForm] = useState({ label: "", secret: "" });
  const [formError, setFormError] = useState<unknown>(null);
  const [result, setResult] = useState<ProviderTestResult | null>(null);
  const { message: formErrorMessage, code: formErrorCode } = useErrorCopy(formError);

  const credentialsQuery = useQuery({
    queryKey: ["provider-credentials", provider.id],
    queryFn: ({ signal }) => providersApi.credentials.list(provider.id, signal),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["provider-credentials", provider.id] });
    await queryClient.invalidateQueries({ queryKey: ["providers"] });
    await queryClient.invalidateQueries({ queryKey: ["provider", provider.id] });
  };

  const createMutation = useMutation({
    mutationFn: () => providersApi.credentials.create(provider.id, form),
    onSuccess: async () => {
      toast.success(t("credentials:created"));
      setCreateOpen(false);
      setForm({ label: "", secret: "" });
      setFormError(null);
      await invalidate();
    },
    onError: (error) => setFormError(error),
  });

  const rotateMutation = useMutation({
    mutationFn: (secret: string) =>
      providersApi.credentials.rotate(provider.id, rotateTarget!.id, secret),
    onSuccess: async () => {
      toast.success(t("credentials:rotated"));
      setRotateTarget(null);
      await invalidate();
    },
    onError: (error) => setFormError(error),
  });

  const verifyMutation = useMutation({
    mutationFn: (credential: Credential) =>
      providersApi.credentials.verify(provider.id, credential.id),
    onSuccess: async (probe) => {
      setResult(probe);
      if (probe.ok) toast.success(t("credentials:verifyOk"));
      else toast.error(t("credentials:verifyFailed"));
      await invalidate();
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (credential: Credential) =>
      providersApi.credentials.update(provider.id, credential.id, { status: "revoked" }),
    onSuccess: async () => {
      toast.success(t("credentials:revoked"));
      setRevokeTarget(null);
      await invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (credential: Credential) =>
      providersApi.credentials.remove(provider.id, credential.id),
    onSuccess: async () => {
      toast.success(t("credentials:delete.done"));
      setDeleteTarget(null);
      await invalidate();
    },
  });

  const items = credentialsQuery.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" aria-hidden="true" />
          {t("credentials:title")}
        </CardTitle>
        {canManage ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <KeyRound aria-hidden="true" />
            {t("credentials:addCredential")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="app-muted text-xs leading-relaxed">{t("credentials:secretKeepHint")}</p>

        {credentialsQuery.isPending ? <LoadingState /> : null}
        {credentialsQuery.isError ? (
          <ErrorState error={credentialsQuery.error} onRetry={() => void credentialsQuery.refetch()} />
        ) : null}

        {credentialsQuery.data && items.length === 0 ? (
          <EmptyState title={t("credentials:empty")} hint={t("credentials:emptyHint")} />
        ) : null}

        {items.length > 0 ? (
          <TableWrapper>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("credentials:table.label")}</TableHead>
                  <TableHead>{t("credentials:table.key")}</TableHead>
                  <TableHead>{t("credentials:table.status")}</TableHead>
                  <TableHead>{t("credentials:table.lastVerified")}</TableHead>
                  <TableHead>{t("credentials:table.lastError")}</TableHead>
                  <TableHead>{t("common:actions.details")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((credential) => (
                  <TableRow key={credential.id}>
                    <TableCell className="font-medium">{credential.label}</TableCell>
                    <TableCell>
                      <Ltr mono className="app-muted">
                        {credential.key_hint}
                      </Ltr>
                    </TableCell>
                    <TableCell>
                      <StatusBadge domain="credentialStatus" value={credential.status} showRawValue />
                    </TableCell>
                    <TableCell className="app-muted text-xs">
                      {credential.last_verified_at ? (
                        <span title={dateTime(credential.last_verified_at)}>
                          {relative(credential.last_verified_at)}
                        </span>
                      ) : (
                        t("common:never")
                      )}
                    </TableCell>
                    <TableCell className="text-xs">
                      {credential.last_error_code ? (
                        <Badge tone="danger">
                          <Ltr mono>{credential.last_error_code}</Ltr>
                        </Badge>
                      ) : (
                        <span className="app-muted">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1">
                        {canOperate ? (
                          <Tooltip content={t("credentials:verify")}>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={t("credentials:verify")}
                              loading={
                                verifyMutation.isPending &&
                                verifyMutation.variables?.id === credential.id
                              }
                              onClick={() => verifyMutation.mutate(credential)}
                            >
                              <ShieldCheck aria-hidden="true" />
                            </Button>
                          </Tooltip>
                        ) : null}
                        {canManage ? (
                          <>
                            {credential.status === "active" ? (
                              <Tooltip content={t("credentials:revoke")}>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={t("credentials:revoke")}
                                  onClick={() => setRevokeTarget(credential)}
                                >
                                  <Ban aria-hidden="true" />
                                </Button>
                              </Tooltip>
                            ) : null}
                            <Tooltip content={t("credentials:rotate")}>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={t("credentials:rotate")}
                                onClick={() => {
                                  setFormError(null);
                                  setRotateTarget(credential);
                                }}
                              >
                                <RefreshCw aria-hidden="true" />
                              </Button>
                            </Tooltip>
                            <Tooltip content={t("credentials:delete.title")}>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={t("credentials:delete.title")}
                                onClick={() => setDeleteTarget(credential)}
                              >
                                <Trash2 aria-hidden="true" />
                              </Button>
                            </Tooltip>
                          </>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrapper>
        ) : null}

        {result ? (
          <div
            role="status"
            className={
              result.ok
                ? "rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-xs dark:border-emerald-900 dark:bg-emerald-950/40"
                : "rounded-lg border border-rose-200 bg-rose-50/70 px-3 py-2 text-xs dark:border-rose-900 dark:bg-rose-950/40"
            }
          >
            <p className="font-medium">{result.ok ? t("credentials:verifyOk") : t("credentials:verifyFailed")}</p>
            <p className="app-muted mt-1 flex flex-wrap items-center gap-2">
              <span>
                {t("providers:test.latency")}: {digits(result.latency_ms)} {t("common:units.ms")}
              </span>
              {result.status_code ? (
                <span>
                  {t("providers:test.statusCode")}: <Ltr mono>{result.status_code}</Ltr>
                </span>
              ) : null}
              {result.error_code ? (
                <span>
                  {t("errors:errorCode")}: <Ltr mono>{result.error_code}</Ltr>
                </span>
              ) : null}
              {typeof result.model_count === "number" ? (
                <span>
                  {t("providers:test.models")}: {digits(result.model_count)}
                </span>
              ) : null}
            </p>
          </div>
        ) : null}
      </CardContent>

      {/* create -------------------------------------------------------------- */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("credentials:createTitle")}
        description={t("credentials:createSubtitle")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              {t("common:actions.cancel")}
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!form.label.trim() || form.secret.trim().length < 8}
            >
              {t("common:actions.save")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label={t("credentials:label")} htmlFor="credential-label" required hint={t("credentials:labelHint")}>
            <Input
              id="credential-label"
              value={form.label}
              onChange={(event) => setForm({ ...form, label: event.target.value })}
            />
          </Field>
          <Field
            label={t("credentials:secret")}
            htmlFor="credential-secret"
            required
            hint={t("credentials:secretHint")}
          >
            <Input
              id="credential-secret"
              type="password"
              technical
              autoComplete="off"
              placeholder={t("credentials:secretPlaceholder")}
              value={form.secret}
              onChange={(event) => setForm({ ...form, secret: event.target.value })}
            />
          </Field>
          {formError ? (
            <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
              {formErrorMessage}
              {formErrorCode ? (
                <>
                  {" — "}
                  <Ltr mono className="opacity-80">
                    {formErrorCode}
                  </Ltr>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      </Dialog>

      {/* rotate -------------------------------------------------------------- */}
      <Dialog
        open={rotateTarget !== null}
        onClose={() => setRotateTarget(null)}
        title={t("credentials:rotateTitle")}
        description={t("credentials:rotateSubtitle")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRotateTarget(null)}>
              {t("common:actions.cancel")}
            </Button>
            <Button
              onClick={() => rotateMutation.mutate(form.secret)}
              loading={rotateMutation.isPending}
              disabled={form.secret.trim().length < 8}
            >
              {t("credentials:rotate")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="app-muted text-xs">
            {t("credentials:table.label")}: <span className="font-medium">{rotateTarget?.label}</span>
          </p>
          <Field label={t("credentials:newSecret")} htmlFor="credential-new-secret" required>
            <Input
              id="credential-new-secret"
              type="password"
              technical
              autoComplete="off"
              value={form.secret}
              onChange={(event) => setForm({ ...form, secret: event.target.value })}
            />
          </Field>
          {formError ? (
            <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
              {formErrorMessage}
            </p>
          ) : null}
        </div>
      </Dialog>

      {/* delete -------------------------------------------------------------- */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title={t("credentials:delete.title")}
        message={t("credentials:delete.message", { label: deleteTarget?.label ?? "" })}
        confirmLabel={t("credentials:delete.confirm")}
      />

      {/* revoke -------------------------------------------------------------- */}
      <ConfirmDialog
        open={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={() => revokeTarget && revokeMutation.mutate(revokeTarget)}
        loading={revokeMutation.isPending}
        tone="warning"
        title={t("credentials:revoke")}
        message={t("credentials:revokeMessage", { label: revokeTarget?.label ?? "" })}
        details={[t("credentials:revokeConfirm")]}
        confirmLabel={t("credentials:revoke")}
      />
    </Card>
  );
}

/** Narrow helper used by pages that only need to know whether a 404 happened. */
export function isMissingProvider(error: unknown): boolean {
  return error instanceof ApiError && error.code === "provider_not_found";
}

export default CredentialsPanel;
