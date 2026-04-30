import { apiClient } from "../client";

export interface DocumentItem {
  doc_id: string;
  kb_id: string;
  doc_name: string;
  doc_version?: string | null;
  published_at?: string | null;
  source_uri?: string | null;
  status: "pending" | "processing" | "indexed" | "failed" | "deleted";
  error_message?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  request_id?: string | null;
}

export interface IngestProgress {
  stage: string;
  pages_parsed: number;
  chunks_built: number;
  embeddings_done: number;
  vectors_upserted: number;
  stage_ms: number;
  parse_ms: number;
  chunk_ms: number;
  embed_ms: number;
  upsert_ms: number;
}

export interface IngestJob {
  job_id: string;
  kb_id: string;
  doc_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress?: IngestProgress | null;
  error_message?: string | null;
  error_code?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
  request_id?: string | null;
}

export interface DocumentUploadResponse {
  doc: DocumentItem;
  job: IngestJob;
  request_id?: string | null;
}

export interface StagedAsset {
  asset_id: string;
  label: string;
  file_name: string;
  media_type: string;
  url: string;
  order_index: number;
  source: string;
}

export interface StagedPage {
  page_number?: number | null;
  text: string;
  section_path?: string | null;
}

export interface StagedChunk {
  chunk_id: string;
  chunk_index: number;
  text: string;
  page_start?: number | null;
  page_end?: number | null;
  section_path?: string | null;
  enabled: boolean;
  source_kind: string;
  asset_id?: string | null;
  asset_label?: string | null;
  asset_url?: string | null;
}

export interface StagedPreviewBlock {
  block_type: "heading" | "paragraph" | "table" | "image";
  order_index: number;
  text?: string | null;
  level?: number | null;
  rows?: string[][] | null;
  page_number?: number | null;
  section_path?: string | null;
  asset_id?: string | null;
  asset_label?: string | null;
  asset_url?: string | null;
}

export interface StagedDocument {
  staged_doc_id: string;
  kb_id: string;
  doc_name: string;
  doc_version?: string | null;
  published_at?: string | null;
  source_uri?: string | null;
  filename: string;
  extension: string;
  source_type: string;
  status: "uploaded" | "previewed";
  assets: StagedAsset[];
  pages: StagedPage[];
  preview_blocks: StagedPreviewBlock[];
  chunks: StagedChunk[];
  warnings: string[];
  created_at: string;
  updated_at: string;
  request_id?: string | null;
}

export async function fetchDocuments(kbId: string) {
  const { data } = await apiClient.get<DocumentListResponse>(`/kb/${kbId}/documents`);
  return data;
}

export async function uploadDocument(params: {
  kbId: string;
  file: File;
  docName?: string;
  docVersion?: string;
  publishedAt?: string;
  sourceUri?: string;
}) {
  const formData = new FormData();
  formData.append("file", params.file);
  if (params.docName) {
    formData.append("doc_name", params.docName);
  }
  if (params.docVersion) {
    formData.append("doc_version", params.docVersion);
  }
  if (params.publishedAt) {
    formData.append("published_at", params.publishedAt);
  }
  if (params.sourceUri) {
    formData.append("source_uri", params.sourceUri);
  }
  const { data } = await apiClient.post<DocumentUploadResponse>(
    `/kb/${params.kbId}/documents`,
    formData
  );
  return data;
}

export async function uploadStagedDocument(params: {
  kbId: string;
  file: File;
  docName?: string;
  docVersion?: string;
  publishedAt?: string;
  sourceUri?: string;
}) {
  const formData = new FormData();
  formData.append("file", params.file);
  if (params.docName) {
    formData.append("doc_name", params.docName);
  }
  if (params.docVersion) {
    formData.append("doc_version", params.docVersion);
  }
  if (params.publishedAt) {
    formData.append("published_at", params.publishedAt);
  }
  if (params.sourceUri) {
    formData.append("source_uri", params.sourceUri);
  }
  const { data } = await apiClient.post<StagedDocument>(
    `/kb/${params.kbId}/documents/staged`,
    formData
  );
  return data;
}

export async function buildStagedPreview(stagedDocId: string) {
  const { data } = await apiClient.post<StagedDocument>(
    `/staged-documents/${stagedDocId}/preview`
  );
  return data;
}

export async function updateStagedChunk(params: {
  stagedDocId: string;
  chunkId: string;
  enabled?: boolean;
  text?: string;
}) {
  const { data } = await apiClient.patch<StagedDocument>(
    `/staged-documents/${params.stagedDocId}/chunks/${params.chunkId}`,
    {
      enabled: params.enabled,
      text: params.text
    }
  );
  return data;
}

export async function commitStagedDocument(stagedDocId: string) {
  const { data } = await apiClient.post<DocumentUploadResponse>(
    `/staged-documents/${stagedDocId}/commit`
  );
  return data;
}

export async function deleteDocument(docId: string) {
  const { data } = await apiClient.delete<{ status: string; request_id?: string | null }>(
    `/documents/${docId}`
  );
  return data;
}

export async function reindexDocument(docId: string) {
  const { data } = await apiClient.post<IngestJob>(`/documents/${docId}/reindex`);
  return data;
}

export async function fetchIngestJob(jobId: string) {
  const { data } = await apiClient.get<IngestJob>(`/ingest/jobs/${jobId}`);
  return data;
}

export async function cancelIngestJob(jobId: string) {
  const { data } = await apiClient.post<IngestJob>(`/ingest/jobs/${jobId}/cancel`);
  return data;
}

export async function retryIngestJob(jobId: string) {
  const { data } = await apiClient.post<IngestJob>(`/ingest/jobs/${jobId}/retry`);
  return data;
}
