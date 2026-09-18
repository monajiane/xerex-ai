/**
 * Audit trail.
 *
 * Technical identifiers (request id, IP, entity id) are rendered inside LTR
 * isolation islands; raw JSON opens in a strict LTR viewer (PROMPT.md 14.4).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrapper,
} from "@/components/ui/table";
import { CodeBlock } from "@/components/common/CodeBlock";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { auditApi } from "@/lib/api/endpoints";
import type { AuditLogEntry } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";
import { useAuth } from "@/features/auth/AuthProvider";

export function AuditLogsPage() {
  const { t } = useTranslation(["auditLogs", "common", "errors"]);
  const audit = useDynamicTranslation("auditLogs");
  const { dateTime, relative } = useLocale();
  const { isRole } = useAuth();
  const [selected, setSelected] = useState<AuditLogEntry | null>(null);

  const canReadLogs = isRole("owner", "admin");

  const auditQuery = useQuery({
    queryKey: ["audit-logs"],
    queryFn: ({ signal }) => auditApi.list({ page: 1, page_size: 50 }, signal),
    enabled: canReadLogs,
  });

  if (!canReadLogs) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={t("auditLogs:title")} description={t("auditLogs:subtitle")} />
        <EmptyState title={t("errors:insufficient_role")} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("auditLogs:title")} description={t("auditLogs:subtitle")} />

      {auditQuery.isPending ? <LoadingState /> : null}
      {auditQuery.isError ? (
        <ErrorState error={auditQuery.error} onRetry={() => void auditQuery.refetch()} />
      ) : null}

      {auditQuery.data ? (
        auditQuery.data.items.length === 0 ? (
          <EmptyState title={t("auditLogs:empty")} />
        ) : (
          <Card className="overflow-hidden">
            <CardContent className="px-0 py-0">
              <TableWrapper className="rounded-none border-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("auditLogs:tableTime")}</TableHead>
                      <TableHead>{t("auditLogs:tableActor")}</TableHead>
                      <TableHead>{t("auditLogs:tableAction")}</TableHead>
                      <TableHead>{t("auditLogs:tableEntity")}</TableHead>
                      <TableHead>{t("auditLogs:tableIp")}</TableHead>
                      <TableHead>{t("auditLogs:tableRequestId")}</TableHead>
                      <TableHead>{t("common:actions.details")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {auditQuery.data.items.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell className="whitespace-nowrap text-xs" title={dateTime(entry.created_at)}>
                          {relative(entry.created_at)}
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.actor_email ? (
                            <Ltr>{entry.actor_email}</Ltr>
                          ) : (
                            <span className="app-muted">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge tone={entry.action === "login_failed" ? "danger" : "brand"}>
                            {audit.t(`actions.${entry.action}`, { defaultValue: entry.action })}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.entity_type ? (
                            <Ltr mono>{entry.entity_id ?? entry.entity_type}</Ltr>
                          ) : (
                            <span className="app-muted">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.ip_address ? <Ltr mono>{entry.ip_address}</Ltr> : "—"}
                        </TableCell>
                        <TableCell className="text-xs">
                          {entry.request_id ? (
                            <Ltr mono>{entry.request_id}</Ltr>
                          ) : (
                            <span className="app-muted">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelected(entry)}
                            disabled={!entry.diff}
                          >
                            {t("common:actions.details")}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableWrapper>
            </CardContent>
          </Card>
        )
      ) : null}

      <Dialog
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={t("auditLogs:detailTitle")}
        description={selected?.request_id ?? undefined}
      >
        {selected ? (
          <div className="flex flex-col gap-3 text-xs">
            <DetailRow label={t("auditLogs:tableAction")}>
              {audit.t(`actions.${selected.action}`, { defaultValue: selected.action })}
            </DetailRow>
            <DetailRow label={t("auditLogs:tableActor")}>
              <Ltr>{selected.actor_email ?? "—"}</Ltr>
            </DetailRow>
            <DetailRow label={t("auditLogs:tableIp")}>
              <Ltr mono>{selected.ip_address ?? "—"}</Ltr>
            </DetailRow>
            <DetailRow label={t("common:build.serverTime")}>{dateTime(selected.created_at)}</DetailRow>
            {selected.diff ? (
              <CodeBlock value={JSON.stringify(selected.diff, null, 2)} language="json" />
            ) : null}
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b app-divide pb-2 last:border-0">
      <span className="app-muted">{label}</span>
      <span>{children}</span>
    </div>
  );
}

export default AuditLogsPage;
