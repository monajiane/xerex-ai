/**
 * Settings.
 *
 * Editable settings are persisted through `PUT /api/v1/settings/{key}` and every
 * change is audited by the API. Environment-owned values are shown read-only, so
 * the panel never pretends to control what only the deployment can change.
 */
import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/input";
import { useToastHelpers } from "@/components/ui/toast";
import { ErrorState, LoadingState } from "@/components/common/DataState";
import { Ltr } from "@/components/common/Ltr";
import { PageHeader } from "@/components/common/PageHeader";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { settingsApi, systemApi } from "@/lib/api/endpoints";
import { useLocale } from "@/lib/locale/LocaleProvider";
import { useTheme, type ThemePreference } from "@/lib/theme/ThemeProvider";

const SECTIONS: Array<{ key: string; labelKey: string; settingKeys: string[] }> = [
  {
    key: "presentation",
    labelKey: "sectionPresentation",
    settingKeys: ["ui.default_locale", "ui.numeral_style", "ui.theme", "ui.timezone"],
  },
  {
    key: "notifications",
    labelKey: "sectionNotifications",
    settingKeys: ["notifications.email_enabled", "notifications.health_alerts"],
  },
  {
    key: "retention",
    labelKey: "sectionRetention",
    settingKeys: ["retention.usage_days", "retention.logs_days"],
  },
];

export function SettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const settingsNs = useDynamicTranslation("settings");
  const { dateTime, setLocale } = useLocale();
  const { setTheme } = useTheme();
  const toast = useToastHelpers();
  const queryClient = useQueryClient();

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: ({ signal }) => settingsApi.bundle(signal),
  });
  const infoQuery = useQuery({
    queryKey: ["system", "info"],
    queryFn: ({ signal }) => systemApi.info(signal),
  });

  const values = useMemo(() => {
    const map = new Map<string, unknown>();
    settingsQuery.data?.items.forEach((item) => map.set(item.key, item.value));
    return map;
  }, [settingsQuery.data]);

  const updateMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => settingsApi.update(key, value),
    onSuccess: async () => {
      toast.success(t("settings:saveSuccess"));
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      await queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
    },
    onError: () => toast.error(t("settings:saveError")),
  });

  const update = (key: string, value: unknown) => {
    updateMutation.mutate({ key, value });
    if (key === "ui.theme") setTheme(value as ThemePreference);
    if (key === "ui.default_locale") {
      setLocale(String(value) === "en" ? "en" : "fa");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("settings:title")} description={t("settings:subtitle")} />

      {settingsQuery.isPending ? <LoadingState /> : null}
      {settingsQuery.isError ? (
        <ErrorState error={settingsQuery.error} onRetry={() => void settingsQuery.refetch()} />
      ) : null}

      {settingsQuery.data
        ? SECTIONS.map((section) => (
            <Card key={section.key}>
              <CardHeader>
                <CardTitle>{settingsNs.t(section.labelKey)}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                {section.settingKeys.map((key) => {
                  const item = settingsQuery.data.items.find((entry) => entry.key === key);
                  if (!item) return null;
                  const fieldLabel = settingsNs.t(`fields.${key}.label`, { defaultValue: key });
                  const fieldHint = settingsNs.t(`fields.${key}.hint`);
                  const value = values.get(key);

                  if (typeof value === "boolean") {
                    return (
                      <div
                        key={key}
                        className="flex items-start justify-between gap-4 border-b app-divide pb-4 last:border-0"
                      >
                        <div className="text-start">
                          <p className="text-xs font-medium">{fieldLabel}</p>
                          <p className="app-muted mt-1 text-[0.6875rem] leading-relaxed">{fieldHint}</p>
                        </div>
                        <Switch
                          checked={value}
                          label={fieldLabel}
                          disabled={!item.editable || updateMutation.isPending}
                          onCheckedChange={(checked) => update(key, checked)}
                        />
                      </div>
                    );
                  }

                  if (key === "ui.default_locale") {
                    return (
                      <Field key={key} label={fieldLabel} hint={fieldHint} htmlFor={`setting-${key}`}>
                        <Select
                          id={`setting-${key}`}
                          value={String(value ?? "fa")}
                          disabled={!item.editable || updateMutation.isPending}
                          onChange={(event) => update(key, event.target.value)}
                        >
                          <option value="fa">{t("common:language.fa")}</option>
                          <option value="en">{t("common:language.en")}</option>
                        </Select>
                      </Field>
                    );
                  }

                  if (key === "ui.numeral_style") {
                    return (
                      <Field key={key} label={fieldLabel} hint={fieldHint} htmlFor={`setting-${key}`}>
                        <Select
                          id={`setting-${key}`}
                          value={String(value ?? "persian")}
                          disabled={!item.editable || updateMutation.isPending}
                          onChange={(event) => update(key, event.target.value)}
                        >
                          <option value="persian">{t("settings:numeralStyles.persian")}</option>
                          <option value="latin">{t("settings:numeralStyles.latin")}</option>
                        </Select>
                      </Field>
                    );
                  }

                  if (key === "ui.theme") {
                    return (
                      <Field key={key} label={fieldLabel} hint={fieldHint} htmlFor={`setting-${key}`}>
                        <Select
                          id={`setting-${key}`}
                          value={String(value ?? "system")}
                          disabled={!item.editable || updateMutation.isPending}
                          onChange={(event) => update(key, event.target.value)}
                        >
                          <option value="light">{t("common:theme.light")}</option>
                          <option value="dark">{t("common:theme.dark")}</option>
                          <option value="system">{t("common:theme.system")}</option>
                        </Select>
                      </Field>
                    );
                  }

                  return (
                    <Field
                      key={key}
                      label={fieldLabel}
                      hint={fieldHint}
                      htmlFor={`setting-${key}`}
                    >
                      <Input
                        id={`setting-${key}`}
                        technical={key === "ui.timezone"}
                        defaultValue={String(value ?? "")}
                        disabled={!item.editable || updateMutation.isPending}
                        onBlur={(event) => {
                          if (event.target.value !== String(value ?? "")) {
                            update(key, key === "ui.timezone" ? event.target.value : Number(event.target.value));
                          }
                        }}
                      />
                    </Field>
                  );
                })}
              </CardContent>
            </Card>
          ))
        : null}

      <Card>
        <CardHeader>
          <div className="text-start">
            <CardTitle>{t("settings:sectionEnvironment")}</CardTitle>
            <CardDescription>{t("settings:environmentNotice")}</CardDescription>
          </div>
          <Badge tone="neutral">{t("settings:readOnlyBadge")}</Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-xs">
          <EnvRow label={t("settings:environmentKeys.apiPrefix")} value="/api/v1" />
          <EnvRow
            label={t("settings:environmentKeys.defaultLocale")}
            value={infoQuery.data?.localization.default_locale ?? "fa"}
          />
          <EnvRow
            label={t("settings:environmentKeys.locales")}
            value={(infoQuery.data?.localization.supported_locales ?? ["fa", "en"]).join(", ")}
          />
          <EnvRow
            label={t("settings:environmentKeys.timezone")}
            value={infoQuery.data?.localization.default_timezone ?? "Asia/Tehran"}
          />
          <EnvRow
            label={t("common:build.version")}
            value={`${infoQuery.data?.version ?? "0.1.0"} · ${infoQuery.data?.milestone ?? "M1"}`}
          />
          <p className="app-muted mt-1 text-[0.6875rem]">
            {t("settings:savedAt", {
              time: dateTime(settingsQuery.dataUpdatedAt || null) || t("settings:notSavedYet"),
            })}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function EnvRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b app-divide pb-2 last:border-0">
      <span className="app-muted">{label}</span>
      <Ltr mono>{value}</Ltr>
    </div>
  );
}

export default SettingsPage;
