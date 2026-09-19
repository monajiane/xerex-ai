/**
 * API keys («کلیدهای API») — the downstream surface of the gateway.
 *
 * What the page shows and why:
 *  - the table lists the masked prefix only; the plaintext secret exists once, in the
 *    creation dialog, and is never fetched again;
 *  - «مصرف کلید» reads the aggregated per-attempt usage, so an operator can see the
 *    token quota, the cost and the error count of one key;
 *  - «ابطال» keeps the history, «حذف» removes it — the confirmation dialogs say so.
 */
import { useMemo, useState } from "react";
import { Ban, BarChart3, KeyRound, MoreHorizontal, Pencil, Plus, ShieldOff, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
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
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiKeyFormDialog } from "@/features/api-keys/ApiKeyFormDialog";
import { ApiKeyUsageDialog } from "@/features/api-keys/ApiKeyUsageDialog";
import { SecretRevealDialog } from "@/features/api-keys/SecretRevealDialog";
import { apiKeysApi } from "@/lib/api/endpoints";
import type { ApiKey, ApiKeyCreated } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

type StateFilter = "" | "active" | "disabled" | "revoked";

const GATEWAY_ROUTES = [
  "POST /v1/chat/completions",
  "POST /v1/completions",
  "POST /v1/embeddings",
  "GET /v1/models",
];

function keyState(apiKey: ApiKey): "active" | "disabled" | "revoked" | "expired" {
  if (apiKey.revoked_at) return "revoked";
  if (apiKey.expires_at && new Date(apiKey.expires_at).getTime() <= Date.now()) return "expired";
  return apiKey.enabled ? "active" : "disabled";
}

export function ApiKeysPage() {
  const { t } = useTranslation(["apiKeys", "common", "errors"]);
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const { digits, relative } = useLocale();

  const canManage = isRole("owner", "admin");

  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<StateFilter>("");
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ApiKey | null>(null);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [usageTarget, setUsageTarget] = useState<ApiKey | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ApiKey | null>(null);

  const params = useMemo(
    () => ({
      page: 1,
      page_size: 100,
      search: search.trim() || undefined,
      enabled: stateFilter === "active" ? true : stateFilter === "disabled" ? false : undefined,
      // Revoked keys stay visible: their consumption is the reason they exist.
      include_revoked: true,
    }),
    [search, stateFilter],
  );

  const keysQuery = useQuery({
    queryKey: ["api-keys", params],
    queryFn: ({ signal }) => apiKeysApi.list(params, signal),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
  };

  const toggleMutation = useMutation({
    mutationFn: ({ apiKey, enabled }: { apiKey: ApiKey; enabled: boolean }) =>
      apiKeysApi.update(apiKey.id, { enabled }),
    onSuccess: async (_data, variables) => {
      toast.success(variables.enabled ? t("apiKeys:enabledDone") : t("apiKeys:disabledDone"));
      await invalidate();
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (apiKey: ApiKey) => apiKeysApi.revoke(apiKey.id),
    onSuccess: async () => {
      toast.success(t("apiKeys:revoke.done"));
      setRevokeTarget(null);
      await invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (apiKey: ApiKey) => apiKeysApi.remove(apiKey.id),
    onSuccess: async () => {
      toast.success(t("apiKeys:delete.done"));
      setDeleteTarget(null);
      await invalidate();
    },
  });

  const keys = useMemo(() => {
    const items = keysQuery.data?.items ?? [];
    if (stateFilter === "revoked") return items.filter((key) => key.revoked_at !== null);
    if (stateFilter === "active") {
      return items.filter((key) => keyState(key) === "active");
    }
    if (stateFilter === "disabled") {
      return items.filter((key) => keyState(key) !== "active" && keyState(key) !== "revoked");
    }
    return items;
  }, [keysQuery.data, stateFilter]);

  const baseUrl = typeof window === "undefined" ? "/v1" : `${window.location.origin}/v1`;
  const example = `curl ${baseUrl}/chat/completions \\
  -H "Authorization: Bearer xrx_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"${t("apiKeys:usage.sampleMessage")}"}]}'`;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("apiKeys:title")}
        description={t("apiKeys:subtitle")}
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
              {t("apiKeys:addKey")}
            </Button>
          ) : null
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound aria-hidden="true" className="size-4" />
            {t("apiKeys:intro.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500 dark:text-slate-400">{t("apiKeys:intro.baseUrl")}:</span>
            <Ltr className="font-mono">{baseUrl}</Ltr>
          </div>
          <p className="text-slate-600 dark:text-slate-300">{t("apiKeys:intro.hint")}</p>
          <ul className="flex flex-wrap gap-2">
            {GATEWAY_ROUTES.map((route) => (
              <li key={route}>
                <Ltr className="rounded-md border border-slate-200 px-2 py-1 font-mono text-xs dark:border-slate-700">
                  {route}
                </Ltr>
              </li>
            ))}
          </ul>
          <pre
            dir="ltr"
            lang="en"
            className="ltr-block overflow-auto rounded-lg bg-slate-950/95 p-3 font-mono text-xs text-slate-100"
          >
            <code dir="ltr">{example}</code>
          </pre>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("apiKeys:searchPlaceholder")}
          className="max-w-xs"
          aria-label={t("common:actions.search")}
        />
        <Select
          value={stateFilter}
          onChange={(event) => setStateFilter(event.target.value as StateFilter)}
          aria-label={t("apiKeys:filterState")}
          className="max-w-40"
        >
          <option value="">{t("apiKeys:allStates")}</option>
          <option value="active">{t("apiKeys:stateActive")}</option>
          <option value="disabled">{t("apiKeys:stateDisabled")}</option>
          <option value="revoked">{t("apiKeys:stateRevoked")}</option>
        </Select>
      </div>

      {keysQuery.isPending ? (
        <LoadingState />
      ) : keysQuery.isError ? (
        <ErrorState error={keysQuery.error} onRetry={() => void keysQuery.refetch()} />
      ) : keys.length === 0 ? (
        <EmptyState title={t("apiKeys:empty")} hint={t("apiKeys:emptyHint")} />
      ) : (
        <TableWrapper>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("apiKeys:table.name")}</TableHead>
                <TableHead>{t("apiKeys:table.key")}</TableHead>
                <TableHead>{t("apiKeys:table.scopes")}</TableHead>
                <TableHead>{t("apiKeys:table.rateLimit")}</TableHead>
                <TableHead>{t("apiKeys:table.quota")}</TableHead>
                <TableHead>{t("apiKeys:table.lastUsed")}</TableHead>
                <TableHead>{t("apiKeys:table.state")}</TableHead>
                <TableHead className="text-end">{t("apiKeys:table.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((apiKey) => {
                const state = keyState(apiKey);
                const quota =
                  apiKey.quota_tokens === null ? (
                    t("common:notAvailable")
                  ) : (
                    <Ltr className="font-mono text-xs">
                      {`${digits(apiKey.quota_tokens)} ${t("common:units.tokens")}`}
                    </Ltr>
                  );
                return (
                  <TableRow key={apiKey.id}>
                    <TableCell className="font-medium">{apiKey.name}</TableCell>
                    <TableCell>
                      <Ltr className="font-mono text-xs">{apiKey.masked}</Ltr>
                    </TableCell>
                    <TableCell>
                      <span className="flex flex-wrap gap-1">
                        {apiKey.scopes.map((scope) => (
                          <Badge key={scope} tone="neutral">
                            {t(`apiKeys:scope.${scope}`, { defaultValue: scope })}
                          </Badge>
                        ))}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Ltr className="font-mono text-xs">{digits(apiKey.rate_limit_per_min)}</Ltr>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600 dark:text-slate-300">{quota}</TableCell>
                    <TableCell className="text-sm">
                      {apiKey.last_used_at ? relative(apiKey.last_used_at) : t("common:time.never")}
                    </TableCell>
                    <TableCell>
                      <StatusBadge domain="apiKeyState" value={state} />
                    </TableCell>
                    <TableCell className="text-end">
                      <Menu
                        menuLabel={t("apiKeys:table.actions")}
                        trigger={({ toggle, open }) => (
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t("apiKeys:table.actions")}
                            aria-expanded={open}
                            onClick={toggle}
                          >
                            <MoreHorizontal aria-hidden="true" />
                          </Button>
                        )}
                        items={[
                          {
                            label: t("apiKeys:actions.usage"),
                            icon: <BarChart3 aria-hidden="true" className="size-4" />,
                            onSelect: () => setUsageTarget(apiKey),
                          },
                          ...(canManage
                            ? [
                                {
                                  label: t("common:actions.edit"),
                                  icon: <Pencil aria-hidden="true" className="size-4" />,
                                  onSelect: () => {
                                    setEditTarget(apiKey);
                                    setFormOpen(true);
                                  },
                                },
                                {
                                  label: apiKey.enabled
                                    ? t("apiKeys:actions.disable")
                                    : t("apiKeys:actions.enable"),
                                  icon: <ShieldOff aria-hidden="true" className="size-4" />,
                                  onSelect: () =>
                                    toggleMutation.mutate({ apiKey, enabled: !apiKey.enabled }),
                                },
                                {
                                  label: t("apiKeys:actions.revoke"),
                                  icon: <Ban aria-hidden="true" className="size-4" />,
                                  tone: "danger" as const,
                                  disabled: apiKey.revoked_at !== null,
                                  onSelect: () => setRevokeTarget(apiKey),
                                },
                                {
                                  label: t("common:actions.delete"),
                                  icon: <Trash2 aria-hidden="true" className="size-4" />,
                                  tone: "danger" as const,
                                  onSelect: () => setDeleteTarget(apiKey),
                                },
                              ]
                            : []),
                        ]}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableWrapper>
      )}

      {keysQuery.data && keysQuery.data.total > 0 ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {t("common:table.total")}: <Ltr>{digits(keysQuery.data.total)}</Ltr>
        </p>
      ) : null}

      {formOpen ? (
        <ApiKeyFormDialog
          apiKey={editTarget}
          onClose={() => {
            setFormOpen(false);
            setEditTarget(null);
          }}
          onCreated={(result) => {
            setFormOpen(false);
            setEditTarget(null);
            setCreated(result);
          }}
        />
      ) : null}

      <SecretRevealDialog apiKey={created} onClose={() => setCreated(null)} />

      <ApiKeyUsageDialog apiKey={usageTarget} onClose={() => setUsageTarget(null)} />

      <ConfirmDialog
        open={revokeTarget !== null}
        title={t("apiKeys:revoke.title")}
        message={t("apiKeys:revoke.message", { name: revokeTarget?.name ?? "" })}
        details={[t("apiKeys:revoke.hint"), t("common:confirmDialog.irreversible")]}
        confirmLabel={t("apiKeys:revoke.confirm")}
        loading={revokeMutation.isPending}
        onConfirm={() => revokeTarget && revokeMutation.mutate(revokeTarget)}
        onClose={() => setRevokeTarget(null)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("apiKeys:delete.title")}
        message={t("apiKeys:delete.message", { name: deleteTarget?.name ?? "" })}
        details={[t("apiKeys:delete.hint"), t("common:confirmDialog.irreversible")]}
        confirmLabel={t("apiKeys:delete.confirm")}
        loading={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}

export default ApiKeysPage;
