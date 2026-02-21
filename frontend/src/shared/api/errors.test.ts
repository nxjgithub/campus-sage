import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";
import { formatApiErrorMessage, normalizeApiError } from "./errors";

describe("normalizeApiError", () => {
  it("应处理普通 Error", () => {
    const result = normalizeApiError(new Error("boom"));
    expect(result.code).toBe("UNKNOWN_ERROR");
    expect(result.message).toBe("boom");
  });

  it("应优先读取响应体中的 request_id", () => {
    const error = {
      isAxiosError: true,
      message: "request failed",
      response: {
        data: {
          error: {
            code: "KB_NOT_FOUND",
            message: "知识库不存在"
          },
          request_id: "req_body_1"
        },
        headers: AxiosHeaders.from({ "x-request-id": "req_header_1" })
      }
    } as AxiosError;
    const result = normalizeApiError(error);
    expect(result.request_id).toBe("req_body_1");
  });

  it("当响应体缺失 request_id 时应回退读取响应头", () => {
    const error = {
      isAxiosError: true,
      message: "request failed",
      response: {
        data: {
          error: {
            code: "KB_NOT_FOUND",
            message: "知识库不存在"
          }
        },
        headers: AxiosHeaders.from({ "x-request-id": "req_header_2" })
      }
    } as AxiosError;
    const result = normalizeApiError(error);
    expect(result.request_id).toBe("req_header_2");
  });
});

describe("formatApiErrorMessage", () => {
  it("应包含错误码与 request_id", () => {
    const text = formatApiErrorMessage({
      code: "RAG_NO_EVIDENCE",
      message: "证据不足",
      request_id: "req_123"
    });
    expect(text).toBe("证据不足（RAG_NO_EVIDENCE，request_id=req_123）");
  });
});
