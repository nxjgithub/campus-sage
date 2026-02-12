import { describe, expect, it } from "vitest";
import { normalizeApiError } from "./errors";

describe("normalizeApiError", () => {
  it("应处理普通 Error", () => {
    const result = normalizeApiError(new Error("boom"));
    expect(result.code).toBe("UNKNOWN_ERROR");
    expect(result.message).toBe("boom");
  });
});
