import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createKb, fetchKbList } from "../../shared/api/modules/kb";
import { KbCreatePage } from "./KbCreatePage";

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn(),
  createKb: vi.fn()
}));

function renderWithProviders(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return render(
    <MemoryRouter initialEntries={["/admin/kb/create"]}>
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("KbCreatePage 创建交互", () => {
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
  });

  it("应通过独立创建页提交知识库创建请求", async () => {
    renderWithProviders(<KbCreatePage />);

    await userEvent.type(screen.getByLabelText("知识库名称"), "招生知识库");
    await userEvent.click(screen.getByRole("button", { name: "创建知识库" }));

    await waitFor(() => {
      expect(createKb).toHaveBeenCalledWith({
        name: "招生知识库",
        description: null,
        visibility: "internal",
        config: {
          topk: 5,
          threshold: 0.25,
          rerank_enabled: false,
          max_context_tokens: 3000,
          min_context_chars: 20,
          min_keyword_coverage: 0.3
        }
      });
    });
  });
});
