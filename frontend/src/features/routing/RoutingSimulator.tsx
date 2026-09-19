/**
 * Dry-run simulator («شبیه‌سازی مسیریابی»).
 *
 * No request leaves the platform: the backend resolves the candidates and runs the
 * routing engine, then returns the order **and the reason for every position**. The
 * reason tokens are stable English; this component is where they become Persian, so a
 * new engine reason is a translation entry, not a code change in the engine.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrapper,
} from "@/components/ui/table";
import { EmptyState, useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { routingApi } from "@/lib/api/endpoints";
import type { RoutingCatalogItem } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

export interface RoutingSimulatorProps {
  strategies: RoutingCatalogItem[];
}

export function RoutingSimulator({ strategies }: RoutingSimulatorProps) {
  const { t } = useTranslation(["routing", "common", "errors"]);
  const { digits, n, cost, duration } = useLocale();

  const [model, setModel] = useState("");
  const [strategy, setStrategy] = useState("");
  const [tokens, setTokens] = useState("1000");
  const [error, setError] = useState<unknown>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(error);

  const mutation = useMutation({
    mutationFn: () =>
      routingApi.simulate({
        model: model.trim(),
        strategy: strategy ? (strategy as RoutingCatalogItem["strategy"]) : undefined,
        requested_tokens: Number(tokens) || 0,
      }),
    onSuccess: () => setError(null),
    onError: (cause) => setError(cause),
  });

  const result = mutation.data;

  /** Renders one engine reason token as Persian, falling back to the raw token. */
  const reasonCopy = (reason: string): string => {
    const [key, rawValue] = reason.split("=");
    // Numeric values are Persian digits inside the Persian sentence; tokens without a
    // value (``no_price_data``) keep their raw form.
    const value = rawValue !== undefined && /^-?\d+(\.\d+)?$/.test(rawValue) ? digits(rawValue) : (rawValue ?? "");
    return t(`routing:reason.${key}`, { value, defaultValue: reason });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-1.5 text-start">
          <label htmlFor="routing-sim-model" className="text-xs font-medium">
            {t("routing:simulate.model")}
          </label>
          <Input
            id="routing-sim-model"
            value={model}
            technical
            placeholder={t("routing:simulate.modelPlaceholder")}
            onChange={(event) => setModel(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5 text-start">
          <label htmlFor="routing-sim-strategy" className="text-xs font-medium">
            {t("routing:simulate.strategy")}
          </label>
          <Select
            id="routing-sim-strategy"
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
          >
            <option value="">{t("routing:simulate.useRule")}</option>
            {strategies.map((spec) => (
              <option key={spec.strategy} value={spec.strategy}>
                {spec.strategy}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5 text-start">
          <label htmlFor="routing-sim-tokens" className="text-xs font-medium">
            {t("routing:simulate.tokens")}
          </label>
          <Input
            id="routing-sim-tokens"
            value={tokens}
            inputMode="numeric"
            technical
            onChange={(event) => setTokens(event.target.value)}
          />
          <span className="app-muted text-[0.6875rem]">{t("routing:simulate.tokensHint")}</span>
        </div>
        <div className="flex items-end">
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={model.trim() === ""}
          >
            {t("routing:simulate.run")}
          </Button>
        </div>
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

      {mutation.isPending ? null : result === undefined ? (
        <EmptyState title={t("routing:simulate.empty")} hint={t("routing:simulate.emptyHint")} />
      ) : result.candidates.length === 0 ? (
        <EmptyState
          title={t("routing:simulate.noCandidates")}
          hint={t("routing:simulate.noCandidatesHint")}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone="info">
              {t("routing:simulate.resultTitle")} — {result.strategy}
            </Badge>
            {result.rule_name ? <Badge tone="neutral">{result.rule_name}</Badge> : null}
            <span className="text-slate-500 dark:text-slate-400">
              {t("routing:simulate.selected")}: {result.candidates[0]?.provider_name}
            </span>
          </div>

          <TableWrapper>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("routing:simulate.candidate")}</TableHead>
                  <TableHead>{t("common:status.label")}</TableHead>
                  <TableHead>{t("routing:simulate.latency")}</TableHead>
                  <TableHead>{t("routing:simulate.price")}</TableHead>
                  <TableHead>{t("routing:simulate.estimatedCost")}</TableHead>
                  <TableHead>{t("routing:simulate.reasons")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.candidates.map((candidate) => (
                  <TableRow key={`${candidate.provider_id}-${candidate.model_id}`}>
                    <TableCell>
                      <span className="flex flex-col">
                        <span className="font-medium">{candidate.provider_name}</span>
                        <Ltr className="font-mono text-xs text-slate-500 dark:text-slate-400">
                          {candidate.model_name ?? ""}
                        </Ltr>
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge tone={candidate.eligible ? "success" : "danger"}>
                        {candidate.eligible
                          ? t("routing:simulate.eligible")
                          : t("routing:simulate.excluded")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Ltr className="font-mono text-xs">
                        {candidate.latency_ms === null
                          ? t("common:notAvailable")
                          : duration(candidate.latency_ms)}
                      </Ltr>
                    </TableCell>
                    <TableCell>
                      <Ltr className="font-mono text-xs">
                        {candidate.price_per_1m === null
                          ? t("common:notAvailable")
                          : cost(candidate.price_per_1m)}
                      </Ltr>
                    </TableCell>
                    <TableCell>
                      <Ltr className="font-mono text-xs">
                        {candidate.estimated_cost === null
                          ? t("common:notAvailable")
                          : cost(candidate.estimated_cost)}
                      </Ltr>
                    </TableCell>
                    <TableCell>
                      <span className="flex flex-wrap gap-1">
                        {candidate.reasons.length === 0 ? (
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {t("common:notAvailable")}
                          </span>
                        ) : (
                          candidate.reasons.map((reason) => (
                            <Badge key={reason} tone="neutral">
                              {reasonCopy(reason)}
                            </Badge>
                          ))
                        )}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrapper>

          <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <summary className="cursor-pointer text-sm font-medium">
              {t("routing:simulate.explanation")}
            </summary>
            <ul className="mt-2 flex flex-wrap gap-2 text-xs">
              {result.explanation.map((entry) => (
                <li key={entry}>
                  <Ltr className="font-mono">{entry}</Ltr>
                </li>
              ))}
            </ul>
            <p className="app-muted mt-2 text-xs">
              {t("routing:simulate.tokens")}: <Ltr className="font-mono">{n(Number(tokens) || 0)}</Ltr>
            </p>
          </details>
        </div>
      )}
    </div>
  );
}

export default RoutingSimulator;
