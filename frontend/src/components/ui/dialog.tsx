/**
 * Accessible modal dialog implemented without third-party primitives.
 * The overlay closes on Escape and on backdrop click, and focus is moved into the
 * dialog when it opens so keyboard users are not left behind the modal.
 */
import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  className,
}: DialogProps) {
  const { t } = useTranslation("common");
  const titleId = useId();
  const descriptionId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    containerRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  const sizes = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-3xl" } as const;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative z-10 w-full rounded-2xl border app-divide bg-white shadow-xl dark:bg-slate-900",
          sizes[size],
          className,
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b app-divide px-5 py-4">
          <div className="text-start">
            <h2 id={titleId} className="text-base font-semibold">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="app-muted mt-1 text-xs leading-relaxed">
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("actions.close")}
            className="rounded-md p-1 app-muted hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 text-start">{children}</div>
        {footer ? (
          <footer className="flex flex-wrap items-center justify-start gap-2 border-t app-divide px-5 py-3 sm:justify-end">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}

export default Dialog;
