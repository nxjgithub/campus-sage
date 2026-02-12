import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEvalSet, fetchEvalRun, runEval } from "../../shared/api/modules/eval";
import { fetchKbList } from "../../shared/api/modules/kb";
import { EvalPage } from "./EvalPage";

vi.mock("../../shared/api/modules/eval", () => ({
  createEvalSet: vi.fn(),
  runEval: vi.fn(),
  fetchEvalRun: vi.fn()
}));

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
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

describe("EvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKbList).mockResolvedValue({ items: [] });
    vi.mocked(createEvalSet).mockResolvedValue({
      eval_set_id: "es-1",
      name: "set-1",
      description: null,
      item_count: 1,
      created_at: "2026-02-12T10:00:00Z"
    });
    vi.mocked(runEval).mockResolvedValue({
      run_id: "run-1",
      eval_set_id: "es-1",
      kb_id: "kb-1",
      topk: 5,
      threshold: 0.25,
      rerank_enabled: false,
      metrics: {
        recall_at_k: 0.8,
        mrr: 0.7,
        avg_ms: 120,
        p95_ms: 240,
        samples: 10
      },
      created_at: "2026-02-12T10:01:00Z"
    });
    vi.mocked(fetchEvalRun).mockResolvedValue({
      run_id: "run-1",
      eval_set_id: "es-1",
      kb_id: "kb-1",
      topk: 5,
      threshold: 0.25,
      rerank_enabled: false,
      metrics: null,
      created_at: "2026-02-12T10:01:00Z"
    });
  });

  it("创建评测集时应提交结构化样本", async () => {
    renderWithProviders(<EvalPage />);

    await userEvent.type(screen.getByLabelText("评测集名称"), " 教务评测集_v1 ");
    await userEvent.type(screen.getByLabelText("问题"), " 补考申请流程是什么？ ");
    await userEvent.type(screen.getByLabelText("标签（逗号分隔）"), "policy, exam ");
    await userEvent.click(screen.getByRole("button", { name: "创建评测集" }));

    await waitFor(() => {
      expect(createEvalSet).toHaveBeenCalledWith({
        name: "教务评测集_v1",
        description: undefined,
        items: [
          {
            question: "补考申请流程是什么？",
            gold_doc_id: undefined,
            gold_page_start: undefined,
            gold_page_end: undefined,
            tags: ["policy", "exam"]
          }
        ]
      });
    });
  });
});
