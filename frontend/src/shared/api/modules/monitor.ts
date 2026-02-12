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

export async function fetchQueueStats() {
  const { data } = await apiClient.get<QueueStatsResponse>("/monitor/queues");
  return data;
}

export async function moveDeadJobs() {
  const { data } = await apiClient.post<{ moved: number; request_id?: string | null }>(
    "/monitor/queues/ingest/move-dead"
  );
  return data;
}
