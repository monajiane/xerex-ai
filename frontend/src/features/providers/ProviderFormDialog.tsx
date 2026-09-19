/**
 * Provider create/edit form («افزودن ارائه‌دهنده» / «ویرایش ارائه‌دهنده»).
 *
 * The kind selector is fed by the backend catalog (`GET /catalog/providers`), so
 * the panel never invents provider kinds or default base URLs. Technical values
 * (base URL, slug) render LTR-isolated inside Persian labels (PROMPT.md 14.4).
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { Ltr } from "@/components/common/Ltr";
import { useErrorCopy } from "@/components/common/DataState";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { providersApi, systemApi } from "@/lib/api/endpoints";
import type { Provider, ProviderCreateInput, ProviderKind } from "@/lib/api/types";

interface FormState {
  name: string;
  kind: ProviderKind;
  baseUrl: string;
  slug: string;
  description: string;
  priority: string;
  weight: string;
  timeoutMs: string;
  maxRetries: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  name: "",
  kind: "openai",
  baseUrl: "",
  slug: "",
  description: "",
  priority: "100",
  weight: "100",
  timeoutMs: "30000",
  maxRetries: "2",
  enabled: true,
};

function toForm(provider: Provider): FormState {
  return {
    name: provider.name,
    kind: provider.kind,
    baseUrl: provider.base_url,
    slug: provider.slug,
    description: provider.description ?? "",
    priority: String(provider.priority),
    weight: String(provider.weight),
    timeoutMs: String(provider.timeout_ms),
    maxRetries: String(provider.max_retries),
    enabled: provider.enabled,
  };
}

export interface ProviderFormDialogProps {
  onClose: () => void;
  /** `null` creates a provider, an instance edits it. */
  provider: Provider | null;
}

/**
 * Mounted only while it is open, so the form state is initialised exactly once per
 * open — no state synchronisation effect, no stale values from a previous edit.
 */
export function ProviderFormDialog({ onClose, provider }: ProviderFormDialogProps) {
  const { t } = useTranslation(["providers", "common", "validation"]);
  const enums = useDynamicTranslation("enums");
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => (provider ? toForm(provider) : EMPTY));
  const [formError, setFormError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);
  const { message: errorMessage, code: errorCode } = useErrorCopy(formError);

  const catalogQuery = useQuery({
    queryKey: ["provider-catalog"],
    queryFn: () => systemApi.providerCatalog(),
    staleTime: 5 * 60 * 1000,
  });

  const selectedKind = useMemo(
    () => catalogQuery.data?.items.find((item) => item.kind === form.kind),
    [catalogQuery.data, form.kind],
  );

  // The documented default base URL of the selected kind comes from the backend
  // catalog; it is only a starting point and the administrator can overwrite it.
  const effectiveBaseUrl = form.baseUrl || (provider ? "" : (selectedKind?.default_base_url ?? ""));

  const createMutation = useMutation({
    mutationFn: (body: ProviderCreateInput) => providersApi.create(body),
    onSuccess: async () => {
      toast.success(t("providers:created"));
      onClose();
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
    onError: (error) => setFormError(error),
  });

  const updateMutation = useMutation({
    mutationFn: (body: ProviderCreateInput) => providersApi.update(provider!.id, body),
    onSuccess: async () => {
      toast.success(t("providers:updated"));
      onClose();
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      await queryClient.invalidateQueries({ queryKey: ["provider", provider!.id] });
    },
    onError: (error) => setFormError(error),
  });

  const pending = createMutation.isPending || updateMutation.isPending;
  const errors = touched ? validate({ ...form, baseUrl: effectiveBaseUrl }) : {};
  const hasCatalog = (catalogQuery.data?.items.length ?? 0) > 0;

  function submit() {
    setTouched(true);
    if (Object.keys(validate({ ...form, baseUrl: effectiveBaseUrl })).length > 0) return;
    const body: ProviderCreateInput = {
      name: form.name.trim(),
      kind: form.kind,
      base_url: effectiveBaseUrl.trim(),
      slug: form.slug.trim() || null,
      description: form.description.trim() || null,
      enabled: form.enabled,
      priority: Number(form.priority),
      weight: Number(form.weight),
      timeout_ms: Number(form.timeoutMs),
      max_retries: Number(form.maxRetries),
    };
    if (provider) updateMutation.mutate(body);
    else createMutation.mutate(body);
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={provider ? t("providers:editTitle") : t("providers:createTitle")}
      description={provider ? t("providers:editSubtitle") : t("providers:createSubtitle")}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {t("common:actions.cancel")}
          </Button>
          <Button onClick={submit} loading={pending} disabled={!hasCatalog}>
            {t("common:actions.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-4">
          <h3 className="text-xs font-semibold app-muted">{t("providers:form.sectionIdentity")}</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("providers:form.name")} htmlFor="provider-name" required hint={t("providers:form.nameHint")}>
              <Input
                id="provider-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                invalid={Boolean(errors.name)}
              />
            </Field>
            <Field
              label={t("providers:form.kind")}
              htmlFor="provider-kind"
              required
              hint={t("providers:form.kindHint")}
            >
              <Select
                id="provider-kind"
                value={form.kind}
                disabled={Boolean(provider)}
                onChange={(event) => setForm({ ...form, kind: event.target.value as ProviderKind })}
              >
                {(catalogQuery.data?.items ?? []).map((entry) => (
                  <option key={entry.kind} value={entry.kind}>
                    {enums.t(`providerKind.${entry.kind}`, { defaultValue: entry.display_name })}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label={t("providers:form.baseUrl")} htmlFor="provider-base-url" required hint={t("providers:form.baseUrlHint")}>
            <Input
              id="provider-base-url"
              technical
              value={effectiveBaseUrl}
              onChange={(event) => setForm({ ...form, baseUrl: event.target.value })}
              invalid={Boolean(errors.baseUrl)}
            />
          </Field>
          <Field label={t("providers:form.slug")} htmlFor="provider-slug" hint={t("providers:form.slugHint")}>
            <Input
              id="provider-slug"
              technical
              value={form.slug}
              disabled={Boolean(provider)}
              onChange={(event) => setForm({ ...form, slug: event.target.value })}
            />
          </Field>
          <Field label={t("providers:form.description")} htmlFor="provider-description">
            <Textarea
              id="provider-description"
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </Field>
        </section>

        <section className="flex flex-col gap-4">
          <h3 className="text-xs font-semibold app-muted">{t("providers:form.sectionRouting")}</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("providers:form.priority")} htmlFor="provider-priority" hint={t("providers:form.priorityHint")}>
              <Input
                id="provider-priority"
                type="number"
                min={0}
                max={10000}
                technical
                value={form.priority}
                onChange={(event) => setForm({ ...form, priority: event.target.value })}
              />
            </Field>
            <Field label={t("providers:form.weight")} htmlFor="provider-weight" hint={t("providers:form.weightHint")}>
              <Input
                id="provider-weight"
                type="number"
                min={0}
                max={10000}
                technical
                value={form.weight}
                onChange={(event) => setForm({ ...form, weight: event.target.value })}
              />
            </Field>
            <Field label={t("providers:form.timeout")} htmlFor="provider-timeout" hint={t("providers:form.timeoutHint")}>
              <Input
                id="provider-timeout"
                type="number"
                min={1000}
                max={600000}
                step={1000}
                technical
                value={form.timeoutMs}
                onChange={(event) => setForm({ ...form, timeoutMs: event.target.value })}
              />
            </Field>
            <Field
              label={t("providers:form.maxRetries")}
              htmlFor="provider-retries"
              hint={t("providers:form.maxRetriesHint")}
            >
              <Input
                id="provider-retries"
                type="number"
                min={0}
                max={10}
                technical
                value={form.maxRetries}
                onChange={(event) => setForm({ ...form, maxRetries: event.target.value })}
              />
            </Field>
          </div>
          <div className="flex items-start gap-3 rounded-lg border app-divide px-3 py-2.5">
            <Switch
              checked={form.enabled}
              onCheckedChange={(checked) => setForm({ ...form, enabled: checked })}
              label={t("providers:form.enabled")}
            />
            <p className="app-muted text-[0.6875rem] leading-relaxed">
              {t("providers:form.enabledHint")}
            </p>
          </div>
        </section>

        {selectedKind ? (
          <p className="app-muted flex flex-wrap items-center gap-1 text-[0.6875rem]">
            {enums.t(`providerKind.${selectedKind.kind}`, { defaultValue: selectedKind.display_name })}
            <span aria-hidden="true">·</span>
            <Ltr mono>{selectedKind.auth_scheme}</Ltr>
          </p>
        ) : null}

        {formError ? (
          <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
            {errorMessage}
            {errorCode ? (
              <>
                {" — "}
                <Ltr mono className="opacity-80">
                  {errorCode}
                </Ltr>
              </>
            ) : null}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

/** Client-side checks mirror the backend constraints; the API stays authoritative. */
function validate(form: FormState): Partial<Record<keyof FormState, boolean>> {
  const errors: Partial<Record<keyof FormState, boolean>> = {};
  if (!form.name.trim()) errors.name = true;
  if (!/^https?:\/\/.+/i.test(form.baseUrl.trim())) errors.baseUrl = true;
  return errors;
}

export default ProviderFormDialog;
