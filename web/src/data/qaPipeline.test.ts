import { describe, it, expect } from "vitest";
import { QA_PIPELINE } from "./qaPipeline";

describe("QA_PIPELINE", () => {
  it("has the main pipeline nodes in order", () => {
    const ids = QA_PIPELINE.nodes.map((n) => n.id);
    // main chain order (excluding terminal clarify branch)
    const mainIds = ids.filter((id) => id !== "clarify");
    expect(mainIds).toEqual(["scope", "retrieve", "generate", "verify"]);
  });
  it("edges include the main chain", () => {
    expect(QA_PIPELINE.edges).toContainEqual({ from: "scope", to: "retrieve" });
    expect(QA_PIPELINE.edges).toContainEqual({ from: "retrieve", to: "generate" });
    expect(QA_PIPELINE.edges).toContainEqual({ from: "generate", to: "verify" });
  });
  it("scope node label mentions resolve", () => {
    const scope = QA_PIPELINE.nodes.find((n) => n.id === "scope")!;
    expect(scope.label.toLowerCase()).toContain("resolve");
  });
  it("has a clarify node reachable from scope", () => {
    const clarify = QA_PIPELINE.nodes.find((n) => n.id === "clarify");
    expect(clarify).toBeTruthy();
    expect(QA_PIPELINE.edges).toContainEqual({ from: "scope", to: "clarify" });
  });
});
