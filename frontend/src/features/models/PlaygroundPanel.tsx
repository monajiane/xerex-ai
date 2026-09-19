/**
 * «آزمایش مدل» — the playground.
 *
 * One prompt goes through the real adapter. The panel shows the answer, the real
 * token counts, the latency and — when the provider refuses — the stable error code
 * inside an LTR badge. Streaming uses Server-Sent Events and renders the answer as
 * it arrives; if the model cannot stream, the panel says so instead of inventing
 * an answer.
 */
import { useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Switch, Textarea } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { Ltr } from "@/components/common/Ltr";
import { useErrorCopy } from "@/components/common/DataState";
import { modelsApi } from "@/lib/api/endpoints";
import { readEventStream } from "@/lib/api/client";
import type { Model, ModelTestResult } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

export interface PlaygroundPanelProps {
  model: Model;
  /** Operators and administrators may run the playground; viewers only read. */
  canRun: boolean;
}

export function PlaygroundPanel({ model, canRun }: PlaygroundPanelProps) {
  const { t } = useTranslation(["models", "common", "errors"]);
  const toast = useToastHelpers();
  const { digits, cost, duration } = useLocale();

  const [prompt, setPrompt] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [maxTokens, setMaxTokens] = useState("256");
  const [stream, setStream] = useState(true);
  const [result, setResult] = useState<ModelTestResult | null>(null);
  const [streamedText, setStreamedText] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { message: errorMessage, code: errorCode } = useErrorCopy(error);

  const estimatedCost =
    result && result.error_code === null
      ? ((model.input_price_per_1m ?? 0) * result.input_tokens +
          (model.output_price_per_1m ?? 0) * result.output_tokens) /
        1_000_000
      : null;

  async function run() {
    if (!prompt.trim()) {
      toast.error(t("models:playground.needPrompt"));
      return;
    }
    setRunning(true);
    setError(null);
    setResult(null);
    setStreamedText("");

    const body = {
      prompt,
      temperature: Number(temperature),
      max_tokens: Number(maxTokens),
    };

    if (!stream) {
      try {
        setResult(await modelsApi.test(model.id, body));
      } catch (caught) {
        setError(caught);
      } finally {
        setRunning(false);
      }
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await modelsApi.testStream(model.id, { ...body, stream: true });
      const summary: ModelTestResult = {
        model_id: model.id,
        provider_id: model.provider_id,
        latency_ms: 0,
        input_tokens: 0,
        output_tokens: 0,
        output_text: "",
        finish_reason: null,
        error_code: null,
      };
      let text = "";
      for await (const event of readEventStream(response)) {
        if (typeof event.delta === "string") {
          text += event.delta;
          setStreamedText(text);
        }
        if (event.done) {
          summary.latency_ms = Number(event.latency_ms ?? 0);
          summary.output_tokens = Number(event.output_tokens ?? 0);
          summary.error_code = (event.error_code as string | null) ?? null;
          summary.finish_reason = (event.finish_reason as string | null) ?? null;
        }
      }
      summary.output_text = text;
      if (summary.error_code) {
        // Streaming is optional per endpoint: fall back to the full answer once.
        const fallback = await modelsApi.test(model.id, body);
        if (fallback.error_code === "provider_streaming_unsupported") {
          setResult(fallback);
          toast.info(t("models:playground.streamUnsupported"));
        } else {
          setResult({ ...fallback, output_text: fallback.output_text || text });
        }
      } else {
        setResult(summary);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      abortRef.current = null;
      setRunning(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
  }

  const output = running && stream ? streamedText : (result?.output_text ?? streamedText);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("models:playground.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <p className="app-muted text-xs leading-relaxed">{t("models:playground.subtitle")}</p>

        <Field label={t("models:playground.prompt")} htmlFor="playground-prompt" required>
          <Textarea
            id="playground-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={t("models:playground.promptPlaceholder")}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label={t("models:playground.temperature")}
            htmlFor="playground-temperature"
            hint={t("models:playground.temperatureHint")}
          >
            <Input
              id="playground-temperature"
              type="number"
              min={0}
              max={2}
              step="0.1"
              technical
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
            />
          </Field>
          <Field label={t("models:playground.maxTokens")} htmlFor="playground-max-tokens">
            <Input
              id="playground-max-tokens"
              type="number"
              min={1}
              max={8192}
              technical
              value={maxTokens}
              onChange={(event) => setMaxTokens(event.target.value)}
            />
          </Field>
          <div className="flex items-end gap-3 pb-2">
            <Switch checked={stream} label={t("models:playground.stream")} onCheckedChange={setStream} />
            <span className="text-xs">{t("models:playground.stream")}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => void run()} loading={running} disabled={!canRun}>
            <Play aria-hidden="true" />
            {running ? t("models:playground.running") : t("models:playground.run")}
          </Button>
          {running ? (
            <Button variant="secondary" onClick={stop}>
              <Square aria-hidden="true" />
              {t("common:actions.cancel")}
            </Button>
          ) : null}
        </div>

        {error ? (
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

        {result || streamedText ? (
          <div className="flex flex-col gap-3">
            {result?.error_code ? (
              <p
                role="alert"
                className="rounded-lg border border-rose-200 bg-rose-50/70 px-3 py-2 text-xs dark:border-rose-900 dark:bg-rose-950/40"
              >
                {t("models:playground.errorTitle")} — <Ltr mono>{result.error_code}</Ltr>
              </p>
            ) : null}

            <div>
              <p className="app-muted mb-1 text-[0.6875rem]">{t("models:playground.output")}</p>
              <pre
                dir="auto"
                className="max-h-80 overflow-auto rounded-lg border app-divide bg-slate-50 px-3 py-2 text-sm whitespace-pre-wrap dark:bg-slate-900"
              >
                {output || t("models:playground.outputEmpty")}
              </pre>
            </div>

            {result && result.error_code === null ? (
              <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <Metric label={t("models:playground.latency")} value={duration(result.latency_ms)} />
                <Metric label={t("models:playground.inputTokens")} value={digits(result.input_tokens)} />
                <Metric
                  label={t("models:playground.outputTokens")}
                  value={result.output_tokens ? digits(result.output_tokens) : t("common:notAvailable")}
                />
                {estimatedCost !== null &&
                (model.input_price_per_1m !== null || model.output_price_per_1m !== null) ? (
                  <Metric
                    label={t("models:playground.cost")}
                    value={cost(estimatedCost)}
                    hint={t("models:playground.costHint")}
                  />
                ) : null}
              </dl>
            ) : null}

            {result?.finish_reason ? (
              <p className="app-muted text-[0.6875rem]">
                {t("models:playground.finishReason")}: <Ltr mono>{result.finish_reason}</Ltr>
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <dt className="app-muted text-[0.6875rem]">{label}</dt>
      <dd className="font-mono text-sm">{value}</dd>
    </div>
  );
}

export default PlaygroundPanel;
