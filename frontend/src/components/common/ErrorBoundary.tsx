/**
 * Last-resort boundary. The administrator sees a Persian message plus the raw
 * error digest, never a raw stack trace (PROMPT.md 14.8).
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { Ltr } from "@/components/common/Ltr";

interface BoundaryProps {
  children: ReactNode;
  title: string;
  message: string;
  retryLabel: string;
}

interface State {
  error: Error | null;
}

class Boundary extends Component<BoundaryProps, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // English log line: logs are never Persian (PROMPT.md section 10).
    console.error("ui_error_boundary", {
      message: error.message,
      componentStack: info.componentStack,
    });
  }

  render() {
    const { error } = this.state;
    const { t } = { t: undefined } as never; // placeholder, never used
    void t;
    if (!error) return this.props.children;

    return (
      <div className="grid min-h-screen place-items-center p-6">
        <div className="app-card max-w-md p-6 text-center">
          <h1 className="text-base font-semibold">{this.props.title}</h1>
          <p className="app-muted mt-2 text-xs leading-relaxed">{this.props.message}</p>
          <Ltr mono className="mt-3 block text-[0.6875rem] text-slate-500">
            {`${error.name}: ${error.message}`}
          </Ltr>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className={`mt-4 ${buttonVariants({ size: "sm" })}`}
          >
            {this.props.retryLabel}
          </button>
        </div>
      </div>
    );
  }
}

export function ErrorBoundary({ children }: { children: ReactNode }) {
  const { t } = useTranslation(["errors", "common"]);
  return (
    <Boundary
      title={t("errors:title")}
      message={t("errors:internal_error")}
      retryLabel={t("errors:retry")}
    >
      {children}
    </Boundary>
  );
}

export default ErrorBoundary;
