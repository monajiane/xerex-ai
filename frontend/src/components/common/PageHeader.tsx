import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
}

/** Page title block. Reads right-to-left: title first, actions at the inline end. */
export function PageHeader({ title, description, actions, badge, className }: PageHeaderProps) {
  return (
    <div
      className={cn("flex flex-wrap items-start justify-between gap-4 text-start", className)}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-bold sm:text-xl">{title}</h1>
          {badge}
        </div>
        {description ? (
          <p className="app-muted mt-1.5 max-w-3xl text-xs leading-relaxed sm:text-sm">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export default PageHeader;
