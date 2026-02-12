import { apiClient } from "../client";

export interface RoleItem {
  name: string;
  permissions: string[];
}

export interface RoleListResponse {
  items: RoleItem[];
  request_id?: string | null;
}

export async function fetchRoleList() {
  const { data } = await apiClient.get<RoleListResponse>("/roles");
  return data;
}
