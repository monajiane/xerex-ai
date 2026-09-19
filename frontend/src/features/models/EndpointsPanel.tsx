/**
 * «نقاط اتصال مدل» — the dispatch targets of one model.
 *
 * An endpoint carries the path, the method, whether it streams, and optionally the
 * credential the call leaves through. Leaving the credential empty is a real
 * choice — the provider default is used — and the UI says so instead of showing a
 * blank cell.
 */
import { useState } from "react";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Switch } from "@/components/ui/input";
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
import { EmptyState, ErrorState, LoadingState, useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { useAuth } from "@/features/auth/AuthProvider";
import { providersApi, modelsApi } from "@/lib/api/endpoints";
import type { Model, ModelEndpoint } from "@/lib/api/types";

interface FormState {
  path: string;
  method: string;
  streamingSupported: boolean;
  credentialId: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  path: "/chat/completions",
  method: "POST",
  streamingSupported: true,
  credentialId: "",
  enabled: true,
};

export function EndpointsPanel({ model }: { model: Model }) {
  const { t } = useTranslation(["models", "common", "credentials", "errors"]);
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const canManage = isRole("owner", "admin");

  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ModelEndpoint | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelEndpoint | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);

  const endpointsQuery = useQuery({
    queryKey: ["model-endpoints", model.id],
    queryFn: ({ signal }) => modelsApi.endpoints.list(model.id, signal),
  });

  const credentialsQuery = useQuery({
    queryKey: ["provider-credentials", model.provider_id],
    queryFn: ({ signal }) => providersApi.credentials.list(model.provider_id, signal),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["model-endpoints", model.id] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      modelsApi.endpoints.create(model.id, {
        path: form.path.trim(),
        method: form.method,
        streaming_supported: form.streamingSupported,
        credential_id: form.credentialId || null,
        enabled: form.enabled,
      }),
    onSuccess: async () => {
      toast.success(t("models:endpoints.created"));
      setFormOpen(false);
      await invalidate();
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      modelsApi.endpoints.update(model.id, editTarget!.id, {
        path: form.path.trim(),
        method: form.method,
        streaming_supported: form.streamingSupported,
        credential_id: form.credentialId || null,
        enabled: form.enabled,
      }),
    onSuccess: async () => {
      toast.success(t("models:endpoints.updated"));
      setFormOpen(false);
      await invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (endpoint: ModelEndpoint) => modelsApi.endpoints.remove(model.id, endpoint.id),
    onSuccess: async () => {
      toast.success(t("models:endpoints.deleted"));
      setDeleteTarget(null);
      await invalidate();
    },
  });

  const { message: formErrorMessage, code: formErrorCode } = useErrorCopy(
    createMutation.error ?? updateMutation.error,
  );

  function openForm(endpoint: ModelEndpoint | null) {
    setEditTarget(endpoint);
    setForm(
      endpoint
        ? {
            path: endpoint.path,
            method: endpoint.method,
            streamingSupported: endpoint.streaming_supported,
            credentialId: endpoint.credential_id ?? "",
            enabled: endpoint.enabled,
          }
        : EMPTY,
    );
    setFormOpen(true);
  }

  const endpoints = endpointsQuery.data ?? [];
  const credentials = credentialsQuery.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle>{t("models:detail.endpoints")}</CardTitle>
        {canManage ? (
          <Button size="sm" variant="secondary" onClick={() => openForm(null)}>
            <Plus aria-hidden="true" />
            {t("models:endpoints.add")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {endpointsQuery.isPending ? <LoadingState /> : null}
        {endpointsQuery.isError ? (
          <ErrorState error={endpointsQuery.error} onRetry={() => void endpointsQuery.refetch()} />
        ) : null}

        {endpointsQuery.data && endpoints.length === 0 ? (
          <EmptyState title={t("models:endpoints.empty")} hint={t("models:endpoints.emptyHint")} />
        ) : null}

        {endpoints.length > 0 ? (
          <TableWrapper>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("models:endpoints.table.path")}</TableHead>
                  <TableHead>{t("models:endpoints.table.method")}</TableHead>
                  <TableHead>{t("models:endpoints.table.streaming")}</TableHead>
                  <TableHead>{t("models:endpoints.table.credential")}</TableHead>
                  <TableHead>{t("models:endpoints.table.state")}</TableHead>
                  <TableHead>{t("models:endpoints.table.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {endpoints.map((endpoint) => (
                  <TableRow key={endpoint.id}>
                    <TableCell>
                      <Ltr mono>{endpoint.path}</Ltr>
                    </TableCell>
                    <TableCell>
                      <Ltr mono className="text-xs">
                        {endpoint.method}
                      </Ltr>
                    </TableCell>
                    <TableCell>
                      <Badge tone={endpoint.streaming_supported ? "success" : "neutral"}>
                        {endpoint.streaming_supported ? t("common:yes") : t("common:no")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {endpoint.credential_id ? (
                        credentials.find((item) => item.id === endpoint.credential_id)?.label ??
                        t("models:endpoints.credential")
                      ) : (
                        <span className="app-muted">{t("models:endpoints.credentialDefault")}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge tone={endpoint.enabled ? "success" : "neutral"}>
                        {endpoint.enabled ? t("common:status.enabled") : t("common:status.disabled")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {canManage ? (
                        <Menu
                          menuLabel={t("models:endpoints.table.actions")}
                          trigger={({ open, toggle }) => (
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={t("models:endpoints.table.actions")}
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
                              onSelect: () => openForm(endpoint),
                            },
                            {
                              label: t("common:actions.delete"),
                              icon: <Trash2 aria-hidden="true" />,
                              tone: "danger",
                              onSelect: () => setDeleteTarget(endpoint),
                            },
                          ]}
                        />
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrapper>
        ) : null}
      </CardContent>

      {formOpen ? (
        <Dialog
          open
          onClose={() => setFormOpen(false)}
          title={editTarget ? t("models:endpoints.editTitle") : t("models:endpoints.createTitle")}
          footer={
            <>
              <Button variant="ghost" onClick={() => setFormOpen(false)}>
                {t("common:actions.cancel")}
              </Button>
              <Button
                onClick={() => (editTarget ? updateMutation.mutate() : createMutation.mutate())}
                loading={createMutation.isPending || updateMutation.isPending}
                disabled={!form.path.trim().startsWith("/")}
              >
                {t("common:actions.save")}
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <Field
              label={t("models:endpoints.path")}
              htmlFor="endpoint-path"
              required
              hint={t("models:endpoints.pathHint")}
            >
              <Input
                id="endpoint-path"
                technical
                value={form.path}
                onChange={(event) => setForm({ ...form, path: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("models:endpoints.method")} htmlFor="endpoint-method">
                <Select
                  id="endpoint-method"
                  value={form.method}
                  onChange={(event) => setForm({ ...form, method: event.target.value })}
                >
                  <option value="POST">POST</option>
                  <option value="GET">GET</option>
                </Select>
              </Field>
              <div className="flex items-end gap-3 pb-2">
                <Switch
                  checked={form.streamingSupported}
                  label={t("models:endpoints.streaming")}
                  onCheckedChange={(checked) => setForm({ ...form, streamingSupported: checked })}
                />
                <span className="text-xs">{t("models:endpoints.streaming")}</span>
              </div>
            </div>
            <Field
              label={t("models:endpoints.credential")}
              htmlFor="endpoint-credential"
              hint={t("models:endpoints.credentialHint")}
            >
              <Select
                id="endpoint-credential"
                value={form.credentialId}
                onChange={(event) => setForm({ ...form, credentialId: event.target.value })}
              >
                <option value="">{t("models:endpoints.credentialDefault")}</option>
                {credentials.map((credential) => (
                  <option key={credential.id} value={credential.id}>
                    {credential.label}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex items-center gap-3">
              <Switch
                checked={form.enabled}
                label={t("models:endpoints.enabled")}
                onCheckedChange={(checked) => setForm({ ...form, enabled: checked })}
              />
              <span className="text-xs">{t("models:endpoints.enabled")}</span>
            </div>
            {createMutation.error || updateMutation.error ? (
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
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title={t("models:endpoints.deleteTitle")}
        message={t("models:endpoints.deleteMessage", { path: deleteTarget?.path ?? "" })}
        confirmLabel={t("models:endpoints.deleteConfirm")}
      />
    </Card>
  );
}

export default EndpointsPanel;
