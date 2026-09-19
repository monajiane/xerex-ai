/**
 * Shared provider lookup.
 *
 * Models, endpoints and (later) routing rules all need provider names next to a
 * `provider_id`. One cached query keeps that honest — the panel never invents a
 * display name and never issues one request per row.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { providersApi } from "@/lib/api/endpoints";
import type { Provider } from "@/lib/api/types";

export interface ProvidersLookup {
  providers: Provider[];
  byId: Map<string, Provider>;
  nameOf: (providerId: string | null | undefined) => string;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

export function useProvidersLookup(): ProvidersLookup {
  const query = useQuery({
    queryKey: ["providers", "lookup"],
    queryFn: ({ signal }) => providersApi.list({ page: 1, page_size: 100, order_by: "name" }, signal),
    staleTime: 30_000,
  });

  const providers = useMemo(() => query.data?.items ?? [], [query.data]);
  const byId = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  );

  return {
    providers,
    byId,
    nameOf: (providerId) => (providerId ? (byId.get(providerId)?.name ?? providerId) : "—"),
    isLoading: query.isPending,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}
