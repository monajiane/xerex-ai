/**
 * Persian confirmation dialog for destructive actions (PROMPT.md 14.7).
 *
 * Every destructive action in the panel goes through this component so that the
 * wording, the danger colouring and the keyboard behaviour are identical
 * everywhere: the confirm button states exactly what happens, never just «OK».
 */
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  /** Main question, translated and already interpolated by the caller. */
  message: string;
  /** Extra consequence lines (impact counts, cascade effects). */
  details?: string[];
  /** Wording of the confirming button, e.g. «حذف ارائه‌دهنده». */
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  tone?: "danger" | "warning";
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  details,
  confirmLabel,
  cancelLabel,
  loading = false,
  tone = "danger",
}: ConfirmDialogProps) {
  const { t } = useTranslation("common");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel ?? t("actions.cancel")}
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel ?? t("actions.confirm")}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={
            tone === "danger"
              ? "mt-0.5 rounded-full bg-rose-50 p-2 text-rose-600 dark:bg-rose-950/60 dark:text-rose-300"
              : "mt-0.5 rounded-full bg-amber-50 p-2 text-amber-600 dark:bg-amber-950/60 dark:text-amber-300"
          }
        >
          <AlertTriangle className="size-4" />
        </span>
        <div className="flex flex-col gap-2 text-sm">
          <p className="font-medium">{message}</p>
          {details?.length ? (
            <ul className="flex flex-col gap-1 text-xs leading-relaxed app-muted">
              {details.map((detail) => (
                <li key={detail} className="flex gap-1.5">
                  <span aria-hidden="true">•</span>
                  <span>{detail}</span>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-rose-600 dark:text-rose-300">{t("confirmDialog.irreversible")}</p>
        </div>
      </div>
    </Dialog>
  );
}

export default ConfirmDialog;
