import axios, { AxiosError } from "axios";

export interface ApiErrorShape {
  code: string;
  message: string;
  detail?: unknown;
  request_id?: string | null;
}

export function normalizeApiError(error: unknown): ApiErrorShape {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{
      error?: { code?: string; message?: string; detail?: unknown };
      request_id?: string | null;
    }>;
    const payload = axiosError.response?.data;
    const code = payload?.error?.code ?? "NETWORK_ERROR";
    const message = payload?.error?.message ?? axiosError.message ?? "请求失败";
    return {
      code,
      message,
      detail: payload?.error?.detail,
      request_id: payload?.request_id
    };
  }
  if (error instanceof Error) {
    return {
      code: "UNKNOWN_ERROR",
      message: error.message
    };
  }
  return {
    code: "UNKNOWN_ERROR",
    message: "未知错误"
  };
}
