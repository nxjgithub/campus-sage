import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanupStaleStartedJobs,
  fetchQueueStats,
  fetchRuntimeDiagnostics,
  moveDeadJobs
} from "../../shared/api/modules/monitor";
import { MonitorPage } from "./MonitorPage";

vi.mock("../../shared/api/modules/monitor", () => ({
  cleanupStaleStartedJobs: vi.fn(),
  fetchQueueStats: vi.fn(),
  fetchRuntimeDiagnostics: vi.fn(),
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
    vi.mocked(fetchRuntimeDiagnostics).mockResolvedValue({
      app_env: "test",
      log_level: "INFO",
      debug_mode: false,
      enable_swagger: true,
      database: {
        backend: "sqlite",
        target: "test.db",
        schema_version: 8
      },
      services: {
        vector_backend: "memory",
        embedding_backend: "fake",
        rerank_backend: "simple",
        vllm_enabled: false,
        ingest_queue_enabled: false
      },
      upload: {
        max_mb: 50,
        allowed_exts: [".pdf"]
      },
      security: {
        jwt_default_secret: false,
        jwt_weak_secret: false
      },
      rag_metrics: {
        sample_size: 0,
        refusal_count: 0,
        clarification_count: 0,
        freshness_warning_count: 0,
        citation_covered_count: 0,
        refusal_rate: 0,
        clarification_rate: 0,
        freshness_warning_rate: 0,
        citation_coverage_rate: 0
      },
      warnings: [],
      request_id: "req-runtime-1"
    });
    vi.mocked(moveDeadJobs).mockResolvedValue({
      moved: 3,
      request_id: "req-move-1"
    });
    vi.mocked(cleanupStaleStartedJobs).mockResolvedValue({
      removed: 2,
      request_id: "req-cleanup-1"
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

  it("清理过期执行记录应先确认，确认后再调用接口", async () => {
    renderWithProviders(<MonitorPage />);

    const cleanupButton = await screen.findByRole("button", {
      name: /清理过期执行记录/
    });
    await userEvent.click(cleanupButton);

    expect(await screen.findByRole("button", { name: "确认清理" })).toBeInTheDocument();
    expect(cleanupStaleStartedJobs).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "确认清理" }));
    await waitFor(() => {
      expect(cleanupStaleStartedJobs).toHaveBeenCalledTimes(1);
    });
  });

  it("队列统计全为零时仍应展示健康看板", async () => {
    vi.mocked(fetchQueueStats).mockResolvedValue({
      stats: {
        queued: 0,
        started: 0,
        deferred: 0,
        finished: 0,
        failed_registry: 0,
        dead: 0,
        scheduled: 0
      },
      alerts: [],
      request_id: "req-monitor-empty"
    });

    renderWithProviders(<MonitorPage />);

    expect(await screen.findByText("队列监控中心")).toBeInTheDocument();
    expect(screen.getByText("暂无告警")).toBeInTheDocument();
    expect(screen.queryByText("当前条件下暂无内容")).not.toBeInTheDocument();
  });
});
