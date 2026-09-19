/**
 * Model create/edit form («افزودن مدل» / «ویرایش مدل»).
 *
 * Pricing is entered per million tokens — exactly the unit the database stores, so
 * nothing is silently converted. Optional numbers stay empty when unknown: the
 * panel never invents a price.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Switch } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { Ltr } from "@/components/common/Ltr";
import { useErrorCopy } from "@/components/common/DataState";
import { useProvidersLookup } from "@/features/providers/useProviders";
import { modelsApi } from "@/lib/api/endpoints";
import type { Model, ModelCreateInput, ModelWriteInput } from "@/lib/api/types";

interface FormState {
  name: string;
  displayName: string;
  providerId: string;
  contextWindow: string;
  maxOutputTokens: string;
  inputPrice: string;
  outputPrice: string;
  capabilities: string;
  enabled: boolean;
  deprecated: boolean;
}

function emptyForm(providerId: string): FormState {
  return {
    name: "",
    displayName: "",
    providerId,
    contextWindow: "",
    maxOutputTokens: "",
    inputPrice: "",
    outputPrice: "",
    capabilities: "",
    enabled: true,
    deprecated: false,
  };
}

function toForm(model: Model): FormState {
  return {
    name: model.name,
    displayName: model.display_name ?? "",
    providerId: model.provider_id,
    contextWindow: model.context_window ? String(model.context_window) : "",
    maxOutputTokens: model.max_output_tokens ? String(model.max_output_tokens) : "",
    inputPrice: model.input_price_per_1m !== null ? String(model.input_price_per_1m) : "",
    outputPrice: model.output_price_per_1m !== null ? String(model.output_price_per_1m) : "",
    capabilities: model.capabilities
      ? Object.entries(model.capabilities)
          .filter(([, value]) => Boolean(value))
          .map(([key]) => key)
          .join(", ")
      : "",
    enabled: model.enabled,
    deprecated: model.deprecated,
  };
}

export interface ModelFormDialogProps {
  onClose: () => void;
  /** `null` creates a model, an instance edits it. */
  model: Model | null;
  /** Preselected provider when adding from a filtered list. */
  providerId?: string;
}

export function ModelFormDialog({ onClose, model, providerId }: ModelFormDialogProps) {
  const { t } = useTranslation(["models", "common"]);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const providers = useProvidersLookup();
  const [form, setForm] = useState<FormState>(() =>
    model ? toForm(model) : emptyForm(providerId ?? ""),
  );
  const [formError, setFormError] = useState<unknown>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(formError);

  const selectedProviderId = form.providerId || providers.providers[0]?.id || "";

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["models"] });
    if (model) await queryClient.invalidateQueries({ queryKey: ["model", model.id] });
  };

  const createMutation = useMutation({
    mutationFn: (body: ModelCreateInput) => modelsApi.create(body),
    onSuccess: async () => {
      toast.success(t("models:created"));
      onClose();
      await invalidate();
    },
    onError: (error) => setFormError(error),
  });

  const updateMutation = useMutation({
    mutationFn: (body: ModelWriteInput) => modelsApi.update(model!.id, body),
    onSuccess: async () => {
      toast.success(t("models:updated"));
      onClose();
      await invalidate();
    },
    onError: (error) => setFormError(error),
  });

  const pending = createMutation.isPending || updateMutation.isPending;

  function submit() {
    const capabilities = form.capabilities
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);
    const capabilityMap = capabilities.length
      ? Object.fromEntries(capabilities.map((entry) => [entry, true]))
      : null;
    const numbers = {
      context_window: form.contextWindow ? Number(form.contextWindow) : null,
      max_output_tokens: form.maxOutputTokens ? Number(form.maxOutputTokens) : null,
      input_price_per_1m: form.inputPrice ? Number(form.inputPrice) : null,
      output_price_per_1m: form.outputPrice ? Number(form.outputPrice) : null,
    };

    if (model) {
      updateMutation.mutate({
        ...numbers,
        display_name: form.displayName.trim() || null,
        capabilities: capabilityMap,
        enabled: form.enabled,
        deprecated: form.deprecated,
      });
      return;
    }
    createMutation.mutate({
      provider_id: selectedProviderId,
      name: form.name.trim(),
      display_name: form.displayName.trim() || null,
      capabilities: capabilityMap,
      enabled: form.enabled,
      deprecated: form.deprecated,
      ...numbers,
    });
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={model ? t("models:editTitle") : t("models:createTitle")}
      description={model ? t("models:editSubtitle") : t("models:createSubtitle")}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            onClick={submit}
            loading={pending}
            disabled={providers.providers.length === 0 || (!model && !form.name.trim())}
          >
            {t("common:actions.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-4">
          <h3 className="text-xs font-semibold app-muted">{t("models:form.sectionIdentity")}</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("models:form.provider")} htmlFor="model-provider" required>
              <Select
                id="model-provider"
                value={selectedProviderId}
                disabled={Boolean(model)}
                onChange={(event) => setForm({ ...form, providerId: event.target.value })}
              >
                {providers.providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label={t("models:form.name")}
              htmlFor="model-name"
              required
              hint={t("models:form.nameHint")}
            >
              <Input
                id="model-name"
                technical
                value={form.name}
                disabled={Boolean(model)}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <Field label={t("models:form.displayName")} htmlFor="model-display" hint={t("models:form.displayNameHint")}>
              <Input
                id="model-display"
                value={form.displayName}
                onChange={(event) => setForm({ ...form, displayName: event.target.value })}
              />
            </Field>
            <Field
              label={t("models:form.capabilities")}
              htmlFor="model-capabilities"
              hint={t("models:form.capabilitiesHint")}
            >
              <Input
                id="model-capabilities"
                technical
                value={form.capabilities}
                onChange={(event) => setForm({ ...form, capabilities: event.target.value })}
              />
            </Field>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h3 className="text-xs font-semibold app-muted">{t("models:form.sectionPricing")}</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("models:form.contextWindow")}
              htmlFor="model-context"
              hint={t("models:form.contextWindowHint")}
            >
              <Input
                id="model-context"
                type="number"
                min={1}
                technical
                value={form.contextWindow}
                onChange={(event) => setForm({ ...form, contextWindow: event.target.value })}
              />
            </Field>
            <Field label={t("models:form.maxOutputTokens")} htmlFor="model-max-output">
              <Input
                id="model-max-output"
                type="number"
                min={1}
                technical
                value={form.maxOutputTokens}
                onChange={(event) => setForm({ ...form, maxOutputTokens: event.target.value })}
              />
            </Field>
            <Field label={t("models:form.inputPrice")} htmlFor="model-input-price">
              <Input
                id="model-input-price"
                type="number"
                min={0}
                step="0.0001"
                technical
                value={form.inputPrice}
                onChange={(event) => setForm({ ...form, inputPrice: event.target.value })}
              />
            </Field>
            <Field label={t("models:form.outputPrice")} htmlFor="model-output-price">
              <Input
                id="model-output-price"
                type="number"
                min={0}
                step="0.0001"
                technical
                value={form.outputPrice}
                onChange={(event) => setForm({ ...form, outputPrice: event.target.value })}
              />
            </Field>
          </div>
          <p className="app-muted text-[0.6875rem] leading-relaxed">{t("models:form.pricingHint")}</p>
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold app-muted">{t("models:form.sectionState")}</h3>
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-3">
              <Switch
                checked={form.enabled}
                label={t("models:form.enabled")}
                onCheckedChange={(checked) => setForm({ ...form, enabled: checked })}
              />
              <span className="text-xs">{t("models:form.enabled")}</span>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                checked={form.deprecated}
                label={t("models:form.deprecated")}
                onCheckedChange={(checked) => setForm({ ...form, deprecated: checked })}
              />
              <span className="text-xs">{t("models:form.deprecated")}</span>
            </div>
          </div>
          <p className="app-muted text-[0.6875rem] leading-relaxed">{t("models:form.deprecatedHint")}</p>
        </section>

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

export default ModelFormDialog;
