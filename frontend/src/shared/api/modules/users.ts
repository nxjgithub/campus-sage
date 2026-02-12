import { apiClient } from "../client";

export interface CurrentUser {
  user_id: string;
  email: string;
  status: "active" | "disabled" | "deleted";
  roles: string[];
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
  request_id?: string | null;
}

export async function fetchCurrentUser() {
  const { data } = await apiClient.get<CurrentUser>("/users/me");
  return data;
}

export interface UserListItem {
  user_id: string;
  email: string;
  status: "active" | "disabled" | "deleted";
  roles: string[];
  created_at: string;
}

export interface UserListResponse {
  items: UserListItem[];
  total: number;
  limit: number;
  offset: number;
  request_id?: string | null;
}

export interface UserCreatePayload {
  email: string;
  password: string;
  roles?: string[];
}

export interface UserUpdatePayload {
  status?: "active" | "disabled" | "deleted";
  roles?: string[];
  password?: string;
}

export interface KbAccessItem {
  kb_id: string;
  access_level: "read" | "write" | "admin";
}

export interface KbAccessResponse {
  user_id: string;
  items: KbAccessItem[];
  request_id?: string | null;
}

export interface KbAccessPayload {
  kb_id: string;
  access_level: "read" | "write" | "admin";
}

export interface UserListParams {
  status?: "active" | "disabled" | "deleted";
  keyword?: string;
  limit?: number;
  offset?: number;
}

export async function fetchUserList(params?: UserListParams) {
  const { data } = await apiClient.get<UserListResponse>("/users", { params });
  return data;
}

export async function createUser(payload: UserCreatePayload) {
  const { data } = await apiClient.post<CurrentUser>("/users", payload);
  return data;
}

export async function updateUser(userId: string, payload: UserUpdatePayload) {
  const { data } = await apiClient.patch<CurrentUser>(`/users/${userId}`, payload);
  return data;
}

export async function fetchUserKbAccess(userId: string) {
  const { data } = await apiClient.get<KbAccessResponse>(`/users/${userId}/kb-access`);
  return data;
}

export async function upsertUserKbAccess(userId: string, payload: KbAccessPayload) {
  const { data } = await apiClient.post<KbAccessResponse>(`/users/${userId}/kb-access`, payload);
  return data;
}

export async function deleteUserKbAccess(userId: string, kbId: string) {
  const { data } = await apiClient.delete<{
    user_id: string;
    kb_id: string;
    status: string;
    request_id?: string | null;
  }>(`/users/${userId}/kb-access/${kbId}`);
  return data;
}

export interface KbAccessReplacePayload {
  items: KbAccessItem[];
}

export async function replaceUserKbAccess(userId: string, payload: KbAccessReplacePayload) {
  const { data } = await apiClient.put<KbAccessResponse>(`/users/${userId}/kb-access`, payload);
  return data;
}
