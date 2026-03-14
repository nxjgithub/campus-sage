import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";
import {
  formatApiErrorMessage,
  normalizeApiError,
  resolveApiErrorDisplay
} from "./errors";

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

  it("应在响应体缺少 request_id 时回退读取响应头", () => {
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

describe("resolveApiErrorDisplay", () => {
  it("应将已知错误码映射为前端统一提示", () => {
    const result = resolveApiErrorDisplay({
      code: "AUTH_INVALID_CREDENTIALS",
      message: "用户名密码错误"
    });

    expect(result.summary).toBe("邮箱或密码不正确，请重新输入。");
  });

  it("应保留已知错误的下一步建议", () => {
    const result = resolveApiErrorDisplay({
      code: "VECTOR_SEARCH_FAILED",
      message: "向量检索失败"
    });

    expect(result.summary).toBe("检索服务暂时不可用。");
    expect(result.nextStep).toBe("请稍后重试。");
  });

  it("应在未知错误码时回退到后端 message", () => {
    const result = resolveApiErrorDisplay({
      code: "SOMETHING_NEW",
      message: "后端返回的新错误"
    });

    expect(result.summary).toBe("后端返回的新错误");
  });
});

describe("formatApiErrorMessage", () => {
  it("应优先输出用户可理解文案，并附带请求 ID", () => {
    const text = formatApiErrorMessage({
      code: "RAG_NO_EVIDENCE",
      message: "证据不足",
      request_id: "req_123"
    });

    expect(text).toBe("当前知识库中的证据不足，暂时无法回答该问题。（请求 ID：req_123）");
  });

  it("应在无请求 ID 时仅返回用户文案", () => {
    const text = formatApiErrorMessage({
      code: "AUTH_INVALID_CREDENTIALS",
      message: "用户名密码错误"
    });

    expect(text).toBe("邮箱或密码不正确，请重新输入。");
  });
});
