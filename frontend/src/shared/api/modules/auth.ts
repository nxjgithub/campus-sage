import { apiClient } from "../client";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RefreshPayload {
  refresh_token: string;
}

export interface LogoutPayload {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  request_id?: string | null;
}

export async function login(payload: LoginPayload) {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", payload, {
    skipAuthRefresh: true
  });
  return data;
}

export async function refreshToken(payload: RefreshPayload) {
  const { data } = await apiClient.post<TokenResponse>("/auth/refresh", payload, {
    skipAuthRefresh: true
  });
  return data;
}

export async function logout(payload: LogoutPayload) {
  const { data } = await apiClient.post<{ status?: string; request_id?: string | null }>(
    "/auth/logout",
    payload,
    { skipAuthRefresh: true }
  );
  return data;
}
