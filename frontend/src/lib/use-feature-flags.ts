"use client";

import { useQuery } from "@tanstack/react-query";
import { customFetch } from "@/api/mutator";

export type FeatureFlags = Record<string, boolean>;

interface FeatureFlagsResponse {
  data: { feature_flags: FeatureFlags };
  status: number;
}

export function useFeatureFlags(enabled = true) {
  const query = useQuery<FeatureFlags>({
    queryKey: ["feature-flags"],
    queryFn: async () => {
      const res: FeatureFlagsResponse = await customFetch(
        "/api/v1/organization-settings/feature-flags",
        { method: "GET" },
      );
      return res.data.feature_flags;
    },
    enabled,
    staleTime: 60_000,
    refetchOnMount: "always",
    retry: 2,
    retryDelay: 1000,
  });

  return {
    flags: query.data ?? ({} as FeatureFlags),
    isLoading: query.isLoading || (query.isError && !query.data),
    isFeatureEnabled: (flag: string) => query.data?.[flag] ?? false,
  };
}
