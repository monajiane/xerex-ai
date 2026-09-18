/**
 * Honest placeholder for modules that are planned but not implemented yet.
 *
 * The panel never fabricates provider or model data (see the M1 brief). Instead of
 * a fake table, an administrator sees:
 *   - the milestone that will deliver the module,
 *   - what the module will do (Persian copy from the i18n layer),
 *   - the planned API contract, rendered with LTR isolation.
 */
import { Construction } from "lucide-react";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Ltr } from "@/components/common/Ltr";
import { ErrorState, LoadingState } from "@/components/common/DataState";
import { PageHeader } from "@/components/common/PageHeader";
import { useDynamicTranslation } from "@/i18n/dynamic";
import { systemApi } from "@/lib/api/endpoints";
import type { RoadmapModule } from "@/lib/api/types";

export type PlaceholderModuleKey =
  | "providers"
  | "credentials"
  | "models"
  | "apiKeys"
  | "routing"
  | "usage"
  | "logs"
  | "gateway";

export interface PlaceholderModuleProps {
  moduleKey: PlaceholderModuleKey;
  /** Key of the module in the backend roadmap, when it differs from the UI key. */
  roadmapKey?: string;
}

export function PlaceholderModule({ moduleKey, roadmapKey }: PlaceholderModuleProps) {
  const { t } = useTranslation(["roadmap", "common"]);
  const roadmap = useDynamicTranslation("roadmap");
  const enums = useDynamicTranslation("enums");
  const copyKey = `modules.${moduleKey}` as const;

  const roadmapQuery = useQuery({
    queryKey: ["system", "roadmap"],
    queryFn: ({ signal }) => systemApi.roadmap(signal),
  });

  const roadmapModule: RoadmapModule | undefined = useMemo(() => {
    const wanted = roadmapKey ?? moduleKey;
    return roadmapQuery.data?.modules.find((module) => module.key === wanted);
  }, [roadmapQuery.data, moduleKey, roadmapKey]);

  const title = roadmap.t(`${copyKey}.title`, { defaultValue: moduleKey });
  const description = roadmap.t(`${copyKey}.description`);
  const milestone = roadmapModule?.milestone ?? "M2";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={title}
        description={description}
        badge={
          <Badge tone="info">
            <Construction className="size-3.5" aria-hidden="true" />
            {t("badge")}
          </Badge>
        }
      />

      <Card>
        <CardHeader>
          <div className="text-start">
            <CardTitle>{t("title")}</CardTitle>
            <CardDescription>{t("description", { milestone })}</CardDescription>
          </div>
          <Badge tone="neutral">
            <span>{enums.t("capabilityState.planned")}</span>
          </Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="app-muted text-xs leading-relaxed">{t("noFakeData")}</p>

          {roadmapQuery.isPending ? <LoadingState /> : null}
          {roadmapQuery.isError ? (
            <ErrorState error={roadmapQuery.error} onRetry={() => void roadmapQuery.refetch()} />
          ) : null}

          {roadmapModule ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold">{t("plannedEndpoints")}</h3>
              <ul className="flex flex-col gap-2">
                {roadmapModule.endpoints.map((endpoint) => (
                  <li
                    key={`${endpoint.method}-${endpoint.path}`}
                    className="flex flex-wrap items-center gap-2 rounded-lg border app-divide px-3 py-2"
                  >
                    <Badge tone="brand">
                      <Ltr mono>{endpoint.method}</Ltr>
                    </Badge>
                    <Ltr mono className="text-xs">
                      {endpoint.path}
                    </Ltr>
                    <span className="app-muted text-[0.6875rem]">{endpoint.summary}</span>
                    <Badge tone="neutral" className="ms-auto">
                      <Ltr mono>{endpoint.milestone}</Ltr>
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default PlaceholderModule;
