import axios, { AxiosError } from "axios";

export interface ApiErrorShape {
  code: string;
  message: string;
  detail?: unknown;
  request_id?: string | null;
}

function resolveRequestIdFromHeaders(error: AxiosError): string | null {
  const pickText = (value: unknown): string | null => {
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      const text = value.find((item) => typeof item === "string");
      return typeof text === "string" ? text : null;
    }
    return null;
  };

  const headers = error.response?.headers;
  if (!headers) {
    return null;
  }

  if (typeof headers.get === "function") {
    return pickText(headers.get("x-request-id") ?? headers.get("X-Request-ID"));
  }

  const record = headers as Record<string, unknown>;
  return pickText(record["x-request-id"] ?? record["X-Request-ID"]);
}

export function normalizeApiError(error: unknown): ApiErrorShape {
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    "message" in error &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    const record = error as {
      code: string;
      message: string;
      detail?: unknown;
      request_id?: string | null;
    };
    return {
      code: record.code,
      message: record.message,
      detail: record.detail,
      request_id: record.request_id ?? null
    };
  }
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
      request_id: payload?.request_id ?? resolveRequestIdFromHeaders(axiosError)
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

export function formatApiErrorMessage(error: ApiErrorShape): string {
  const suffix = error.request_id ? `，request_id=${error.request_id}` : "";
  return `${error.message}（${error.code}${suffix}）`;
}
