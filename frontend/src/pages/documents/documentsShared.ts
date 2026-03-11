import { DocumentItem, IngestJob } from "../../shared/api/modules/documents";

export interface UploadFormValues {
  kb_id: string;
  doc_name?: string;
  doc_version?: string;
  published_at?: string;
  source_uri?: string;
}

export type TableDensity = "middle" | "small";
export type DocumentStatusFilter = "all" | DocumentItem["status"];

export const FINAL_JOB_STATUS = new Set(["succeeded", "failed", "canceled"]);
export const JOB_HISTORY_LIMIT = 40;
export const UPLOAD_ACCEPT = ".pdf,.docx,.html,.htm,.md,.txt";
export const UPLOAD_FORMAT_HINT = "支持 PDF、DOCX、HTML、Markdown、TXT";

export const DOCUMENT_STATUS_META: Record<DocumentItem["status"], { label: string; color: string }> =
  {
    pending: { label: "待处理", color: "default" },
    processing: { label: "处理中", color: "processing" },
    indexed: { label: "已索引", color: "success" },
    failed: { label: "失败", color: "error" },
    deleted: { label: "已删除", color: "default" }
  };

export const JOB_STATUS_META: Record<IngestJob["status"], { label: string; color: string }> = {
  queued: { label: "排队中", color: "default" },
  running: { label: "执行中", color: "processing" },
  succeeded: { label: "已完成", color: "success" },
  failed: { label: "失败", color: "error" },
  canceled: { label: "已取消", color: "warning" }
};

export const JOB_STAGE_LABEL: Record<string, string> = {
  queued: "等待调度",
  parsing: "解析文档",
  chunking: "切分内容",
  embedding: "生成向量",
  upserting: "写入索引",
  finished: "已完成"
};

export const JOB_STAGE_ORDER: Record<string, number> = {
  queued: 0,
  parsing: 1,
  chunking: 2,
  embedding: 3,
  upserting: 4,
  finished: 5
};

export function getJobHistoryStorageKey(kbId: string) {
  return `csage_ingest_jobs_${kbId}`;
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function getJobStageLabel(stage?: string | null) {
  if (!stage) {
    return "-";
  }
  return JOB_STAGE_LABEL[stage] ?? stage;
}

export function readJobHistoryIds(kbId: string) {
  if (typeof window === "undefined") {
    return [] as string[];
  }
  try {
    const raw = window.localStorage.getItem(getJobHistoryStorageKey(kbId));
    const parsed = raw ? (JSON.parse(raw) as string[]) : [];
    return parsed.filter((item) => typeof item === "string");
  } catch {
    return [];
  }
}

export function writeJobHistoryIds(kbId: string, ids: string[]) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(getJobHistoryStorageKey(kbId), JSON.stringify(ids));
  } catch {
    // 本地缓存失败时不阻塞主流程。
  }
}

export function pushJobHistoryId(kbId: string, jobId: string) {
  const next = [jobId, ...readJobHistoryIds(kbId).filter((item) => item !== jobId)].slice(
    0,
    JOB_HISTORY_LIMIT
  );
  writeJobHistoryIds(kbId, next);
  return next;
}
