import type { LucideIcon } from "lucide-react";

import { Ltr } from "@/components/common/Ltr";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface StatCardProps {
  label: string;
  /** Pre-formatted, locale aware value. */
  value: string;
  hint?: string;
  unit?: string;
  icon?: LucideIcon;
  /** Technical raw value shown in an LTR container (e.g. exact token count). */
  technicalValue?: string;
  available?: boolean;
  emptyLabel?: string;
  className?: string;
}

export function StatCard({
  label,
  value,
  hint,
  unit,
  icon: Icon,
  technicalValue,
  available = true,
  emptyLabel,
  className,
}: StatCardProps) {
  return (
    <Card className={cn("p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="app-muted text-xs">{label}</p>
          <p className="mt-2 text-xl font-bold tracking-tight">
            {available ? value : <span className="app-muted text-sm">{emptyLabel}</span>}
            {available && unit ? <span className="app-muted ms-1 text-xs font-normal">{unit}</span> : null}
          </p>
          {available && technicalValue ? (
            <p className="mt-1 text-[0.6875rem] app-muted">
              <Ltr mono>{technicalValue}</Ltr>
            </p>
          ) : null}
          {hint ? <p className="app-muted mt-1 text-[0.6875rem]">{hint}</p> : null}
        </div>
        {Icon ? (
          <span className="rounded-lg bg-brand-50 p-2 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300">
            <Icon className="size-4" aria-hidden="true" />
          </span>
        ) : null}
      </div>
    </Card>
  );
}

export default StatCard;
