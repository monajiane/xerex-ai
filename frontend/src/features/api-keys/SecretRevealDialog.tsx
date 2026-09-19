/**
 * One-time secret display («کلید ساخته شد»).
 *
 * The backend returns the plaintext key exactly once; this dialog is the only place
 * it is ever visible, so it says so explicitly, offers a copy button, and cannot be
 * dismissed by accident (the close button stays available but the notice is part of
 * the dialog description rather than a toast that disappears).
 */
import { CopyButton } from "@/components/common/CopyButton";
import { Ltr } from "@/components/common/Ltr";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useTranslation } from "react-i18next";

import type { ApiKeyCreated } from "@/lib/api/types";

export interface SecretRevealDialogProps {
  apiKey: ApiKeyCreated | null;
  onClose: () => void;
}

export function SecretRevealDialog({ apiKey, onClose }: SecretRevealDialogProps) {
  const { t } = useTranslation(["apiKeys", "common"]);

  return (
    <Dialog
      open={apiKey !== null}
      onClose={onClose}
      title={t("apiKeys:secret.title")}
      description={t("apiKeys:secret.notice")}
      footer={
        <Button onClick={onClose}>{t("apiKeys:secret.done")}</Button>
      }
    >
      {apiKey ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm text-slate-600 dark:text-slate-300">
              {t("apiKeys:secret.label")}
            </span>
            <CopyButton
              value={apiKey.secret}
              label={t("common:actions.copy")}
              copiedLabel={t("apiKeys:secret.copied")}
            />
          </div>
          <div className="rounded-lg bg-slate-900 px-3 py-3 dark:bg-slate-950">
            <Ltr className="block break-all font-mono text-sm text-emerald-300">
              {apiKey.secret}
            </Ltr>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">{t("apiKeys:table.name")}</dt>
            <dd>{apiKey.name}</dd>
            <dt className="text-slate-500 dark:text-slate-400">{t("apiKeys:table.rateLimit")}</dt>
            <dd>
              <Ltr>{String(apiKey.rate_limit_per_min)}</Ltr>
            </dd>
          </dl>
        </div>
      ) : null}
    </Dialog>
  );
}

export default SecretRevealDialog;
