import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { askStreamByKb } from "../../shared/api/modules/ask";
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
    status: "anonymous",
    user: null,
    role: "user",
    isAuthenticated: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refreshUser: vi.fn()
  })
}));

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
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

describe("AskPage 聊天交互", () => {
  const scrollIntoViewMock = vi.fn();
  const windowOpenMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
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

    const marker = await screen.findByRole("button", { name: "[1]" });
    await userEvent.click(marker);

    expect(await screen.findByText("证据面板")).toBeInTheDocument();
    const snippet = await screen.findByText("补考申请需要满足课程修读条件。");
    const card = snippet.closest(".citation-card");
    expect(card).toHaveClass("citation-card--active");
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

    expect(await screen.findByText("补充场景条件")).toBeInTheDocument();
    expect(screen.getByText("建议补充学院、年级、身份或办理场景等限定信息")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看官方来源" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "填入补充条件" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/请输入你的问题|请输入问题/)).toHaveValue(
        "学院/年级/身份/办理场景"
      );
    });

    await userEvent.click(screen.getByRole("button", { name: "查看官方来源" }));

    expect(windowOpenMock).toHaveBeenCalledWith(
      "https://example.edu/academic/policy",
      "_blank",
      "noopener,noreferrer"
    );
  });
});
