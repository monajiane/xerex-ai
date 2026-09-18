import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

/**
 * A 4xx response is a deterministic answer, so retrying it only hides the real
 * error from the administrator. Network and 5xx failures are retried once.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 1;
      },
    },
    mutations: { retry: false },
  },
});
