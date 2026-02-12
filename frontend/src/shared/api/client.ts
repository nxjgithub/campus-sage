import axios, { AxiosError, AxiosHeaders, InternalAxiosRequestConfig } from "axios";
import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from "../auth/token";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

declare module "axios" {
  interface AxiosRequestConfig {
    skipAuthRefresh?: boolean;
  }
}

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 60_000
});

const authClient = axios.create({
  baseURL: "/api/v1",
  timeout: 60_000
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  if (!refreshPromise) {
    refreshPromise = authClient
      .post<TokenResponse>(
        "/auth/refresh",
        { refresh_token: refreshToken },
        { skipAuthRefresh: true }
      )
      .then((response) => {
        saveTokens(response.data);
        return response.data.access_token;
      })
      .catch(() => {
        clearTokens();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

apiClient.interceptors.request.use((config) => {
  const requestId = `req_${crypto.randomUUID().replace(/-/g, "")}`;
  const headers =
    config.headers instanceof AxiosHeaders
      ? config.headers
      : AxiosHeaders.from(config.headers);

  headers.set("X-Request-ID", requestId);
  const accessToken = getAccessToken();
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  config.headers = headers;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status;
    const originalConfig = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean; skipAuthRefresh?: boolean })
      | undefined;

    if (!originalConfig || status !== 401 || originalConfig.skipAuthRefresh || originalConfig._retry) {
      return Promise.reject(error);
    }

    originalConfig._retry = true;
    const nextAccessToken = await refreshAccessToken();
    if (!nextAccessToken) {
      return Promise.reject(error);
    }

    const headers =
      originalConfig.headers instanceof AxiosHeaders
        ? originalConfig.headers
        : AxiosHeaders.from(originalConfig.headers);
    headers.set("Authorization", `Bearer ${nextAccessToken}`);
    originalConfig.headers = headers;
    return apiClient(originalConfig);
  }
);
