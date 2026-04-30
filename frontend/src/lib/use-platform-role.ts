import { ApiError } from "@/api/mutator";
import {
  type getMeApiV1UsersMeGetResponse,
  useGetMeApiV1UsersMeGet,
} from "@/api/generated/users/users";

export type PlatformRole = "owner" | "operator" | null;

export function usePlatformRole(isSignedIn: boolean | null | undefined) {
  const meQuery = useGetMeApiV1UsersMeGet<
    getMeApiV1UsersMeGetResponse,
    ApiError
  >({
    query: {
      enabled: Boolean(isSignedIn),
      refetchOnMount: "always",
      retry: false,
    },
  });

  const profile = meQuery.data?.status === 200 ? meQuery.data.data : null;
  const role = (profile?.platform_role ?? null) as PlatformRole;

  return {
    platformRole: role,
    isPlatformOwner: role === "owner",
    isPlatformOperator: role === "operator" || role === "owner",
    isLoading: meQuery.isLoading,
  };
}
