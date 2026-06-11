import { describe, it, expect } from "vitest";
import { QA_PIPELINE } from "./qaPipeline";

describe("QA_PIPELINE", () => {
  it("has the main pipeline nodes in order: scope, retrieve, write, bind, verify", () => {
    const ids = QA_PIPELINE.nodes.map((n) => n.id);
    const mainIds = ids.filter((id) => id !== "clarify");
    expect(mainIds).toEqual(["scope", "retrieve", "write", "bind", "verify"]);
  });

  it("edges connect scope→retrieve, retrieve→write, write→bind, bind→verify", () => {
    expect(QA_PIPELINE.edges).toContainEqual({ from: "scope", to: "retrieve" });
    expect(QA_PIPELINE.edges).toContainEqual({ from: "retrieve", to: "write" });
    expect(QA_PIPELINE.edges).toContainEqual({ from: "write", to: "bind" });
    expect(QA_PIPELINE.edges).toContainEqual({ from: "bind", to: "verify" });
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

  it("bind node is kind 'data' (pure-code, no model)", () => {
    const bind = QA_PIPELINE.nodes.find((n) => n.id === "bind")!;
    expect(bind).toBeTruthy();
    expect(bind.kind).toBe("data");
  });

  it("write node is kind 'llm'", () => {
    const write = QA_PIPELINE.nodes.find((n) => n.id === "write")!;
    expect(write).toBeTruthy();
    expect(write.kind).toBe("llm");
  });

  it("write node description mentions storytelling", () => {
    const write = QA_PIPELINE.nodes.find((n) => n.id === "write")!;
    expect(write.desc.toLowerCase()).toMatch(/story|narrative|intro|deepening|conclusion/);
  });

  it("bind node description mentions citation binding (no model)", () => {
    const bind = QA_PIPELINE.nodes.find((n) => n.id === "bind")!;
    expect(bind.desc.toLowerCase()).toMatch(/cit|bind|\[\[eid\]\]/i);
  });

  it("retrieve node description mentions both corpus and wiki", () => {
    const retrieve = QA_PIPELINE.nodes.find((n) => n.id === "retrieve")!;
    expect(retrieve.desc.toLowerCase()).toMatch(/wiki|corpus|parallel/);
  });

  it("does NOT have a generate node (replaced by write)", () => {
    const gen = QA_PIPELINE.nodes.find((n) => (n.id as string) === "generate");
    expect(gen).toBeUndefined();
  });
});
