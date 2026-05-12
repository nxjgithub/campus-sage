import { apiClient } from "../client";

export interface QueueStats {
  queued: number;
  started: number;
  deferred: number;
  finished: number;
  failed_registry: number;
  dead: number;
  scheduled: number;
}

export interface QueueStatsResponse {
  stats: QueueStats;
  alerts: string[];
  request_id?: string | null;
}

export interface RuntimeDiagnosticsResponse {
  app_env: string;
  log_level: string;
  debug_mode: boolean;
  enable_swagger: boolean;
  database: {
    backend: string;
    target: string;
    schema_version: number;
  };
  services: {
    vector_backend: string;
    embedding_backend: string;
    rerank_backend: string;
    vllm_enabled: boolean;
    ingest_queue_enabled: boolean;
  };
  upload: {
    max_mb: number;
    allowed_exts: string[];
  };
  security: {
    jwt_default_secret: boolean;
    jwt_weak_secret: boolean;
  };
  rag_metrics: {
    sample_size: number;
    refusal_count: number;
    clarification_count: number;
    freshness_warning_count: number;
    citation_covered_count: number;
    refusal_rate: number;
    clarification_rate: number;
    freshness_warning_rate: number;
    citation_coverage_rate: number;
  };
  warnings: string[];
  request_id?: string | null;
}

export async function fetchQueueStats() {
  const { data } = await apiClient.get<QueueStatsResponse>("/monitor/queues");
  return data;
}

export async function fetchRuntimeDiagnostics() {
  const { data } = await apiClient.get<RuntimeDiagnosticsResponse>("/monitor/runtime");
  return data;
}

export async function moveDeadJobs() {
  const { data } = await apiClient.post<{ moved: number; request_id?: string | null }>(
    "/monitor/queues/ingest/move-dead"
  );
  return data;
}
