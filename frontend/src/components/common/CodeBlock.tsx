/**
 * Strict LTR block for code, JSON, URLs and logs (PROMPT.md 14.4).
 * `unicode-bidi: isolate-override` guarantees that not a single character is
 * reordered, even when the block is embedded in a Persian layout.
 */
import { CopyButton } from "@/components/common/CopyButton";
import { cn } from "@/lib/utils";

export interface CodeBlockProps {
  value: string;
  language?: string;
  maxHeight?: string;
  className?: string;
  copyLabel?: string;
  copiedLabel?: string;
}

export function CodeBlock({
  value,
  language,
  maxHeight = "22rem",
  className,
  copyLabel,
  copiedLabel,
}: CodeBlockProps) {
  return (
    <div className={cn("relative rounded-lg border app-divide bg-slate-950/95", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-1.5">
        <span dir="ltr" lang="en" className="ltr-isolate font-mono text-[0.6875rem] text-slate-400">
          {language ?? "json"}
        </span>
        <CopyButton value={value} label={copyLabel} copiedLabel={copiedLabel} tone="onDark" />
      </div>
      <pre
        dir="ltr"
        lang="en"
        className="ltr-block m-0 overflow-auto p-3 text-[0.8125rem] leading-relaxed text-slate-100"
        style={{ maxHeight }}
      >
        <code dir="ltr">{value}</code>
      </pre>
    </div>
  );
}

export default CodeBlock;
