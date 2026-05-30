import { apiClient } from "../client";

export interface EvalItemCreatePayload {
  question: string;
  gold_doc_id?: string;
  gold_doc_name?: string;
  gold_page_start?: number;
  gold_page_end?: number;
  tags?: string[];
}

export interface EvalSetCreatePayload {
  name: string;
  description?: string;
  items: EvalItemCreatePayload[];
}

export interface EvalSetResponse {
  eval_set_id: string;
  name: string;
  description?: string | null;
  item_count: number;
  created_at: string;
  request_id?: string | null;
}

export interface EvalSetListResponse {
  items: EvalSetResponse[];
  request_id?: string | null;
}

export interface EvalRunPayload {
  eval_set_id: string;
  kb_id: string;
  topk: number;
  threshold?: number;
  rerank_enabled?: boolean;
}

export interface EvalMetrics {
  recall_at_k: number;
  mrr: number;
  avg_ms: number;
  p95_ms: number;
  samples: number;
}

export interface EvalRunResponse {
  run_id: string;
  eval_set_id: string;
  kb_id: string;
  topk: number;
  threshold?: number | null;
  rerank_enabled: boolean;
  metrics?: EvalMetrics | null;
  created_at: string;
  request_id?: string | null;
}

export interface EvalRunListParams {
  limit?: number;
  offset?: number;
}

export interface EvalRunListResponse {
  items: EvalRunResponse[];
  request_id?: string | null;
}

export interface EvalCandidatePreview {
  rank: number;
  doc_id?: string | null;
  doc_name?: string | null;
  score?: number | null;
  matched: boolean;
}

export interface EvalRunItemResult {
  eval_item_id: string;
  question: string;
  gold_doc_id?: string | null;
  gold_doc_name?: string | null;
  hit: boolean;
  rank?: number | null;
  retrieve_ms?: number | null;
  raw_rank?: number | null;
  threshold_rank?: number | null;
  raw_hit_count?: number | null;
  threshold_hit_count?: number | null;
  final_hit_count?: number | null;
  top_candidates: EvalCandidatePreview[];
}

export interface EvalRunItemResultListResponse {
  items: EvalRunItemResult[];
  request_id?: string | null;
}

export async function createEvalSet(payload: EvalSetCreatePayload) {
  const { data } = await apiClient.post<EvalSetResponse>("/eval/sets", payload);
  return data;
}

export async function fetchEvalSets() {
  const { data } = await apiClient.get<EvalSetListResponse>("/eval/sets");
  return data;
}

export async function runEval(payload: EvalRunPayload) {
  const { data } = await apiClient.post<EvalRunResponse>("/eval/runs", payload);
  return data;
}

export async function fetchEvalRuns(params: EvalRunListParams = {}) {
  const { data } = await apiClient.get<EvalRunListResponse>("/eval/runs", {
    params
  });
  return data;
}

export async function fetchEvalRun(runId: string) {
  const { data } = await apiClient.get<EvalRunResponse>(`/eval/runs/${runId}`);
  return data;
}

export async function fetchEvalRunResults(runId: string) {
  const { data } = await apiClient.get<EvalRunItemResultListResponse>(`/eval/runs/${runId}/results`);
  return data;
}
