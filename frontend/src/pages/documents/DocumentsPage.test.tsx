import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
    <MemoryRouter initialEntries={["/admin/documents"]}>
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
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
          doc_name: "学生手册",
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
          progress: {
            stage: "embedding",
            pages_parsed: 12,
            chunks_built: 30,
            embeddings_done: 10,
            vectors_upserted: 4,
            stage_ms: 100,
            parse_ms: 50,
            chunk_ms: 50,
            embed_ms: 50,
            upsert_ms: 50
          },
          created_at: "2026-02-12T12:00:00Z",
          updated_at: "2026-02-12T12:00:00Z"
        };
      }
      return {
        job_id: jobId,
        kb_id: "kb-1",
        doc_id: "doc-1",
        status: "failed",
        progress: {
          stage: "finished",
          pages_parsed: 12,
          chunks_built: 30,
          embeddings_done: 30,
          vectors_upserted: 30,
          stage_ms: 100,
          parse_ms: 50,
          chunk_ms: 50,
          embed_ms: 50,
          upsert_ms: 50
        },
        created_at: "2026-02-12T12:00:00Z",
        updated_at: "2026-02-12T12:00:00Z"
      };
    });
    vi.mocked(uploadDocument).mockResolvedValue({
      doc: {
        doc_id: "doc-1",
        kb_id: "kb-1",
        doc_name: "学生手册",
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

  it("重建索引前先弹出确认框，确认后才调用接口", async () => {
    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    const docCell = await screen.findByText("学生手册");
    const row = docCell.closest("tr");
    if (!(row instanceof HTMLElement)) {
      throw new Error("未找到文档列表行");
    }

    await userEvent.click(within(row).getByRole("button", { name: /重建/ }));

    expect(await screen.findByText("确认重建该文档索引？")).toBeInTheDocument();
    expect(reindexDocument).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "确认重建" }));

    await waitFor(() => {
      expect(reindexDocument).toHaveBeenCalledWith("doc-1");
    });
  });

  it("当前任务重试前先弹出确认框，确认后才调用接口", async () => {
    window.localStorage.setItem("csage_ingest_jobs_kb-1", JSON.stringify(["job-1"]));

    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    const currentJobTitle = await screen.findByText("当前任务");
    const currentJobCard = currentJobTitle.closest(".ant-card");
    if (!(currentJobCard instanceof HTMLElement)) {
      throw new Error("未找到当前任务卡片");
    }

    await userEvent.click(within(currentJobCard).getByRole("button", { name: /重试/ }));

    expect(await screen.findByText("确认重试当前任务？")).toBeInTheDocument();
    expect(retryIngestJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "确认重试" }));

    await waitFor(() => {
      expect(retryIngestJob).toHaveBeenCalledWith("job-1");
    });
  });

  it("历史任务取消前先弹出确认框，确认后才调用接口", async () => {
    window.localStorage.setItem("csage_ingest_jobs_kb-1", JSON.stringify(["job-1", "job-2"]));

    renderWithProviders(<DocumentsPage initialKbId="kb-1" />);

    const cancelButtons = await screen.findAllByRole("button", { name: /取消历史任务/ });
    const cancelButton = cancelButtons.find((button) => !button.hasAttribute("disabled"));
    if (!(cancelButton instanceof HTMLButtonElement)) {
      throw new Error("未找到可点击的历史任务取消按钮");
    }
    await userEvent.click(cancelButton);

    expect(await screen.findByText("确认取消该任务？")).toBeInTheDocument();
    expect(cancelIngestJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "确认取消" }));

    await waitFor(() => {
      expect(cancelIngestJob).toHaveBeenCalledWith("job-2");
    });
  });
});
