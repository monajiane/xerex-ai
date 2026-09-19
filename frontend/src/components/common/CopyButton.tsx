import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export interface CopyButtonProps {
  value: string;
  label?: string;
  copiedLabel?: string;
  tone?: "default" | "onDark";
  className?: string;
}

export function CopyButton({
  value,
  label,
  copiedLabel,
  tone = "default",
  className,
}: CopyButtonProps) {
  const { t } = useTranslation("common");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      title={label ?? t("actions.copy")}
      aria-label={label ?? t("actions.copy")}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors",
        tone === "onDark"
          ? "text-slate-300 hover:bg-white/10"
          : "app-muted hover:bg-slate-100 dark:hover:bg-slate-800",
        className,
      )}
    >
      {copied ? (
        <Check className="size-3.5 text-emerald-500" aria-hidden="true" />
      ) : (
        <Copy className="size-3.5" aria-hidden="true" />
      )}
      <span>{copied ? (copiedLabel ?? t("actions.copied")) : (label ?? t("actions.copy"))}</span>
    </button>
  );
}

export default CopyButton;
