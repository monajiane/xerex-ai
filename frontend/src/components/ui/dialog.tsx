/**
 * Accessible modal dialog implemented without third-party primitives.
 *
 * Keyboard contract (M7):
 *  - opening moves focus into the dialog, preferring the first control inside it;
 *  - `Tab`/`Shift+Tab` cycle **inside** the dialog and never reach the page behind it;
 *  - `Escape` and the backdrop close it;
 *  - closing returns focus to the element that opened it, so a keyboard user continues
 *    from the button they pressed instead of the top of the document.
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
    const opener = document.activeElement as HTMLElement | null;

    const focusables = (): HTMLElement[] => {
      const root = containerRef.current;
      if (!root) return [];
      return Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
            'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.offsetParent !== null || element === document.activeElement);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        // Nothing to focus inside: keep the dialog itself as the focus target.
        event.preventDefault();
        containerRef.current?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const inside = containerRef.current?.contains(active ?? null) ?? false;
      if (!inside) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && (active === first || active === containerRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Prefer the first interactive control; fall back to the dialog container itself so
    // screen readers announce the title immediately.
    const [firstFocusable] = focusables();
    (firstFocusable ?? containerRef.current)?.focus();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (opener && document.contains(opener)) opener.focus();
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
