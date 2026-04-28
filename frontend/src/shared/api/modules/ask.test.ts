import { afterEach, describe, expect, it, vi } from "vitest";

function streamResponse(body: string) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(body));
        controller.close();
      }
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "X-Request-ID": "req_stream"
      }
    }
  );
}

describe("askStreamByKb", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("流式请求 401 后应刷新 token 并重试解析 SSE", async () => {
    let accessToken = "access_expired";
    const refreshAccessToken = vi.fn().mockImplementation(async () => {
      accessToken = "access_fresh";
      return "access_fresh";
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: { code: "AUTH_TOKEN_EXPIRED", message: "token expired" },
            request_id: "req_expired"
          }),
          { status: 401, headers: { "Content-Type": "application/json" } }
        )
      )
      .mockImplementationOnce((_url: string, init?: RequestInit) => {
        expect((init?.headers as Headers).get("Authorization")).toBe("Bearer access_fresh");
        return Promise.resolve(
          streamResponse(
            [
              'event: start\ndata: {"run_id":"run_1","request_id":"req_stream"}',
              'event: token\ndata: {"run_id":"run_1","delta":"回答片段","request_id":"req_stream"}',
              'event: done\ndata: {"run_id":"run_1","status":"succeeded","request_id":"req_stream"}',
              ""
            ].join("\n\n")
          )
        );
      });

    vi.doMock("../client", () => ({
      apiClient: { defaults: { baseURL: "/api/v1" } },
      refreshAccessToken
    }));
    vi.doMock("../../auth/token", () => ({
      getAccessToken: () => accessToken
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { askStreamByKb } = await import("./ask");
    const events: string[] = [];

    await askStreamByKb(
      "kb_1",
      { question: "补考条件是什么？" },
      {
        onEvent: (event) => {
          events.push(event.event);
        }
      }
    );

    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(events).toEqual(["start", "token", "done"]);
  });

  it("刷新 token 失败时应返回原始 401 错误结构", async () => {
    const refreshAccessToken = vi.fn().mockResolvedValue(null);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "AUTH_TOKEN_EXPIRED", message: "token expired" },
          request_id: "req_expired"
        }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      )
    );

    vi.doMock("../client", () => ({
      apiClient: { defaults: { baseURL: "/api/v1" } },
      refreshAccessToken
    }));
    vi.doMock("../../auth/token", () => ({
      getAccessToken: () => "access_expired"
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { askStreamByKb } = await import("./ask");

    await expect(
      askStreamByKb("kb_1", { question: "补考条件是什么？" })
    ).rejects.toMatchObject({
      code: "AUTH_TOKEN_EXPIRED",
      message: "token expired",
      request_id: "req_expired"
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
