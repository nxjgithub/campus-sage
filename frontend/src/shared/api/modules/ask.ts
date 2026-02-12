import { apiClient } from "../client";

export interface AskFilters {
  doc_ids?: string[];
  published_after?: string;
}

export interface AskRequest {
  question: string;
  conversation_id?: string;
  topk?: number;
  threshold?: number;
  rerank_enabled?: boolean;
  filters?: AskFilters;
  debug?: boolean;
}

export interface CitationItem {
  citation_id: number;
  doc_id: string;
  doc_name: string;
  doc_version?: string | null;
  published_at?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  section_path?: string | null;
  chunk_id: string;
  snippet: string;
  score?: number | null;
}

export interface AskResponse {
  answer: string;
  refusal: boolean;
  refusal_reason?: string | null;
  suggestions: string[];
  citations: CitationItem[];
  conversation_id?: string | null;
  message_id?: string | null;
  timing?: Record<string, number> | null;
  request_id?: string | null;
}

export async function askByKb(kbId: string, payload: AskRequest) {
  const { data } = await apiClient.post<AskResponse>(`/kb/${kbId}/ask`, payload);
  return data;
}
