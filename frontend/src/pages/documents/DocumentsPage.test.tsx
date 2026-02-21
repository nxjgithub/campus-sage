import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchKbList } from "../../shared/api/modules/kb";
import {
  cancelIngestJob,
  deleteDocument,
  fetchDocuments,
  fetchIngestJob,
  reindexDocument,
  retryIngestJob,
  uploadDocument
} from "../../shared/api/modules/documents";
import { DocumentsPage } from "./DocumentsPage";

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
}));

vi.mock("../../shared/api/modules/documents", () => ({
  uploadDocument: vi.fn(),
  fetchDocuments: vi.fn(),
  deleteDocument: vi.fn(),
  reindexDocument: vi.fn(),
  fetchIngestJob: vi.fn(),
  cancelIngestJob: vi.fn(),
  retryIngestJob: vi.fn()
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

describe("DocumentsPage 二次确认交互", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();

    vi.mocked(fetchKbList).mockResolvedValue({
      items: [
        {
          kb_id: "kb-1",
          name: "测试知识库",
          visibility: "internal",
          updated_at: "2026-02-12T12:00:00Z"
        }
      ]
    });
    vi.mocked(fetchDocuments).mockResolvedValue({
      items: [
        {
          doc_id: "doc-1",
          kb_id: "kb-1",
          doc_name: "手册A",
          status: "indexed",
          chunk_count: 12,
          created_at: "2026-02-12T12:00:00Z",
          updated_at: "2026-02-12T12:00:00Z"
        }
      ]
    });
    vi.mocked(fetchIngestJob).mockImplementation(async (jobId: string) => {
      if (jobId === "job-2") {
        return {
          job_id: "job-2",
          kb_id: "kb-1",
          doc_id: "doc-1",
          status: "running",
          created_at: "2026-02-12T12:00:00Z",
          updated_at: "2026-02-12T12:00:00Z"
        };
      }
      return {
        job_id: jobId,
        kb_id: "kb-1",
        doc_id: "doc-1",
        status: "failed",
        created_at: "2026-02-12T12:00:00Z",
        updated_at: "2026-02-12T12:00:00Z"
      };
    });
    vi.mocked(uploadDocument).mockResolvedValue({
      doc: {
        doc_id: "doc-1",
        kb_id: "kb-1",
        doc_name: "手册A",
        status: "indexed",
        chunk_count: 12,
        created_at: "2026-02-12T12:00:00Z",
        updated_at: "2026-02-12T12:00:00Z"
      },
      job: {
        job_id: "job-1",
        kb_id: "kb-1",
        doc_id: "doc-1",
        status: "queued",
        created_at: "2026-02-12T12:00:00Z",
        updated_at: "2026-02-12T12:00:00Z"
      }
    });
    vi.mocked(deleteDocument).mockResolvedValue({ status: "ok" });
    vi.mocked(cancelIngestJob).mockResolvedValue({
      job_id: "job-1",
      kb_id: "kb-1",
      doc_id: "doc-1",
      status: "canceled",
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
    vi.mocked(reindexDocument).mockResolvedValue({
      job_id: "job-reindex",
      kb_id: "kb-1",
      doc_id: "doc-1",
      status: "queued",
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
    vi.mocked(retryIngestJob).mockResolvedValue({
      job_id: "job-retry",
      kb_id: "kb-1",
      doc_id: "doc-1",
      status: "queued",
      created_at: "2026-02-12T12:00:00Z",
      updated_at: "2026-02-12T12:00:00Z"
    });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("重建索引应先弹确认框，确认后再调用接口", async () => {
    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    const reindexButton = await screen.findByRole("button", { name: /重\s*建\s*索\s*引/ });
    await userEvent.click(reindexButton);

    expect(await screen.findByText("确认重建该文档索引？")).toBeInTheDocument();
    expect(reindexDocument).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /确\s*认\s*重\s*建/ }));
    await waitFor(() => {
      expect(reindexDocument).toHaveBeenCalledWith("doc-1");
    });
  });

  it("当前任务重试应先弹确认框，确认后再调用接口", async () => {
    window.localStorage.setItem("csage_ingest_jobs_kb-1", JSON.stringify(["job-1"]));

    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    await screen.findByText("任务跟踪中");
    const taskCardTitle = screen.getAllByText("入库任务状态")[0];
    const taskCard = taskCardTitle.closest(".ant-card");
    if (!(taskCard instanceof HTMLElement)) {
      throw new Error("未找到入库任务状态卡片");
    }
    const retryButton = within(taskCard).getByRole("button", { name: /重\s*试\s*任\s*务/ });
    await userEvent.click(retryButton);

    expect(await screen.findByText("确认重试当前任务？")).toBeInTheDocument();
    expect(reindexDocument).not.toHaveBeenCalled();
    expect(retryIngestJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /确\s*认\s*重\s*试/ }));
    await waitFor(() => {
      expect(retryIngestJob).toHaveBeenCalledTimes(1);
      expect(reindexDocument).not.toHaveBeenCalled();
    });
  });

  it("历史任务取消应先确认，确认后再调用接口", async () => {
    window.localStorage.setItem("csage_ingest_jobs_kb-1", JSON.stringify(["job-1", "job-2"]));

    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    const historyJobCell = await screen.findByText("running");
    const historyRow = historyJobCell.closest("tr");
    if (!(historyRow instanceof HTMLElement)) {
      throw new Error("未找到历史任务行");
    }

    const cancelButton = within(historyRow).getByRole("button", { name: /取\s*消/ });
    await userEvent.click(cancelButton);

    expect(await screen.findByText("确认取消该任务？")).toBeInTheDocument();
    expect(cancelIngestJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /确\s*认\s*取\s*消/ }));
    await waitFor(() => {
      expect(cancelIngestJob).toHaveBeenCalledWith("job-2");
    });
  });
});
