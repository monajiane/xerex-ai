/**
 * Loading / error / empty states.
 *
 * Error text is derived from the stable English `error.code` returned by the API
 * and translated in the panel (PROMPT.md 14.5) — the raw code always stays visible
 * inside an LTR badge so an administrator can quote it in a bug report.
 */
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useDynamicTranslation } from "@/i18n/dynamic";
import { Button } from "@/components/ui/button";
import { Ltr } from "@/components/common/Ltr";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

export function useErrorCopy(error: unknown): {
  message: string;
  code: string | null;
  requestId: string | null;
} {
  const { t: tError } = useTranslation("errors");
  const dynamic = useDynamicTranslation("errors");

  if (error instanceof ApiError) {
    const details = error.details as { min_length?: number } | null;
    const message = dynamic.t(error.code, {
      defaultValue: "",
      min_length: details?.min_length ?? 10,
    });
    return {
      message: message || tError("generic"),
      code: error.code,
      requestId: error.requestId,
    };
  }
  return { message: tError("generic"), code: null, requestId: null };
}

export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const { t } = useTranslation("errors");
  const { message, code, requestId } = useErrorCopy(error);

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50/70 px-6 py-10 text-center dark:border-rose-900 dark:bg-rose-950/40",
        className,
      )}
    >
      <AlertTriangle className="size-6 text-rose-600 dark:text-rose-300" aria-hidden="true" />
      <p className="text-sm font-medium text-rose-900 dark:text-rose-100">{message}</p>
      <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-rose-800/80 dark:text-rose-200/80">
        {code ? (
          <span className="flex items-center gap-1">
            {t("errorCode")}: <Ltr mono>{code}</Ltr>
          </span>
        ) : null}
        {requestId ? (
          <span className="flex items-center gap-1">
            {t("requestId")}: <Ltr mono>{requestId}</Ltr>
          </span>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {t("retry")}
        </Button>
      ) : null}
    </div>
  );
}

export function LoadingState({ label, className }: { label?: string; className?: string }) {
  const { t } = useTranslation("states");
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex items-center justify-center gap-2 py-12 text-sm app-muted", className)}
    >
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      <span>{label ?? t("loadingTitle")}</span>
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title?: string;
  hint?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  const { t } = useTranslation("states");
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed app-divide px-6 py-12 text-center",
        className,
      )}
    >
      <Inbox className="size-6 app-muted" aria-hidden="true" />
      <p className="text-sm font-medium">{title ?? t("emptyTitle")}</p>
      {hint ? <p className="app-muted max-w-lg text-xs leading-relaxed">{hint}</p> : null}
      {action}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-700/60", className)}
    />
  );
}
