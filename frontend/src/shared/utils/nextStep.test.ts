import { describe, expect, it } from "vitest";
import { CitationItem, NextStepItem } from "../api/modules/ask";
import { resolveOfficialSourceUrl, resolveReviewNextStep } from "./nextStep";

describe("nextStep 工具", () => {
  it("应优先使用 next_step 自带的官方来源链接", () => {
    const step: NextStepItem = {
      action: "check_official_source",
      label: "查看官方来源",
      detail: "查看官网",
      value: "https://example.edu/policy"
    };

    expect(resolveOfficialSourceUrl(step, [])).toBe("https://example.edu/policy");
  });

  it("应在 next_step 无链接时回退到引用中的官方来源", () => {
    const step: NextStepItem = {
      action: "check_official_source",
      label: "查看官方来源",
      detail: "查看官网",
      value: null
    };
    const citations: CitationItem[] = [
      {
        citation_id: 1,
        doc_id: "doc_1",
        doc_name: "教务处通知",
        chunk_id: "chunk_1",
        snippet: "以官网通知为准",
        source_uri: "https://example.edu/notice"
      }
    ];

    expect(resolveOfficialSourceUrl(step, citations)).toBe("https://example.edu/notice");
  });

  it("历史会话中的文本型建议应解析为复制动作", () => {
    const step: NextStepItem = {
      action: "add_context",
      label: "补充场景条件",
      detail: "补充学院、年级、学生类型或办理场景。",
      value: "学院/年级/身份/办理场景"
    };

    expect(resolveReviewNextStep(step, [])).toEqual({
      kind: "copy",
      payload: "学院/年级/身份/办理场景"
    });
  });

  it("历史会话中的官网建议应解析为打开外链动作", () => {
    const step: NextStepItem = {
      action: "check_official_source",
      label: "查看官方来源",
      detail: "查看官网",
      value: "https://example.edu/policy"
    };

    expect(resolveReviewNextStep(step, [])).toEqual({
      kind: "open",
      payload: "https://example.edu/policy"
    });
  });
});
