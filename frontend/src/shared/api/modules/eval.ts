import { apiClient } from "../client";

export interface EvalItemCreatePayload {
  question: string;
  gold_doc_id?: string;
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

export async function createEvalSet(payload: EvalSetCreatePayload) {
  const { data } = await apiClient.post<EvalSetResponse>("/eval/sets", payload);
  return data;
}

export async function runEval(payload: EvalRunPayload) {
  const { data } = await apiClient.post<EvalRunResponse>("/eval/runs", payload);
  return data;
}

export async function fetchEvalRun(runId: string) {
  const { data } = await apiClient.get<EvalRunResponse>(`/eval/runs/${runId}`);
  return data;
}
