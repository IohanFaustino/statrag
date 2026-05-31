import { describe, it, expect } from "vitest";
import { QA_PIPELINE } from "./qaPipeline";

describe("QA_PIPELINE", () => {
  it("has the four pipeline nodes in order", () => {
    const ids = QA_PIPELINE.nodes.map((n) => n.id);
    expect(ids).toEqual(["scope", "retrieve", "generate", "verify"]);
  });
  it("edges connect the chain", () => {
    expect(QA_PIPELINE.edges).toEqual([
      { from: "scope", to: "retrieve" },
      { from: "retrieve", to: "generate" },
      { from: "generate", to: "verify" },
    ]);
  });
});
