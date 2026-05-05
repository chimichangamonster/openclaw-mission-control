/**
 * use-org-members — minimal hook returning the org's member roster shaped for
 * UI dropdowns (assignee picker etc). Wraps the generated Orval hook and
 * flattens to `{user_id, name, email}` so callers don't deal with the raw
 * embedded `user` object.
 */

import { useMemo } from "react";

import { ApiError } from "@/api/mutator";
import {
  type listOrgMembersApiV1OrganizationsMeMembersGetResponse,
  useListOrgMembersApiV1OrganizationsMeMembersGet,
} from "@/api/generated/organizations/organizations";

export interface OrgMemberSummary {
  user_id: string;
  name: string;
  email: string;
}

export function useOrgMembers(): {
  members: OrgMemberSummary[];
  isLoading: boolean;
} {
  const query = useListOrgMembersApiV1OrganizationsMeMembersGet<
    listOrgMembersApiV1OrganizationsMeMembersGetResponse,
    ApiError
  >(undefined, {
    query: { retry: false },
  });

  const members = useMemo<OrgMemberSummary[]>(() => {
    if (query.data?.status !== 200) return [];
    const items = query.data.data.items ?? [];
    return items.map((m) => ({
      user_id: m.user_id,
      name:
        m.user?.preferred_name ||
        m.user?.name ||
        m.user?.email ||
        m.user_id,
      email: m.user?.email ?? "",
    }));
  }, [query.data]);

  return { members, isLoading: query.isLoading };
}
