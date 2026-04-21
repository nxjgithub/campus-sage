import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  createKb,
  deleteKb,
  fetchKbDetail,
  fetchKbList,
  updateKb
} from "../../shared/api/modules/kb";
import { KbPage } from "./KbPage";

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn(),
  fetchKbDetail: vi.fn(),
  createKb: vi.fn(),
  updateKb: vi.fn(),
  deleteKb: vi.fn()
}));

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return render(
    <MemoryRouter
      initialEntries={["/admin/kb"]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("KbPage 二次确认交互", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKbList).mockResolvedValue({
      items: [
        {
          kb_id: "kb-1",
          name: "教务知识库",
          visibility: "internal",
          updated_at: "2026-02-12T12:00:00Z"
        }
      ]
    });
    vi.mocked(fetchKbDetail).mockResolvedValue({
      kb_id: "kb-1",
      name: "教务知识库",
      description: null,
      visibility: "internal",
      config: {
        topk: 5,
        threshold: 0.25,
        rerank_enabled: false,
        max_context_tokens: 3000,
        min_context_chars: 20,
        min_keyword_coverage: 0.3
      },
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
    vi.mocked(createKb).mockResolvedValue({
      kb_id: "kb-2",
      name: "新建知识库",
      description: null,
      visibility: "internal",
      config: {
        topk: 5,
        threshold: 0.25,
        rerank_enabled: false,
        max_context_tokens: 3000,
        min_context_chars: 20,
        min_keyword_coverage: 0.3
      },
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
    vi.mocked(updateKb).mockResolvedValue({
      kb_id: "kb-1",
      name: "教务知识库",
      description: null,
      visibility: "internal",
      config: {
        topk: 5,
        threshold: 0.25,
        rerank_enabled: false,
        max_context_tokens: 3000,
        min_context_chars: 20,
        min_keyword_coverage: 0.3
      },
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
    vi.mocked(deleteKb).mockResolvedValue({ status: "ok" });
  });

  it("删除知识库应先确认，确认后再调用接口", async () => {
    renderWithProviders(<KbPage />);

    const rowCell = await screen.findByText("教务知识库");
    const row = rowCell.closest("tr");
    if (!(row instanceof HTMLElement)) {
      throw new Error("未找到知识库行");
    }
    const trigger = within(row).getByRole("button", { name: /删\s*除/ });
    await userEvent.click(trigger);

    expect(await screen.findByText("确认删除该知识库？")).toBeInTheDocument();
    expect(deleteKb).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /确\s*认\s*删\s*除/ }));
    await waitFor(() => {
      expect(deleteKb).toHaveBeenCalledWith("kb-1");
    });
  });
});
