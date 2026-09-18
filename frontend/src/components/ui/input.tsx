/**
 * Form controls.
 *
 * Labels and helper text are aligned with `text-start`, so they sit on the right
 * edge in Persian and on the left edge in English without a single directional
 * utility (PROMPT.md 14.2).
 */
import { forwardRef, useId } from "react";

import { cn } from "@/lib/utils";

const fieldBase =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition-colors placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:placeholder:text-slate-500 dark:disabled:bg-slate-800";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  /** Technical fields (keys, ids, URLs) render LTR inside the input. */
  technical?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, technical = false, dir, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      dir={technical ? "ltr" : dir}
      aria-invalid={invalid || undefined}
      className={cn(
        fieldBase,
        technical && "ltr-isolate font-mono text-[0.8125rem]",
        invalid && "border-rose-400 focus:border-rose-500 focus:ring-rose-500/20",
        className,
      )}
      {...props}
    />
  );
});

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, "min-h-24 resize-y", invalid && "border-rose-400", className)}
      {...props}
    />
  );
});

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, "appearance-none", invalid && "border-rose-400", className)}
      {...props}
    >
      {children}
    </select>
  );
});

export interface FieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function Field({ label, htmlFor, hint, error, required, children, className }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5 text-start", className)}>
      <label htmlFor={htmlFor} className="text-xs font-medium">
        {label}
        {required ? (
          <span aria-hidden="true" className="text-rose-500 ms-1">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
          {error}
        </p>
      ) : hint ? (
        <p className="app-muted text-[0.6875rem] leading-relaxed">{hint}</p>
      ) : null}
    </div>
  );
}

export function useFieldId(prefix: string): string {
  const id = useId();
  return `${prefix}-${id}`;
}

export function Switch({
  checked,
  onCheckedChange,
  label,
  disabled,
  className,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-600",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-4 rounded-full bg-white transition-transform",
          // Logical transform: moves toward the inline end in both directions.
          checked ? "translate-x-0 rtl:-translate-x-5 ltr:translate-x-5" : "ltr:translate-x-1 rtl:-translate-x-1",
        )}
      />
    </button>
  );
}
