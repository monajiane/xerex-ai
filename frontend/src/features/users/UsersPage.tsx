/**
 * Administrator management.
 *
 * RBAC is enforced by the API; the panel additionally hides actions the current
 * role cannot perform (defence in depth, never the only defence).
 */
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrapper,
} from "@/components/ui/table";
import { useToastHelpers } from "@/components/ui/toast";
import { EmptyState, ErrorState, LoadingState, useErrorCopy } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAuth } from "@/features/auth/AuthProvider";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { usersApi } from "@/lib/api/endpoints";
import type { AdminRole } from "@/lib/api/types";
import { useLocale } from "@/lib/locale/LocaleProvider";

const ASSIGNABLE_ROLES: AdminRole[] = ["admin", "operator", "viewer"];

export function UsersPage() {
  const { t } = useTranslation(["users", "common"]);
  const usersNs = useDynamicTranslation("users");
  const enums = useDynamicTranslation("enums");
  const { dateTime, relative } = useLocale();
  const { isRole } = useAuth();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    fullName: "",
    email: "",
    password: "",
    role: "viewer" as AdminRole,
  });
  const [formError, setFormError] = useState<unknown>(null);
  const { message: formErrorMessage, code: formErrorCode } = useErrorCopy(formError);

  const canManage = isRole("owner", "admin");

  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: ({ signal }) => usersApi.list({ page: 1, page_size: 50 }, signal),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      usersApi.create({
        email: form.email,
        password: form.password,
        full_name: form.fullName || undefined,
        role: form.role,
      }),
    onSuccess: async () => {
      toast.success(t("users:created"));
      setDialogOpen(false);
      setForm({ fullName: "", email: "", password: "", role: "viewer" });
      setFormError(null);
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => setFormError(error),
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("users:title")}
        description={t("users:subtitle")}
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              <UserPlus aria-hidden="true" />
              {t("users:addUser")}
            </Button>
          ) : null
        }
      />

      {usersQuery.isPending ? <LoadingState /> : null}
      {usersQuery.isError ? (
        <ErrorState error={usersQuery.error} onRetry={() => void usersQuery.refetch()} />
      ) : null}

      {usersQuery.data ? (
        usersQuery.data.items.length === 0 ? (
          <EmptyState title={t("users:empty")} />
        ) : (
          <Card className="overflow-hidden">
            <CardContent className="px-0 py-0">
              <TableWrapper className="rounded-none border-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("users:tableName")}</TableHead>
                      <TableHead>{t("users:tableEmail")}</TableHead>
                      <TableHead>{t("users:tableRole")}</TableHead>
                      <TableHead>{t("users:tableStatus")}</TableHead>
                      <TableHead>{t("users:tableLastLogin")}</TableHead>
                      <TableHead>{t("users:tableCreatedAt")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {usersQuery.data.items.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell className="font-medium">{user.full_name ?? "—"}</TableCell>
                        <TableCell>
                          <Ltr>{user.email}</Ltr>
                        </TableCell>
                        <TableCell>
                          <Badge tone={user.role === "owner" ? "brand" : "neutral"}>
                            {enums.t(`role.${user.role}`, { defaultValue: user.role })}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <StatusBadge domain="userStatus" value={user.status} showRawValue />
                        </TableCell>
                        <TableCell className="app-muted text-xs">
                          {user.last_login_at ? (
                            <span title={dateTime(user.last_login_at)}>
                              {relative(user.last_login_at)}
                            </span>
                          ) : (
                            t("common:never")
                          )}
                        </TableCell>
                        <TableCell className="app-muted text-xs">
                          {dateTime(user.created_at)}
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
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={t("users:createTitle")}
        description={t("users:createSubtitle")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              {t("common:actions.cancel")}
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!form.email || form.password.length < 10}
            >
              {t("users:addUser")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label={t("users:tableName")} htmlFor="user-name">
            <Input
              id="user-name"
              value={form.fullName}
              onChange={(event) => setForm({ ...form, fullName: event.target.value })}
            />
          </Field>
          <Field label={t("users:tableEmail")} htmlFor="user-email" required>
            <Input
              id="user-email"
              type="email"
              technical
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>
          <Field
            label={t("users:passwordLabel")}
            htmlFor="user-password"
            hint={t("users:passwordHint")}
            required
          >
            <Input
              id="user-password"
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
          </Field>
          <Field label={t("users:roleLabel")} htmlFor="user-role">
            <Select
              id="user-role"
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as AdminRole })}
            >
              {ASSIGNABLE_ROLES.map((role) => (
                <option key={role} value={role}>
                  {usersNs.t(`roles.${role}`, { defaultValue: role })}
                </option>
              ))}
            </Select>
          </Field>
          <p className="app-muted text-[0.6875rem] leading-relaxed">
            {usersNs.t(`roleHints.${form.role}`)}
          </p>
          {formError ? (
            <p role="alert" className="text-xs text-rose-600 dark:text-rose-300">
              {formErrorMessage}
              {formErrorCode ? (
                <>
                  {" — "}
                  <Ltr mono className="opacity-80">
                    {formErrorCode}
                  </Ltr>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      </Dialog>
    </div>
  );
}

export default UsersPage;
