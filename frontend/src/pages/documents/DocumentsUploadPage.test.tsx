import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntdApp } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchKbList } from "../../shared/api/modules/kb";
import {
  buildStagedPreview,
  commitStagedDocument,
  StagedDocument,
  updateStagedChunk,
  uploadStagedDocument
} from "../../shared/api/modules/documents";
import { DocumentsUploadPage } from "./DocumentsUploadPage";

vi.mock("../../shared/api/modules/kb", () => ({
  fetchKbList: vi.fn()
}));

vi.mock("../../shared/api/modules/documents", () => ({
  uploadStagedDocument: vi.fn(),
  buildStagedPreview: vi.fn(),
  updateStagedChunk: vi.fn(),
  commitStagedDocument: vi.fn()
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
      initialEntries={["/admin/documents/upload?kb=kb-1"]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <QueryClientProvider client={queryClient}>
        <AntdApp>{node}</AntdApp>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function createStagedDocument(overrides: Partial<StagedDocument> = {}): StagedDocument {
  return {
    staged_doc_id: "staged-1",
    kb_id: "kb-1",
    doc_name: "校园通知",
    filename: "校园通知.txt",
    extension: ".txt",
    source_type: "txt",
    status: "previewed",
    assets: [],
    pages: [{ text: "校园通知正文" }],
    preview_blocks: [],
    chunks: [
      {
        chunk_id: "chunk-1",
        chunk_index: 0,
        text: "校园通知正文",
        enabled: true,
        source_kind: "text"
      }
    ],
    warnings: [],
    created_at: "2026-05-29T12:00:00Z",
    updated_at: "2026-05-29T12:00:00Z",
    ...overrides
  };
}

function readFileText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(String(reader.result ?? ""));
    };
    reader.onerror = () => {
      reject(reader.error);
    };
    reader.readAsText(file);
  });
}

describe("DocumentsUploadPage 文本入库", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKbList).mockResolvedValue({
      items: [
        {
          kb_id: "kb-1",
          name: "测试知识库",
          visibility: "internal",
          updated_at: "2026-05-29T12:00:00Z"
        }
      ]
    });
    vi.mocked(uploadStagedDocument).mockResolvedValue(createStagedDocument({ status: "uploaded" }));
    vi.mocked(buildStagedPreview).mockResolvedValue(createStagedDocument());
    vi.mocked(updateStagedChunk).mockResolvedValue(createStagedDocument());
    vi.mocked(commitStagedDocument).mockResolvedValue({
      doc: {
        doc_id: "doc-1",
        kb_id: "kb-1",
        doc_name: "校园通知",
        status: "pending",
        chunk_count: 1,
        created_at: "2026-05-29T12:00:00Z",
        updated_at: "2026-05-29T12:00:00Z"
      },
      job: {
        job_id: "job-1",
        kb_id: "kb-1",
        doc_id: "doc-1",
        status: "queued",
        created_at: "2026-05-29T12:00:00Z",
        updated_at: "2026-05-29T12:00:00Z"
      }
    });
  });

  it("把粘贴文本封装为 TXT 文件并进入暂存预览流程", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DocumentsUploadPage />);

    await user.click(await screen.findByText("粘贴文本"));
    await user.type(screen.getByPlaceholderText("默认使用“粘贴文本”"), "校园通知");
    const pastedText = "这是一段可以直接粘贴入库的校园通知正文。";
    await user.type(
      screen.getByPlaceholderText(
        "粘贴一段公告、制度、问答材料或网页正文，系统会按 TXT 文档生成预览和分块。"
      ),
      pastedText
    );
    await user.click(screen.getByRole("button", { name: /上传并生成预览/ }));

    await waitFor(() => {
      expect(uploadStagedDocument).toHaveBeenCalledTimes(1);
    });
    const uploadParams = vi.mocked(uploadStagedDocument).mock.calls[0][0];
    expect(uploadParams.kbId).toBe("kb-1");
    expect(uploadParams.docName).toBe("校园通知");
    expect(uploadParams.file).toBeInstanceOf(File);
    expect(uploadParams.file.name).toBe("校园通知.txt");
    await expect(readFileText(uploadParams.file)).resolves.toBe(pastedText);
    expect(buildStagedPreview).toHaveBeenCalledWith("staged-1");
  });
});
