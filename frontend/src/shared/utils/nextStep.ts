import { CitationItem, NextStepItem } from "../api/modules/ask";

export function isOfficialSourceUrl(value?: string | null) {
  if (!value) {
    return false;
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function resolveOfficialSourceUrl(step: NextStepItem, citations: CitationItem[]) {
  if (isOfficialSourceUrl(step.value)) {
    return step.value as string;
  }
  const candidate = citations.find((citation) => isOfficialSourceUrl(citation.source_uri));
  return candidate?.source_uri ?? null;
}

export interface ReviewNextStepResolution {
  kind: "open" | "copy" | "info";
  payload: string;
}

export function resolveReviewNextStep(
  step: NextStepItem,
  citations: CitationItem[]
): ReviewNextStepResolution {
  if (step.action === "check_official_source") {
    const sourceUrl = resolveOfficialSourceUrl(step, citations);
    if (sourceUrl) {
      return {
        kind: "open",
        payload: sourceUrl
      };
    }
    return {
      kind: "info",
      payload: "当前消息未提供可直接打开的官方来源，请结合引用片段继续核对。"
    };
  }

  if (step.action === "verify_kb_scope") {
    return {
      kind: "info",
      payload: "请到知识库治理或文档管理页核对当前收录范围。"
    };
  }

  const value = step.value?.trim() ?? "";
  if (value) {
    return {
      kind: "copy",
      payload: value
    };
  }

  return {
    kind: "info",
    payload: step.detail
  };
}
