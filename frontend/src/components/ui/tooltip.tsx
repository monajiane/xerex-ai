/**
 * CSS-only tooltip.
 *
 * Persian explanation first, technical identifier second inside an LTR span —
 * e.g. «نقطه اتصال پایه ارائه‌دهنده (base_url)».
 */
import { cn } from "@/lib/utils";
import { Ltr } from "@/components/common/Ltr";

export interface TooltipProps {
  content: string;
  /** Optional English identifier shown in an LTR island after the Persian text. */
  technical?: string;
  children: React.ReactNode;
  className?: string;
}

export function Tooltip({ content, technical, children, className }: TooltipProps) {
  return (
    <span className={cn("group relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full start-1/2 z-50 mb-2 hidden w-max max-w-xs -translate-x-1/2 rounded-md bg-slate-900 px-2.5 py-1.5 text-start text-[0.6875rem] leading-relaxed text-white shadow-lg group-hover:block group-focus-within:block rtl:translate-x-1/2 dark:bg-slate-700"
      >
        {content}
        {technical ? (
          <>
            {" ("}
            <Ltr mono>{technical}</Ltr>
            {")"}
          </>
        ) : null}
      </span>
    </span>
  );
}

export default Tooltip;
