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
