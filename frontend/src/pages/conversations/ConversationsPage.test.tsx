import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationMessage } from "../../shared/api/modules/conversations";
import { MessageCard } from "./ConversationsPage";

describe("ConversationsPage 引用交互", () => {
  const scrollIntoViewMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
    });
  });

  it("点击会话消息中的引用编号后应高亮对应卡片并滚动", async () => {
    const item: ConversationMessage = {
      message_id: "msg-2",
      role: "assistant",
      content: "结论来自[2]",
      citations: [
        {
          citation_id: 2,
          doc_id: "doc-2",
          doc_name: "学生手册",
          chunk_id: "chunk-2",
          snippet: "会话证据片段",
          section_path: "奖惩/补考"
        }
      ],
      refusal: false,
      created_at: "2026-02-12T10:00:00Z"
    };

    render(
      <AntdApp>
        <MessageCard
          item={item}
          submitting={false}
          submitted={false}
          onFeedbackSubmit={vi.fn().mockResolvedValue(undefined)}
        />
      </AntdApp>
    );

    const marker = screen.getByRole("button", { name: "[2]" });
    await userEvent.click(marker);

    const snippet = screen.getByText("会话证据片段");
    const card = snippet.closest(".citation-card");
    expect(card).toHaveClass("citation-card--active");
    expect(scrollIntoViewMock).toHaveBeenCalled();
  });

  it("提交反对反馈时应将结构化字段传给回调", async () => {
    const item: ConversationMessage = {
      message_id: "msg-3",
      role: "assistant",
      content: "建议参考管理办法",
      citations: [],
      refusal: false,
      created_at: "2026-02-12T10:10:00Z"
    };

    const onFeedbackSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <AntdApp>
        <MessageCard
          item={item}
          submitting={false}
          submitted={false}
          onFeedbackSubmit={onFeedbackSubmit}
        />
      </AntdApp>
    );

    await userEvent.click(screen.getByRole("button", { name: "反对" }));
    await userEvent.type(
      await screen.findByPlaceholderText("可补充说明答案质量或证据情况"),
      "理由不够具体"
    );
    await userEvent.type(
      screen.getByPlaceholderText("例如：请补充具体政策条款或办理步骤"),
      "请补充具体条款编号"
    );
    await userEvent.click(screen.getByRole("button", { name: "提交反馈" }));

    await waitFor(() => {
      expect(onFeedbackSubmit).toHaveBeenCalledWith("msg-3", {
        rating: "down",
        reasons: [],
        comment: "理由不够具体",
        expected_hint: "请补充具体条款编号"
      });
    });
  });

  it("拒答消息应展示结构化下一步建议", () => {
    const item: ConversationMessage = {
      message_id: "msg-4",
      role: "assistant",
      content: "当前知识库中未找到足够证据，无法给出可靠答案。",
      citations: [],
      refusal: true,
      refusal_reason: "LOW_EVIDENCE",
      request_id: "req_conv_4",
      suggestions: ["建议先查看教务处官网的最新制度原文"],
      next_steps: [
        {
          action: "verify_kb_scope",
          label: "确认知识库范围",
          detail: "先确认当前知识库是否已收录对应制度；若未收录，需要先补充文档。",
          value: null
        }
      ],
      created_at: "2026-02-12T10:12:00Z"
    };

    render(
      <AntdApp>
        <MessageCard
          item={item}
          submitting={false}
          submitted={false}
          onFeedbackSubmit={vi.fn().mockResolvedValue(undefined)}
        />
      </AntdApp>
    );

    expect(screen.getByText("证据内容不足以支撑回答")).toBeInTheDocument();
    expect(screen.getByText("请求 ID：req_conv_4")).toBeInTheDocument();
    expect(screen.getByText("确认知识库范围")).toBeInTheDocument();
    expect(screen.getByText("建议先查看教务处官网的最新制度原文")).toBeInTheDocument();
    expect(
      screen.getByText("先确认当前知识库是否已收录对应制度；若未收录，需要先补充文档。")
    ).toBeInTheDocument();
  });

  it("点击历史拒答建议按钮后应把动作回传给页面处理器", async () => {
    const item: ConversationMessage = {
      message_id: "msg-5",
      role: "assistant",
      content: "建议先核验官网。",
      citations: [
        {
          citation_id: 1,
          doc_id: "doc-5",
          doc_name: "教务处公告",
          chunk_id: "chunk-5",
          snippet: "请以官网最新通知为准。",
          source_uri: "https://example.edu/notice"
        }
      ],
      refusal: true,
      refusal_reason: "LOW_EVIDENCE",
      next_steps: [
        {
          action: "check_official_source",
          label: "查看官方来源",
          detail: "优先核对学校官网、教务处或学院公告中的最新制度原文。",
          value: null
        }
      ],
      created_at: "2026-02-12T10:15:00Z"
    };
    const onApplyNextStep = vi.fn().mockResolvedValue(undefined);

    render(
      <AntdApp>
        <MessageCard
          item={item}
          submitting={false}
          submitted={false}
          onFeedbackSubmit={vi.fn().mockResolvedValue(undefined)}
          onApplyNextStep={onApplyNextStep}
        />
      </AntdApp>
    );

    await userEvent.click(screen.getByRole("button", { name: "查看官方来源" }));

    expect(onApplyNextStep).toHaveBeenCalledWith(item.next_steps?.[0], item.citations);
  });
});
