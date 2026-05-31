import { describe, it, expect } from "vitest";
import type { ModeId, QAAnswer, QAScope } from "./types";

describe("qa types", () => {
  it("ModeId includes qa", () => {
    const m: ModeId = "qa";
    expect(m).toBe("qa");
  });
  it("QAAnswer shape", () => {
    const scope: QAScope = { target_gap: "x", assumed_known: [], answer_form: "explanation" };
    const a: QAAnswer = { text: "t", scope, citations: [], math_blocks: [], grounding: { ok: true, unsupported: [], confidence: 0.9 } };
    expect(a.scope.target_gap).toBe("x");
  });
});
