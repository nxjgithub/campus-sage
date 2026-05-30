import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import {
  AskStreamEvent,
  askStreamByKb,
  cancelChatRun,
  getChatRun,
  regenerateMessage
} from "../../shared/api/modules/ask";
import {
  createConversation,
  deleteConversation,
  fetchConversationList,
  fetchConversationMessagesPage,
  renameConversation,
  submitFeedback
} from "../../shared/api/modules/conversations";
import { fetchKbList } from "../../shared/api/modules/kb";
import { AskPage } from "./AskPage";

const mockSignOut = vi.fn();
let mockAccessToken: string | null = null;
let mockAuthState: {
  status: "loading" | "authenticated" | "anonymous";
  user:
    | {
        user_id: string;
        email: string;
        status: "active" | "disabled" | "deleted";
        roles: string[];
        created_at?: string;
        updated_at?: string;
      }
    | null;
  role: "admin" | "user";
  isAuthenticated: boolean;
} = {
  status: "anonymous",
  user: null,
  role: "user",
  isAuthenticated: false
};

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
}));

vi.mock("../../shared/api/modules/ask", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../shared/api/modules/ask")>();
  return {
    ...original,
    askStreamByKb: vi.fn(),
    regenerateMessage: vi.fn(),
    editAndResendMessage: vi.fn(),
    cancelChatRun: vi.fn(),
    getChatRun: vi.fn()
  };
});

vi.mock("../../shared/api/modules/conversations", () => ({
  fetchConversationList: vi.fn(),
  fetchConversationMessagesPage: vi.fn(),
  submitFeedback: vi.fn(),
  createConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn()
}));

vi.mock("../../shared/auth/auth", () => ({
  useAuth: () => ({
    status: mockAuthState.status,
    user: mockAuthState.user,
    role: mockAuthState.role,
    isAuthenticated: mockAuthState.isAuthenticated,
    signIn: vi.fn(),
    signOut: mockSignOut,
    refreshUser: vi.fn()
  })
}));

vi.mock("../../shared/auth/token", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../shared/auth/token")>();
  return {
    ...original,
    getAccessToken: () => mockAccessToken
  };
});

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AntdApp>{node}</AntdApp>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockBasicStream() {
  vi.mocked(askStreamByKb).mockImplementation(async (_kbId, _payload, options) => {
    options?.onEvent?.({
      event: "start",
      data: { run_id: "run_1", conversation_id: "conv_1", request_id: "req_1" }
    });
    options?.onEvent?.({
      event: "status",
      data: {
        run_id: "run_1",
        phase: "vector_retrieval",
        label: "检索向量库",
        detail: "知识库：教务知识库。",
        request_id: "req_1"
      }
    });
    options?.onEvent?.({
      event: "status",
      data: {
        run_id: "run_1",
        phase: "web_search",
        label: "已抓取授权网页证据",
        detail: "来源：https://jsj.suse.edu.cn/xydt/list.htm。",
        request_id: "req_1"
      }
    });
    options?.onEvent?.({
      event: "token",
      data: { run_id: "run_1", delta: "根据规定[1]可以办理。", request_id: "req_1" }
    });
    options?.onEvent?.({
      event: "citation",
      data: {
        run_id: "run_1",
        citation: {
          citation_id: 1,
          doc_id: "doc_1",
          doc_name: "教务手册",
          chunk_id: "chunk_1",
          snippet: "补考申请需要满足课程修读条件。",
          section_path: "考试管理/补考"
        },
        request_id: "req_1"
      }
    });
    options?.onEvent?.({
      event: "done",
      data: {
        run_id: "run_1",
        status: "succeeded",
        conversation_id: "conv_1",
        user_message_id: "msg_user_1",
        message_id: "msg_assistant_1",
        assistant_created_at: "2026-02-21T10:00:00Z",
        refusal: false,
        timing: { total_ms: 120 },
        request_id: "req_1"
      }
    });
  });
}

function mockRefusalStream() {
  vi.mocked(askStreamByKb).mockImplementation(async (_kbId, _payload, options) => {
    options?.onEvent?.({
      event: "start",
      data: { run_id: "run_refusal", conversation_id: "conv_refusal", request_id: "req_refusal" }
    });
    options?.onEvent?.({
      event: "refusal",
      data: {
        run_id: "run_refusal",
        answer: "当前知识库中未找到足够证据，无法给出可靠答案。",
        refusal_reason: "LOW_COVERAGE",
        suggestions: ["建议补充学院、年级、身份或办理场景等限定信息"],
        next_steps: [
          {
            action: "add_context",
            label: "补充场景条件",
            detail: "补充学院、年级、学生类型或办理场景，可提高证据匹配度。",
            value: "学院/年级/身份/办理场景"
          },
          {
            action: "check_official_source",
            label: "查看官方来源",
            detail: "优先核对学校官网、教务处或学院公告中的最新制度原文。",
            value: "https://example.edu/academic/policy"
          }
        ],
        conversation_id: "conv_refusal",
        user_message_id: "msg_user_refusal",
        message_id: "msg_assistant_refusal",
        assistant_created_at: "2026-02-21T10:05:00Z",
        timing: { total_ms: 80 },
        request_id: "req_refusal"
      }
    });
    options?.onEvent?.({
      event: "done",
      data: {
        run_id: "run_refusal",
        status: "succeeded",
        conversation_id: "conv_refusal",
        user_message_id: "msg_user_refusal",
        message_id: "msg_assistant_refusal",
        assistant_created_at: "2026-02-21T10:05:00Z",
        refusal: true,
        timing: { total_ms: 80 },
        request_id: "req_refusal"
      }
    });
  });
}

async function fillQuestionInput(question: string) {
  await userEvent.type(await screen.findByPlaceholderText(/请输入你的问题|请输入问题/), question);
}

function createDeferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("AskPage 聊天交互", () => {
  const scrollIntoViewMock = vi.fn();
  const windowOpenMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockAccessToken = null;
    mockAuthState = {
      status: "anonymous",
      user: null,
      role: "user",
      isAuthenticated: false
    };
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
    });
    Object.defineProperty(window, "open", {
      configurable: true,
      value: windowOpenMock
    });
    vi.mocked(fetchKbList).mockResolvedValue({
      items: [{ kb_id: "kb_1", name: "教务知识库", visibility: "public", updated_at: "2026-02-21" }]
    });
    vi.mocked(fetchConversationList).mockResolvedValue({
      items: [],
      total: 0,
      next_cursor: null
    });
    vi.mocked(fetchConversationMessagesPage).mockResolvedValue({
      items: [],
      has_more: false,
      next_before: null
    });
    vi.mocked(submitFeedback).mockResolvedValue({
      feedback_id: "fb_1",
      message_id: "msg_assistant_1",
      status: "ok"
    });
    vi.mocked(createConversation).mockResolvedValue({
      conversation_id: "conv_new",
      kb_id: "kb_1",
      title: "新会话",
      created_at: "2026-02-21T10:00:00Z",
      updated_at: "2026-02-21T10:00:00Z"
    });
    vi.mocked(renameConversation).mockResolvedValue({
      conversation_id: "conv_new",
      kb_id: "kb_1",
      title: "新标题",
      created_at: "2026-02-21T10:00:00Z",
      updated_at: "2026-02-21T10:10:00Z"
    });
    vi.mocked(deleteConversation).mockResolvedValue({
      conversation_id: "conv_new",
      status: "deleted"
    });
    vi.mocked(cancelChatRun).mockResolvedValue({
      run_id: "run_1",
      status: "running",
      cancel_flag: true,
      request_id: "req_cancel"
    });
    vi.mocked(getChatRun).mockResolvedValue({
      run_id: "run_1",
      status: "succeeded",
      cancel_flag: false,
      conversation_id: "conv_1",
      user_message_id: "msg_user_1",
      assistant_message_id: "msg_assistant_1",
      started_at: "2026-02-21T10:00:00Z",
      finished_at: "2026-02-21T10:00:01Z",
      request_id: "req_1"
    });
    mockBasicStream();
  });

  it("问答主界面不暴露内部 ID 与高级调参控件", async () => {
    renderWithProviders(<AskPage />);

    expect(await screen.findByRole("combobox")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("选择或输入 kb_id")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("TopK")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("阈值")).not.toBeInTheDocument();
    expect(screen.queryByText("run_id")).not.toBeInTheDocument();
  });

  it("点击答案引用编号后应打开证据弹窗并高亮对应卡片", async () => {
    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText("检索向量库")).toBeInTheDocument();
    expect(await screen.findByText("已抓取授权网页证据")).toBeInTheDocument();
    expect(await screen.findByText("来源：https://jsj.suse.edu.cn/xydt/list.htm。")).toBeInTheDocument();

    const marker = await screen.findByRole("button", { name: "[1]" });
    await userEvent.click(marker);

    expect(await screen.findByText("证据面板")).toBeInTheDocument();
    const snippet = await screen.findByText("补考申请需要满足课程修读条件。");
    const card = snippet.closest(".citation-card");
    expect(card).toHaveClass("citation-card--active");
  });

  it("登录态回答完成并刷新历史后仍保留本轮执行状态", async () => {
    mockAccessToken = "token_ask";
    mockAuthState = {
      status: "authenticated",
      user: { user_id: "user_1", email: "admin@example.com", roles: ["admin"], status: "active" },
      role: "admin",
      isAuthenticated: true
    };
    vi.mocked(fetchConversationMessagesPage)
      .mockResolvedValue({
        items: [
          {
            message_id: "msg_user_1",
            role: "user",
            content: "补考申请条件？",
            created_at: "2026-02-21T10:00:00Z",
            request_id: "req_user_1"
          },
          {
            message_id: "msg_assistant_1",
            parent_message_id: "msg_user_1",
            role: "assistant",
            content: "根据规定[1]可以办理。",
            citations: [
              {
                citation_id: 1,
                doc_id: "doc_1",
                doc_name: "教务手册",
                chunk_id: "chunk_1",
                snippet: "补考申请需要满足课程修读条件。",
                section_path: "考试管理/补考"
              }
            ],
            refusal: false,
            refusal_reason: null,
            suggestions: [],
            next_steps: [],
            timing: { total_ms: 120 },
            created_at: "2026-02-21T10:00:00Z",
            request_id: "req_1"
          }
        ],
        has_more: false,
        next_before: null
      });

    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => {
      expect(fetchConversationMessagesPage).toHaveBeenCalledWith("conv_1", {
        limit: 30
      });
    });
    expect(await screen.findByText("检索向量库")).toBeInTheDocument();
    expect(await screen.findByText("已抓取授权网页证据")).toBeInTheDocument();
    expect(screen.getByText("来源：https://jsj.suse.edu.cn/xydt/list.htm。")).toBeInTheDocument();
  });

  it("证据弹窗打开后按任意键应关闭", async () => {
    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));
    await userEvent.click(await screen.findByRole("button", { name: "[1]" }));
    expect(await screen.findByText("按键或点右上角关闭")).toBeInTheDocument();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));

    await waitFor(() => {
      expect(screen.queryByText("按键或点右上角关闭")).not.toBeInTheDocument();
    });
  });

  it("助手消息反馈提交应携带结构化字段", async () => {
    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    await userEvent.click(await screen.findByRole("button", { name: "赞同" }));
    await userEvent.type(
      await screen.findByPlaceholderText("可补充说明答案质量或证据情况"),
      "内容准确"
    );
    await userEvent.click(screen.getByRole("button", { name: /提交反馈/ }));

    await waitFor(() => {
      expect(submitFeedback).toHaveBeenCalledWith("msg_assistant_1", {
        rating: "up",
        reasons: [],
        comment: "内容准确",
        expected_hint: undefined
      });
    });
  });

  it("拒答时应渲染结构化下一步建议，并支持填入追问与跳转官方来源", async () => {
    mockRefusalStream();
    renderWithProviders(<AskPage />);

    await fillQuestionInput("这个问题信息不够");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText("等待补充")).toBeInTheDocument();
    expect(screen.getByText("继续追问建议")).toBeInTheDocument();
    expect(screen.getByText("请求 ID：req_refusal")).toBeInTheDocument();
    expect((await screen.findAllByText("补充场景条件")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("建议补充学院、年级、身份或办理场景等限定信息")).toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: "查看官方来源" })).length).toBeGreaterThanOrEqual(2);

    await userEvent.click(screen.getByRole("button", { name: "填入补充条件" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/请输入你的问题|请输入问题/)).toHaveValue(
        "学院/年级/身份/办理场景"
      );
    });

    await userEvent.click((await screen.findAllByRole("button", { name: "查看官方来源" }))[0]);

    expect(windowOpenMock).toHaveBeenCalledWith(
      "https://example.edu/academic/policy",
      "_blank",
      "noopener,noreferrer"
    );
  });

  it("最终拒答事件应覆盖临时生成文本并清理临时引用", async () => {
    vi.mocked(askStreamByKb).mockImplementation(async (_kbId, _payload, options) => {
      options?.onEvent?.({
        event: "start",
        data: { run_id: "run_soft_refusal", conversation_id: "conv_soft_refusal", request_id: "req_soft_refusal" }
      });
      options?.onEvent?.({
        event: "token",
        data: {
          run_id: "run_soft_refusal",
          delta: "抱歉，没有任何一条证据提到该事件。参考：[1]",
          request_id: "req_soft_refusal"
        }
      });
      options?.onEvent?.({
        event: "citation",
        data: {
          run_id: "run_soft_refusal",
          citation: {
            citation_id: 1,
            doc_id: "doc_soft_refusal",
            doc_name: "临时证据",
            chunk_id: "chunk_soft_refusal",
            snippet: "这条引用不应保留。"
          },
          request_id: "req_soft_refusal"
        }
      });
      options?.onEvent?.({
        event: "refusal",
        data: {
          run_id: "run_soft_refusal",
          answer: "当前知识库中未找到足够证据，无法给出可靠答案。",
          refusal_reason: "LOW_EVIDENCE",
          suggestions: [],
          next_steps: [
            {
              action: "verify_kb_scope",
              label: "确认知识库范围",
              detail: "先确认当前知识库是否已收录对应制度；若未收录，需要先补充文档。",
              value: null
            }
          ],
          conversation_id: "conv_soft_refusal",
          user_message_id: "msg_user_soft_refusal",
          message_id: "msg_assistant_soft_refusal",
          request_id: "req_soft_refusal"
        }
      });
      options?.onEvent?.({
        event: "done",
        data: {
          run_id: "run_soft_refusal",
          status: "succeeded",
          conversation_id: "conv_soft_refusal",
          user_message_id: "msg_user_soft_refusal",
          message_id: "msg_assistant_soft_refusal",
          refusal: true,
          request_id: "req_soft_refusal"
        }
      });
    });
    renderWithProviders(<AskPage />);

    await fillQuestionInput("请解释具体事件");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(await screen.findByText("等待补充")).toBeInTheDocument();
    expect(screen.getByText("当前知识库中未找到足够证据，无法给出可靠答案。")).toBeInTheDocument();
    expect(screen.queryByText("抱歉，没有任何一条证据提到该事件。参考：[1]")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "[1]" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "查看引用" })).not.toBeInTheDocument();
  });

  it("空态示例问题应可直接回填输入框", async () => {
    renderWithProviders(<AskPage />);

    expect(screen.queryByText("准备开始一次新问答")).not.toBeInTheDocument();
    expect(screen.queryByText("当前会话还没有消息")).not.toBeInTheDocument();
    expect(screen.queryByText("就绪")).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "研究生复试需要准备哪些材料？" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/请输入你的问题|请输入问题/)).toHaveValue(
        "研究生复试需要准备哪些材料？"
      );
    });
  });

  it("知识库失效后应自动刷新并回退到可用知识库", async () => {
    vi.mocked(fetchKbList)
      .mockResolvedValueOnce({
        items: [{ kb_id: "kb_deleted", name: "失效知识库", visibility: "public", updated_at: "2026-02-21" }]
      })
      .mockResolvedValueOnce({
        items: [{ kb_id: "kb_1", name: "教务知识库", visibility: "public", updated_at: "2026-02-22" }]
      });
    vi.mocked(askStreamByKb).mockRejectedValue({
      code: "KB_NOT_FOUND",
      message: "知识库不存在",
      request_id: "req_missing_kb"
    });

    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => {
      expect(fetchKbList).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.getByText("知识库：教务知识库")).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/请输入你的问题|请输入问题/)).toHaveValue(
        "补考申请条件？"
      );
    });
  });

  it("新建会话后即使列表刷新仍返回旧列表，也应保持新会话线程而不回退", async () => {
    mockAccessToken = "token_ask";
    mockAuthState = {
      status: "authenticated",
      user: { user_id: "user_1", email: "admin@example.com", roles: ["admin"], status: "active" },
      role: "admin",
      isAuthenticated: true
    };
    vi.mocked(fetchConversationList)
      .mockResolvedValueOnce({
        items: [
          {
            conversation_id: "conv_old",
            kb_id: "kb_1",
            title: "旧会话",
            last_message_preview: "旧会话里的内容",
            last_message_at: "2026-02-21T10:00:00Z",
            updated_at: "2026-02-21T10:00:00Z"
          }
        ],
        total: 1,
        next_cursor: null
      })
      .mockResolvedValue({
        items: [
          {
            conversation_id: "conv_old",
            kb_id: "kb_1",
            title: "旧会话",
            last_message_preview: "旧会话里的内容",
            last_message_at: "2026-02-21T10:00:00Z",
            updated_at: "2026-02-21T10:00:00Z"
          }
        ],
        total: 1,
        next_cursor: null
      });
    vi.mocked(fetchConversationMessagesPage).mockImplementation(async (conversationId) => ({
      items:
        conversationId === "conv_old"
          ? [
              {
                message_id: "msg_old_assistant",
                role: "assistant",
                content: "这是旧会话回答",
                citations: [],
                refusal: false,
                refusal_reason: null,
                suggestions: [],
                next_steps: [],
                timing: null,
                created_at: "2026-02-21T10:00:00Z",
                request_id: "req_old"
              }
            ]
          : [],
      has_more: false,
      next_before: null
    }));

    renderWithProviders(<AskPage />);

    await userEvent.click(await screen.findByRole("button", { name: /旧会话/ }));
    expect(await screen.findByText("这是旧会话回答")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "新建会话" }));

    await waitFor(() => {
      expect(screen.getByText("当前会话暂无消息")).toBeInTheDocument();
    });
    expect(screen.queryByText("这是旧会话回答")).not.toBeInTheDocument();
  });

  it("继续追问失效或无权会话时应清理上下文并保留问题", async () => {
    mockAccessToken = "token_ask";
    mockAuthState = {
      status: "authenticated",
      user: { user_id: "user_1", email: "admin@example.com", roles: ["admin"], status: "active" },
      role: "admin",
      isAuthenticated: true
    };
    let conversationListPayload = {
      items: [
        {
          conversation_id: "conv_foreign",
          kb_id: "kb_1",
          title: "他人会话",
          last_message_preview: "他人会话内容",
          last_message_at: "2026-02-21T10:00:00Z",
          updated_at: "2026-02-21T10:00:00Z"
        }
      ],
      total: 1,
      next_cursor: null
    };
    vi.mocked(fetchConversationList).mockImplementation(async () => conversationListPayload);
    vi.mocked(fetchConversationMessagesPage).mockResolvedValue({
      items: [
        {
          message_id: "msg_foreign_assistant",
          role: "assistant",
          content: "不应继续保留的历史回答",
          citations: [],
          refusal: false,
          refusal_reason: null,
          suggestions: [],
          next_steps: [],
          timing: null,
          created_at: "2026-02-21T10:00:00Z",
          request_id: "req_old"
        }
      ],
      has_more: false,
      next_before: null
    });
    vi.mocked(askStreamByKb).mockRejectedValue({
      code: "AUTH_FORBIDDEN",
      message: "无权访问该会话",
      request_id: "req_b2377009597b4b79a4f1a486804b9571"
    });

    renderWithProviders(<AskPage />);

    await userEvent.click(await screen.findByRole("button", { name: /他人会话/ }));
    expect(await screen.findByText("不应继续保留的历史回答")).toBeInTheDocument();

    conversationListPayload = {
      items: [],
      total: 0,
      next_cursor: null
    };
    await fillQuestionInput("继续追问");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => {
      expect(askStreamByKb).toHaveBeenCalledWith(
        "kb_1",
        { question: "继续追问", conversation_id: "conv_foreign" },
        expect.any(Object)
      );
    });
    await waitFor(() => {
      expect(screen.queryByText("不应继续保留的历史回答")).not.toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/请输入你的问题|请输入问题/)).toHaveValue("继续追问");
  });

  it("重新生成后同一用户问题只展示最新助手回答", async () => {
    mockAccessToken = "token_ask";
    mockAuthState = {
      status: "authenticated",
      user: { user_id: "user_1", email: "admin@example.com", roles: ["admin"], status: "active" },
      role: "admin",
      isAuthenticated: true
    };
    vi.mocked(fetchConversationList).mockResolvedValue({
      items: [
        {
          conversation_id: "conv_1",
          kb_id: "kb_1",
          title: "研究生考点有哪些？",
          last_message_preview: "旧回答",
          last_message_at: "2026-02-21T10:00:00Z",
          updated_at: "2026-02-21T10:00:00Z"
        }
      ],
      total: 1,
      next_cursor: null
    });
    vi.mocked(fetchConversationMessagesPage)
      .mockResolvedValueOnce({
        items: [
          {
            message_id: "msg_user_1",
            role: "user",
            content: "研究生考点有哪些？",
            created_at: "2026-02-21T10:00:00Z",
            request_id: "req_user"
          },
          {
            message_id: "msg_assistant_old",
            parent_message_id: "msg_user_1",
            role: "assistant",
            content: "旧回答：考点在旧地点。",
            citations: [],
            refusal: false,
            refusal_reason: null,
            suggestions: [],
            next_steps: [],
            timing: null,
            created_at: "2026-02-21T10:01:00Z",
            request_id: "req_old"
          }
        ],
        has_more: false,
        next_before: null
      })
      .mockResolvedValueOnce({
        items: [
          {
            message_id: "msg_user_1",
            role: "user",
            content: "研究生考点有哪些？",
            created_at: "2026-02-21T10:00:00Z",
            request_id: "req_user"
          },
          {
            message_id: "msg_assistant_old",
            parent_message_id: "msg_user_1",
            role: "assistant",
            content: "旧回答：考点在旧地点。",
            citations: [],
            refusal: false,
            refusal_reason: null,
            suggestions: [],
            next_steps: [],
            timing: null,
            created_at: "2026-02-21T10:01:00Z",
            request_id: "req_old"
          }
        ],
        has_more: false,
        next_before: null
      })
      .mockResolvedValue({
        items: [
          {
            message_id: "msg_user_1",
            role: "user",
            content: "研究生考点有哪些？",
            created_at: "2026-02-21T10:00:00Z",
            request_id: "req_user"
          },
          {
            message_id: "msg_assistant_old",
            parent_message_id: "msg_user_1",
            role: "assistant",
            content: "旧回答：考点在旧地点。",
            citations: [],
            refusal: false,
            refusal_reason: null,
            suggestions: [],
            next_steps: [],
            timing: null,
            created_at: "2026-02-21T10:01:00Z",
            request_id: "req_old"
          },
          {
            message_id: "msg_assistant_new",
            parent_message_id: "msg_user_1",
            role: "assistant",
            content: "新回答：考点以最新公告为准。",
            citations: [],
            refusal: false,
            refusal_reason: null,
            suggestions: [],
            next_steps: [],
            timing: null,
            created_at: "2026-02-21T10:02:00Z",
            request_id: "req_new"
          }
        ],
        has_more: false,
        next_before: null
      });
    vi.mocked(regenerateMessage).mockResolvedValue({
      answer: "新回答：考点以最新公告为准。",
      refusal: false,
      refusal_reason: null,
      suggestions: [],
      next_steps: [],
      citations: [],
      conversation_id: "conv_1",
      message_id: "msg_assistant_new",
      user_message_id: "msg_user_1",
      assistant_created_at: "2026-02-21T10:02:00Z",
      timing: { total_ms: 100 },
      request_id: "req_new"
    });

    renderWithProviders(<AskPage />);

    await userEvent.click(await screen.findByRole("button", { name: /研究生考点有哪些/ }));
    expect(await screen.findByText("旧回答：考点在旧地点。")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => {
      expect(screen.getByText("新回答：考点以最新公告为准。")).toBeInTheDocument();
    });
    expect(screen.queryByText("旧回答：考点在旧地点。")).not.toBeInTheDocument();
  });

  it("流式生成中点击停止应调用取消接口，并在 canceled done 后标记为已取消", async () => {
    const deferred = createDeferred();
    let emitStreamEvent: ((event: AskStreamEvent) => void) | null = null;
    vi.mocked(askStreamByKb).mockImplementation(async (_kbId, _payload, options) => {
      emitStreamEvent = options?.onEvent ?? null;
      emitStreamEvent?.({
        event: "start",
        data: { run_id: "run_cancel", conversation_id: "conv_cancel", request_id: "req_cancel" }
      });
      return deferred.promise;
    });
    vi.mocked(cancelChatRun).mockResolvedValue({
      run_id: "run_cancel",
      status: "running",
      cancel_flag: true,
      request_id: "req_cancel"
    });

    renderWithProviders(<AskPage />);

    await fillQuestionInput("请说明补考申请条件");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));
    expect((await screen.findAllByText("生成中")).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: /停止/ }));

    await waitFor(() => {
      expect(cancelChatRun).toHaveBeenCalledWith("run_cancel");
    });
    expect((await screen.findAllByText("停止中")).length).toBeGreaterThan(0);

    await act(async () => {
      emitStreamEvent?.({
        event: "done",
        data: {
          run_id: "run_cancel",
          status: "canceled",
          conversation_id: "conv_cancel",
          user_message_id: "msg_user_cancel",
          message_id: null,
          request_id: "req_cancel"
        }
      });
      deferred.resolve();
      await deferred.promise;
    });

    expect(await screen.findByText("已取消生成。")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("停止中")).not.toBeInTheDocument();
    });
  });

  it("流式连接中断后应查询 run 状态并用服务端消息替换本地占位", async () => {
    mockAccessToken = "token_ask";
    mockAuthState = {
      status: "authenticated",
      user: { user_id: "user_1", email: "admin@example.com", roles: ["admin"], status: "active" },
      role: "admin",
      isAuthenticated: true
    };
    vi.mocked(askStreamByKb).mockImplementation(async (_kbId, _payload, options) => {
      options?.onEvent?.({
        event: "start",
        data: { run_id: "run_recover", conversation_id: "conv_recover", request_id: "req_recover" }
      });
      options?.onEvent?.({
        event: "status",
        data: {
          run_id: "run_recover",
          phase: "web_search",
          label: "未命中授权网页证据",
          detail: "提供方：seed；继续使用知识库证据或执行拒答策略。",
          request_id: "req_recover"
        }
      });
      throw new Error("stream disconnected");
    });
    vi.mocked(getChatRun).mockResolvedValue({
      run_id: "run_recover",
      status: "succeeded",
      cancel_flag: false,
      conversation_id: "conv_recover",
      user_message_id: "msg_user_recover",
      assistant_message_id: "msg_assistant_recover",
      started_at: "2026-02-21T10:00:00Z",
      finished_at: "2026-02-21T10:00:01Z",
      request_id: "req_recover"
    });
    vi.mocked(fetchConversationMessagesPage).mockImplementation(async (conversationId) => ({
      items:
        conversationId === "conv_recover"
          ? [
              {
                message_id: "msg_user_recover",
                role: "user",
                content: "补考申请条件是什么？",
                created_at: "2026-02-21T10:00:00Z",
                request_id: "req_user_recover"
              },
              {
                message_id: "msg_assistant_recover",
                parent_message_id: "msg_user_recover",
                role: "assistant",
                content: "恢复后的服务端回答。",
                citations: [],
                refusal: false,
                refusal_reason: null,
                suggestions: [],
                next_steps: [],
                timing: { total_ms: 120 },
                created_at: "2026-02-21T10:00:01Z",
                request_id: "req_recover"
              }
            ]
          : [],
      has_more: false,
      next_before: null
    }));

    renderWithProviders(<AskPage />);

    await fillQuestionInput("补考申请条件是什么？");
    await userEvent.click(screen.getByRole("button", { name: /发送/ }));

    await waitFor(() => {
      expect(getChatRun).toHaveBeenCalledWith("run_recover");
    });
    expect(await screen.findByText("恢复后的服务端回答。")).toBeInTheDocument();
    expect(await screen.findByText("未命中授权网页证据")).toBeInTheDocument();
    expect(screen.getByText("提供方：seed；继续使用知识库证据或执行拒答策略。")).toBeInTheDocument();
    expect(screen.queryByText("生成已中断。")).not.toBeInTheDocument();
  });
});
