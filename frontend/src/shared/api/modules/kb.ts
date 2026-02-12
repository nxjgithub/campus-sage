import { apiClient } from "../client";

export interface KbConfig {
  topk: number;
  threshold: number;
  rerank_enabled: boolean;
  max_context_tokens: number;
  min_context_chars?: number;
  min_keyword_coverage?: number;
}

export interface KbItem {
  kb_id: string;
  name: string;
  description?: string | null;
  visibility: "public" | "internal" | "admin";
  config?: KbConfig;
  created_at?: string;
  updated_at: string;
  request_id?: string | null;
}

export interface KbListResponse {
  items: KbItem[];
  request_id?: string | null;
}

export interface KbCreateRequest {
  name: string;
  description?: string | null;
  visibility?: "public" | "internal" | "admin";
  config?: KbConfig;
}

export interface KbUpdateRequest {
  description?: string | null;
  visibility?: "public" | "internal" | "admin";
  config?: Partial<KbConfig>;
}

export interface KbDetail {
  kb_id: string;
  name: string;
  description: string | null;
  visibility: "public" | "internal" | "admin";
  config: KbConfig;
  created_at: string;
  updated_at: string;
  request_id?: string | null;
}

export async function fetchKbList() {
  const { data } = await apiClient.get<KbListResponse>("/kb");
  return data;
}

export async function createKb(payload: KbCreateRequest) {
  const { data } = await apiClient.post<KbDetail>("/kb", payload);
  return data;
}

export async function fetchKbDetail(kbId: string) {
  const { data } = await apiClient.get<KbDetail>(`/kb/${kbId}`);
  return data;
}

export async function updateKb(kbId: string, payload: KbUpdateRequest) {
  const { data } = await apiClient.patch<KbDetail>(`/kb/${kbId}`, payload);
  return data;
}

export async function deleteKb(kbId: string) {
  const { data } = await apiClient.delete<{ status: string; request_id?: string | null }>(
    `/kb/${kbId}`
  );
  return data;
}
