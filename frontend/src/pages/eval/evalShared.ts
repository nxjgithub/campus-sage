export interface EvalItemFormRow {
  question: string;
  gold_page_start?: number;
  gold_page_end?: number;
  tags_text?: string;
}

export interface EvalSetFormValues {
  name: string;
  description?: string;
  items: EvalItemFormRow[];
}

export interface EvalRunFormValues {
  eval_set_id: string;
  kb_id: string;
  topk: number;
  threshold?: number;
  rerank_enabled?: boolean;
}

export interface FetchRunFormValues {
  run_id: string;
}

export type TableDensity = "middle" | "small";

export interface RecentEvalSetOption {
  eval_set_id: string;
  name: string;
  created_at: string;
}

export interface RecentEvalRunOption {
  run_id: string;
  eval_set_id: string;
  kb_id: string;
  created_at: string;
}

const RECENT_EVAL_SET_STORAGE_KEY = "csage_recent_eval_sets";
const RECENT_EVAL_RUN_STORAGE_KEY = "csage_recent_eval_runs";
const RECENT_OPTION_LIMIT = 10;

export function parseTags(value?: string) {
  if (!value) {
    return undefined;
  }
  const tags = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return tags.length ? tags : undefined;
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

export function formatMetric(value?: number | null) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(3);
}

function readList<T>(storageKey: string) {
  if (typeof window === "undefined") {
    return [] as T[];
  }
  try {
    const raw = window.localStorage.getItem(storageKey);
    return raw ? ((JSON.parse(raw) as T[]) ?? []) : [];
  } catch {
    return [];
  }
}

function writeList<T>(storageKey: string, items: T[]) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(items));
  } catch {
    // 本地缓存失败时不阻塞评测主流程。
  }
}

export function readRecentEvalSets() {
  return readList<RecentEvalSetOption>(RECENT_EVAL_SET_STORAGE_KEY);
}

export function writeRecentEvalSets(items: RecentEvalSetOption[]) {
  writeList(RECENT_EVAL_SET_STORAGE_KEY, items);
}

export function pushRecentEvalSet(item: RecentEvalSetOption) {
  const next = [item, ...readRecentEvalSets().filter((current) => current.eval_set_id !== item.eval_set_id)].slice(
    0,
    RECENT_OPTION_LIMIT
  );
  writeRecentEvalSets(next);
  return next;
}

export function readRecentEvalRuns() {
  return readList<RecentEvalRunOption>(RECENT_EVAL_RUN_STORAGE_KEY);
}

export function writeRecentEvalRuns(items: RecentEvalRunOption[]) {
  writeList(RECENT_EVAL_RUN_STORAGE_KEY, items);
}

export function pushRecentEvalRun(item: RecentEvalRunOption) {
  const next = [item, ...readRecentEvalRuns().filter((current) => current.run_id !== item.run_id)].slice(
    0,
    RECENT_OPTION_LIMIT
  );
  writeRecentEvalRuns(next);
  return next;
}
