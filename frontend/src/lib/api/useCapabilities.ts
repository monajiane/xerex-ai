/**
 * Capability flags from `GET /api/v1/system/info`.
 *
 * The panel uses these to label planned modules honestly («در گام بعدی») instead
 * of rendering screens that look functional but are not.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { systemApi } from "@/lib/api/endpoints";
import type { Capability } from "@/lib/api/types";

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system", "info"],
    queryFn: ({ signal }) => systemApi.info(signal),
    staleTime: 5 * 60_000,
  });
}

export function useCapabilities() {
  const query = useSystemInfo();

  return useMemo(() => {
    const map = new Map<string, Capability>();
    for (const capability of query.data?.capabilities ?? []) {
      map.set(capability.key, capability);
    }
    return {
      isLoading: query.isPending,
      capabilities: map,
      isImplemented: (key: string) => map.get(key)?.state === "implemented",
      planOf: (key: string) => map.get(key)?.milestone ?? "",
      milestone: query.data?.milestone ?? "",
    };
  }, [query.data, query.isPending]);
}

export function useRoadmapModule(key: string) {
  const query = useQuery({
    queryKey: ["system", "roadmap"],
    queryFn: ({ signal }) => systemApi.roadmap(signal),
  });
  return {
    module: query.data?.modules.find((module) => module.key === key),
    isLoading: query.isPending,
    error: query.error,
    refetch: query.refetch,
  };
}
