import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchQueueStats, moveDeadJobs } from "../../shared/api/modules/monitor";
import { MonitorPage } from "./MonitorPage";

vi.mock("../../shared/api/modules/monitor", () => ({
  fetchQueueStats: vi.fn(),
  moveDeadJobs: vi.fn()
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

describe("MonitorPage 二次确认交互", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchQueueStats).mockResolvedValue({
      stats: {
        queued: 1,
        started: 2,
        deferred: 0,
        finished: 5,
        failed_registry: 1,
        dead: 3,
        scheduled: 1
      },
      alerts: [],
      request_id: "req-monitor-1"
    });
    vi.mocked(moveDeadJobs).mockResolvedValue({
      moved: 3,
      request_id: "req-move-1"
    });
  });

  it("转移失败任务应先确认，确认后再调用接口", async () => {
    renderWithProviders(<MonitorPage />);

    const moveButton = await screen.findByRole("button", {
      name: /迁移失败任务到死信队列/
    });
    await userEvent.click(moveButton);

    expect(await screen.findByRole("button", { name: "确认迁移" })).toBeInTheDocument();
    expect(moveDeadJobs).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "确认迁移" }));
    await waitFor(() => {
      expect(moveDeadJobs).toHaveBeenCalledTimes(1);
    });
  });
});
