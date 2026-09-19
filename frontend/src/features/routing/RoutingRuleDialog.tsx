/**
 * Create / edit one routing rule.
 *
 * A rule is deliberately small: a name pattern (or "all models"), a strategy and a
 * priority. Anything the engine cannot evaluate is rejected by the API with
 * `routing_conditions_invalid`, and that code is shown instead of a generic failure.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Switch } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { useErrorCopy } from "@/components/common/DataState";
import { routingApi } from "@/lib/api/endpoints";
import type { RoutingCatalogItem } from "@/lib/api/types";
import type { RoutingRule } from "@/lib/api/types";

export interface RoutingRuleDialogProps {
  rule: RoutingRule | null;
  strategies: RoutingCatalogItem[];
  onClose: () => void;
}

export function RoutingRuleDialog({ rule, strategies, onClose }: RoutingRuleDialogProps) {
  const { t } = useTranslation(["routing", "common", "errors"]);
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  const [name, setName] = useState(rule?.name ?? "");
  const [pattern, setPattern] = useState(
    (rule?.match_conditions?.model as string | undefined) ?? "",
  );
  const [strategy, setStrategy] = useState(rule?.strategy ?? "priority");
  const [priority, setPriority] = useState(String(rule?.priority ?? 100));
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [error, setError] = useState<unknown>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(error);

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(),
        strategy,
        priority: Number(priority),
        enabled,
        match_conditions: pattern.trim() ? { model: pattern.trim() } : {},
      };
      return rule ? routingApi.rules.update(rule.id, body) : routingApi.rules.create(body);
    },
    onSuccess: async () => {
      toast.success(rule ? t("routing:rules.updated") : t("routing:rules.created"));
      await queryClient.invalidateQueries({ queryKey: ["routing", "rules"] });
      onClose();
    },
    onError: (cause) => setError(cause),
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={rule ? t("routing:rules.editTitle") : t("routing:rules.createTitle")}
      description={rule ? t("routing:rules.editSubtitle") : t("routing:rules.createSubtitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || name.trim() === ""}
          >
            {mutation.isPending ? t("common:saving") : t("common:actions.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label={t("routing:rules.name")}>
          <Input
            id="routing-rule-name"
            aria-label={t("routing:rules.name")}
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
          />
        </Field>

        <Field label={t("routing:rules.modelPattern")} hint={t("routing:rules.modelPatternHint")}>
          <Input
            id="routing-rule-pattern"
            aria-label={t("routing:rules.modelPattern")}
            value={pattern}
            technical
            placeholder="gpt-4o*"
            onChange={(event) => setPattern(event.target.value)}
            autoComplete="off"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("routing:rules.strategy")}>
            <Select
              aria-label={t("routing:rules.strategy")}
              value={strategy}
              onChange={(event) => setStrategy(event.target.value as RoutingRule["strategy"])}
            >
              {strategies.map((spec) => (
                <option key={spec.strategy} value={spec.strategy}>
                  {spec.strategy}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("routing:rules.priority")} hint={t("routing:rules.priorityHint")}>
            <Input
              id="routing-rule-priority"
              aria-label={t("routing:rules.priority")}
              value={priority}
              inputMode="numeric"
              technical
              onChange={(event) => setPriority(event.target.value)}
            />
          </Field>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
          <span className="text-sm">{t("routing:rules.enabled")}</span>
          <Switch
            checked={enabled}
            label={t("routing:rules.enabled")}
            onCheckedChange={setEnabled}
          />
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
          >
            {errorMessage}
            {errorCode ? (
              <span dir="ltr" className="ms-2 font-mono text-xs opacity-70">
                ({errorCode})
              </span>
            ) : null}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

export default RoutingRuleDialog;
