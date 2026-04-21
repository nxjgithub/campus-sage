import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEvalSet } from "../../shared/api/modules/eval";
import { EvalCreatePage } from "./EvalCreatePage";

vi.mock("../../shared/api/modules/eval", () => ({
  createEvalSet: vi.fn()
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
      initialEntries={["/admin/eval/create"]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("EvalCreatePage submit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createEvalSet).mockResolvedValue({
      eval_set_id: "es-1",
      name: "\u6559\u52a1\u8bc4\u6d4b\u96c6_v1",
      description: null,
      item_count: 1,
      created_at: "2026-02-12T10:00:00Z"
    });
  });

  it("should submit structured samples when creating an eval set", async () => {
    renderWithProviders(<EvalCreatePage />);

    await userEvent.type(
      screen.getByLabelText("\u8bc4\u6d4b\u96c6\u540d\u79f0"),
      " \u6559\u52a1\u8bc4\u6d4b\u96c6_v1 "
    );
    await userEvent.type(
      screen.getByLabelText("\u95ee\u9898"),
      " \u8865\u8003\u7533\u8bf7\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f "
    );
    await userEvent.type(
      screen.getByLabelText("\u6807\u7b7e\uff08\u9017\u53f7\u5206\u9694\uff09"),
      "policy, exam "
    );
    await userEvent.click(
      screen.getByRole("button", { name: /\u521b\u5efa\u8bc4\u6d4b\u96c6/ })
    );

    await waitFor(() => {
      expect(createEvalSet).toHaveBeenCalledWith({
        name: "\u6559\u52a1\u8bc4\u6d4b\u96c6_v1",
        description: undefined,
        items: [
          {
            question: "\u8865\u8003\u7533\u8bf7\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f",
            gold_page_start: undefined,
            gold_page_end: undefined,
            tags: ["policy", "exam"]
          }
        ]
      });
    });
  });
});
