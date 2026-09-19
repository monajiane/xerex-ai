/**
 * Issue / edit dialog for a downstream API key («کلیدهای API»).
 *
 * The secret is never part of this form in edit mode: an issued key is immutable and
 * replacing it means revoking and issuing a new one. Scopes are checkboxes over the
 * three capabilities the gateway actually enforces (chat, embeddings, models).
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Switch } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { useErrorCopy } from "@/components/common/DataState";
import { apiKeysApi } from "@/lib/api/endpoints";
import type { ApiKey, ApiKeyCreated } from "@/lib/api/types";

const SCOPES = ["chat", "embeddings", "models"] as const;

/** A created key carries the one-time secret; an updated key does not. */
function isCreated(value: ApiKey | ApiKeyCreated): value is ApiKeyCreated {
  return typeof (value as ApiKeyCreated).secret === "string";
}

interface FormState {
  name: string;
  scopes: string[];
  rateLimit: string;
  quota: string;
  expiresAt: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  name: "",
  scopes: ["chat"],
  rateLimit: "60",
  quota: "",
  expiresAt: "",
  enabled: true,
};

export interface ApiKeyFormDialogProps {
  onClose: () => void;
  /** Present when editing; absent when issuing a new key. */
  apiKey?: ApiKey | null;
  onCreated: (created: ApiKeyCreated) => void;
}

function toForm(apiKey: ApiKey): FormState {
  return {
    name: apiKey.name,
    scopes: apiKey.scopes,
    rateLimit: String(apiKey.rate_limit_per_min),
    quota: apiKey.quota_tokens === null ? "" : String(apiKey.quota_tokens),
    expiresAt: apiKey.expires_at ? apiKey.expires_at.slice(0, 10) : "",
    enabled: apiKey.enabled,
  };
}

/** Mounted only while it is open, so the state below is initialised once, per open. */
export function ApiKeyFormDialog({ onClose, apiKey, onCreated }: ApiKeyFormDialogProps) {
  const { t } = useTranslation(["apiKeys", "common", "errors"]);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>(() => (apiKey ? toForm(apiKey) : EMPTY));
  const [error, setError] = useState<unknown>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(error);

  const toggleScope = (scope: string) => {
    setForm((current) => ({
      ...current,
      scopes: current.scopes.includes(scope)
        ? current.scopes.filter((entry) => entry !== scope)
        : [...current.scopes, scope],
    }));
  };

  const mutation = useMutation({
    mutationFn: async () => {
      const quota = form.quota.trim() === "" ? null : Number(form.quota);
      const expiresAt = form.expiresAt ? new Date(`${form.expiresAt}T00:00:00Z`).toISOString() : null;
      if (apiKey) {
        return apiKeysApi.update(apiKey.id, {
          name: form.name.trim(),
          scopes: form.scopes,
          rate_limit_per_min: Number(form.rateLimit),
          quota_tokens: quota,
          enabled: form.enabled,
          expires_at: expiresAt,
        });
      }
      return apiKeysApi.create({
        name: form.name.trim(),
        scopes: form.scopes,
        rate_limit_per_min: Number(form.rateLimit),
        quota_tokens: quota,
        expires_at: expiresAt,
      });
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      if (isCreated(result)) {
        onCreated(result);
      } else {
        toast.success(t("apiKeys:updated"));
        onClose();
      }
    },
    onError: (cause) => setError(cause),
  });

  const scopesValid = form.scopes.length > 0;

  return (
    <Dialog
      open
      onClose={onClose}
      title={apiKey ? t("apiKeys:editTitle") : t("apiKeys:createTitle")}
      description={apiKey ? t("apiKeys:editSubtitle") : t("apiKeys:createSubtitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || form.name.trim() === "" || !scopesValid}
          >
            {mutation.isPending ? t("common:saving") : t("common:actions.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label={t("apiKeys:form.name")} hint={t("apiKeys:form.nameHint")}>
          <Input
            id="api-key-name" aria-label={t("apiKeys:form.name")}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            autoComplete="off"
          />
        </Field>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("apiKeys:form.scopes")}
          </legend>
          <div className="flex flex-wrap gap-3">
            {SCOPES.map((scope) => (
              <label
                key={scope}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700"
              >
                <input
                  type="checkbox"
                  className="size-4"
                  checked={form.scopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                />
                <span>{t(`apiKeys:scope.${scope}`)}</span>
              </label>
            ))}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">{t("apiKeys:form.scopesHint")}</p>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("apiKeys:form.rateLimit")} hint={t("apiKeys:form.rateLimitHint")}>
            <Input
              id="api-key-rateLimit" aria-label={t("apiKeys:form.rateLimit")}
              value={form.rateLimit}
              inputMode="numeric"
              technical
              onChange={(event) => setForm({ ...form, rateLimit: event.target.value })}
            />
          </Field>
          <Field label={t("apiKeys:form.quota")} hint={t("apiKeys:form.quotaHint")}>
            <Input
              id="api-key-quota" aria-label={t("apiKeys:form.quota")}
              value={form.quota}
              inputMode="numeric"
              technical
              placeholder={t("common:optional")}
              onChange={(event) => setForm({ ...form, quota: event.target.value })}
            />
          </Field>
        </div>

        <Field label={t("apiKeys:form.expiresAt")} hint={t("apiKeys:form.expiresAtHint")}>
          <Input
            id="api-key-expires"
            aria-label={t("apiKeys:form.expiresAt")}
            type="date"
            value={form.expiresAt}
            technical
            onChange={(event) => setForm({ ...form, expiresAt: event.target.value })}
          />
        </Field>

        {apiKey ? (
          <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
            <span className="text-sm">{t("apiKeys:form.enabled")}</span>
            <Switch
              checked={form.enabled}
              label={t("apiKeys:form.enabled")}
              onCheckedChange={(enabled) => setForm({ ...form, enabled })}
            />
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
            {errorMessage}
            {errorCode ? <span dir="ltr" className="ms-2 font-mono text-xs opacity-70">({errorCode})</span> : null}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

export default ApiKeyFormDialog;
