import { describe, expect, it } from "vitest";
import { splitCitationMarkers } from "./citation";

describe("splitCitationMarkers", () => {
  it("无引用标记时应返回单个文本分片", () => {
    expect(splitCitationMarkers("普通回答")).toEqual([
      { type: "text", value: "普通回答" }
    ]);
  });

  it("应正确切分多个引用标记", () => {
    expect(splitCitationMarkers("依据[1]与[2]得出结论")).toEqual([
      { type: "text", value: "依据" },
      { type: "marker", citationId: 1, marker: "[1]" },
      { type: "text", value: "与" },
      { type: "marker", citationId: 2, marker: "[2]" },
      { type: "text", value: "得出结论" }
    ]);
  });

  it("相邻标记应连续解析", () => {
    expect(splitCitationMarkers("见[3][4]")).toEqual([
      { type: "text", value: "见" },
      { type: "marker", citationId: 3, marker: "[3]" },
      { type: "marker", citationId: 4, marker: "[4]" }
    ]);
  });
});
