import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AskResponse, askByKb } from "../../shared/api/modules/ask";
import { submitFeedback } from "../../shared/api/modules/conversations";
import { fetchDocuments } from "../../shared/api/modules/documents";
import { fetchKbList } from "../../shared/api/modules/kb";
import { AskPage } from "./AskPage";

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
}));

vi.mock("../../shared/api/modules/documents", () => ({
  fetchDocuments: vi.fn()
}));

vi.mock("../../shared/api/modules/ask", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../shared/api/modules/ask")>();
  return {
    ...original,
    askByKb: vi.fn()
  };
});

vi.mock("../../shared/api/modules/conversations", () => ({
  submitFeedback: vi.fn()
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
      <AntdApp>{node}</AntdApp>
    </QueryClientProvider>
  );
}

describe("AskPage 引用交互", () => {
  const scrollIntoViewMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
    });
    vi.mocked(fetchKbList).mockResolvedValue({ items: [] });
    vi.mocked(fetchDocuments).mockResolvedValue({ items: [] });
    vi.mocked(askByKb).mockResolvedValue({
      answer: "",
      refusal: false,
      suggestions: [],
      citations: []
    });
    vi.mocked(submitFeedback).mockResolvedValue({
      feedback_id: "fb-1",
      message_id: "msg-1",
      status: "ok"
    });
  });

  it("点击回答中的引用编号后应高亮对应卡片并滚动", async () => {
    const initialResult: AskResponse = {
      answer: "根据规则[1]可以办理",
      refusal: false,
      suggestions: [],
      citations: [
        {
          citation_id: 1,
          doc_id: "doc-1",
          doc_name: "教务手册",
          chunk_id: "chunk-1",
          snippet: "证据片段A",
          section_path: "补考/申请"
        }
      ],
      conversation_id: "conv-1",
      message_id: "msg-1",
      request_id: "req-1"
    };

    renderWithProviders(<AskPage initialResult={initialResult} />);

    const marker = await screen.findByRole("button", { name: "[1]" });
    await userEvent.click(marker);

    const snippet = screen.getByText("证据片段A");
    const card = snippet.closest(".citation-card");
    expect(card).toHaveClass("citation-card--active");
    expect(scrollIntoViewMock).toHaveBeenCalled();
  });

  it("提交反馈成功后应显示已提交状态", async () => {
    const initialResult: AskResponse = {
      answer: "可按流程办理",
      refusal: false,
      suggestions: [],
      citations: [],
      conversation_id: "conv-2",
      message_id: "msg-2",
      request_id: "req-2"
    };

    renderWithProviders(<AskPage initialResult={initialResult} />);

    await userEvent.click(screen.getByRole("button", { name: /赞\s*同/ }));
    await userEvent.type(
      await screen.findByPlaceholderText("可填写对答案质量的说明"),
      "回答有帮助"
    );
    await userEvent.click(screen.getByRole("button", { name: /提\s*交\s*反\s*馈/ }));

    await waitFor(() => {
      expect(submitFeedback).toHaveBeenCalledWith("msg-2", {
        rating: "up",
        reasons: [],
        comment: "回答有帮助",
        expected_hint: undefined
      });
    });

    expect(await screen.findByRole("button", { name: /已\s*提\s*交/ })).toBeDisabled();
  });
});
