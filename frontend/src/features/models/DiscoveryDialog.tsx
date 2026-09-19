/**
 * «کشف مدل‌ها» — reads the provider catalogue and reconciles it with the registry.
 *
 * The dialog reports the real counters returned by the API (discovered / created /
 * updated / unchanged / failed) instead of a vague success message, and the
 * upstream failure code in an LTR badge when the provider refuses.
 */
import { useState } from "react";
import { Radar } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Select, Switch } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { EmptyState, useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { useProvidersLookup } from "@/features/providers/useProviders";
import { modelsApi } from "@/lib/api/endpoints";
import type { ModelDiscoveryResult } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

export interface DiscoveryDialogProps {
  onClose: () => void;
  /** Provider preselected from the list filter, when any. */
  providerId?: string;
}

export function DiscoveryDialog({ onClose, providerId }: DiscoveryDialogProps) {
  const { t } = useTranslation(["models", "common", "errors"]);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const providers = useProvidersLookup();
  const [selected, setSelected] = useState(providerId ?? "");
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState<ModelDiscoveryResult | null>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(null);

  const effectiveProviderId = selected || providers.providers[0]?.id || "";

  const discoveryMutation = useMutation({
    mutationFn: () =>
      modelsApi.discover({ provider_id: effectiveProviderId, overwrite_existing: overwrite }),
    onSuccess: async (data) => {
      setResult(data);
      toast.success(t("models:discover.done"));
      await queryClient.invalidateQueries({ queryKey: ["models"] });
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const failure = discoveryMutation.error;
  const { message: failureMessage, code: failureCode } = useErrorCopy(failure);

  return (
    <Dialog
      open
      onClose={onClose}
      title={t("models:discover.title")}
      description={t("models:discover.subtitle")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("common:actions.close")}
          </Button>
          <Button
            onClick={() => discoveryMutation.mutate()}
            loading={discoveryMutation.isPending}
            disabled={!effectiveProviderId}
          >
            <Radar aria-hidden="true" />
            {t("models:discover.run")}
          </Button>
        </>
      }
    >
      {providers.providers.length === 0 ? (
        <EmptyState title={t("models:discover.needProvider")} />
      ) : (
        <div className="flex flex-col gap-5">
          <Field label={t("models:discover.provider")} htmlFor="discover-provider" required>
            <Select
              id="discover-provider"
              value={effectiveProviderId}
              onChange={(event) => {
                setSelected(event.target.value);
                setResult(null);
              }}
            >
              {providers.providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </Select>
          </Field>

          <div className="flex items-start gap-3 rounded-lg border app-divide px-3 py-2.5">
            <Switch
              checked={overwrite}
              label={t("models:discover.overwrite")}
              onCheckedChange={setOverwrite}
            />
            <div className="flex flex-col">
              <span className="text-xs font-medium">{t("models:discover.overwrite")}</span>
              <span className="app-muted text-[0.6875rem] leading-relaxed">
                {t("models:discover.overwriteHint")}
              </span>
            </div>
          </div>

          {discoveryMutation.isPending ? (
            <p role="status" className="app-muted text-xs">
              {t("models:discover.running")}
            </p>
          ) : null}

          {result ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-3 text-xs dark:border-emerald-900 dark:bg-emerald-950/40">
              <p className="font-medium">{t("models:discover.resultTitle")}</p>
              <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Counter label={t("models:discover.discovered")} value={result.discovered} />
                <Counter label={t("models:discover.created")} value={result.created} />
                <Counter label={t("models:discover.updated")} value={result.updated} />
                <Counter label={t("models:discover.skipped")} value={result.skipped} />
                <Counter label={t("models:discover.failed")} value={result.failed} />
              </dl>
            </div>
          ) : null}

          {failure ? (
            <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
              {failureMessage || errorMessage}
              {failureCode || errorCode ? (
                <>
                  {" — "}
                  <Ltr mono className="opacity-80">
                    {failureCode ?? errorCode}
                  </Ltr>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      )}
    </Dialog>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  const { digits } = useLocale();
  return (
    <div className="flex flex-col">
      <dt className="app-muted text-[0.6875rem]">{label}</dt>
      <dd className="font-mono text-sm">{digits(value)}</dd>
    </div>
  );
}

export default DiscoveryDialog;
