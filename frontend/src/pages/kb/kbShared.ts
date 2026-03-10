import { KbConfig } from "../../shared/api/modules/kb";

export interface KbFormValues {
  name: string;
  description?: string;
  visibility: "public" | "internal" | "admin";
  topk: number;
  threshold: number;
  rerank_enabled: boolean;
  max_context_tokens: number;
  min_context_chars: number;
  min_keyword_coverage: number;
}

export interface KbEditValues {
  description?: string;
  visibility: "public" | "internal" | "admin";
  topk: number;
  threshold: number;
  rerank_enabled: boolean;
  max_context_tokens: number;
  min_context_chars: number;
  min_keyword_coverage: number;
}

export type VisibilityFilter = "all" | "public" | "internal" | "admin";
export type TableDensity = "middle" | "small";

export const DEFAULT_KB_FORM_VALUES: KbFormValues = {
  visibility: "internal",
  topk: 5,
  threshold: 0.25,
  rerank_enabled: false,
  max_context_tokens: 3000,
  min_context_chars: 20,
  min_keyword_coverage: 0.3,
  name: "",
  description: ""
};

export function resolveVisibilityColor(value: VisibilityFilter | KbFormValues["visibility"]) {
  if (value === "public") {
    return "success";
  }
  if (value === "admin") {
    return "error";
  }
  return "processing";
}

export function formatDateParts(value?: string | null) {
  if (!value) {
    return { date: "-", time: "" };
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { date: value, time: "" };
  }
  return {
    date: new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).format(date),
    time: new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit"
    }).format(date)
  };
}

export function buildKbConfig(values: Pick<
  KbFormValues,
  "topk" | "threshold" | "rerank_enabled" | "max_context_tokens" | "min_context_chars" | "min_keyword_coverage"
>): KbConfig {
  return {
    topk: values.topk,
    threshold: values.threshold,
    rerank_enabled: values.rerank_enabled,
    max_context_tokens: values.max_context_tokens,
    min_context_chars: values.min_context_chars,
    min_keyword_coverage: values.min_keyword_coverage
  };
}
