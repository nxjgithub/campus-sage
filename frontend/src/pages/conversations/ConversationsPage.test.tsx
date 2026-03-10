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
});
