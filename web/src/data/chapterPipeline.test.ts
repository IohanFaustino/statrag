import { describe, it, expect } from "vitest";
import { CHAPTER_PIPELINE, FACILITATE_PIPELINE } from "./chapterPipeline";

describe("CHAPTER_PIPELINE", () => {
  it("has the main pipeline nodes in order ending at ground", () => {
    const ids = CHAPTER_PIPELINE.nodes.map((n) => n.id);
    expect(ids).toContain("parse");
    expect(ids).toContain("fetch");
    expect(ids).toContain("resolve");
    expect(ids).toContain("map");
    expect(ids).toContain("stitch");
    expect(ids).toContain("ground");
    // main chain order
    const mainIds = ids.filter((id) => id !== "clarify");
    expect(mainIds).toEqual(["parse", "fetch", "resolve", "map", "stitch", "ground"]);
  });

  it("edges include the main chain through every node", () => {
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "parse", to: "fetch" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "fetch", to: "resolve" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "resolve", to: "map" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "map", to: "stitch" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "stitch", to: "ground" });
  });

  it("parse node is relabeled to parse + resolve scope", () => {
    const parse = CHAPTER_PIPELINE.nodes.find((n) => n.id === "parse")!;
    expect(parse.label.toLowerCase()).toContain("resolve");
  });

  it("has a clarify node reachable from parse", () => {
    const clarify = CHAPTER_PIPELINE.nodes.find((n) => n.id === "clarify");
    expect(clarify).toBeTruthy();
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "parse", to: "clarify" });
  });
});

describe("FACILITATE_PIPELINE (story remake)", () => {
  it("has the correct 6 main nodes (no retrieve/teach)", () => {
    const ids = FACILITATE_PIPELINE.nodes.map((n) => n.id);
    expect(ids).toEqual(expect.arrayContaining(["parse", "fetch", "map", "write", "bind", "verify"]));
    expect(ids).not.toContain("retrieve");
    expect(ids).not.toContain("teach");
  });

  it("has exactly 7 nodes (6 main + clarify)", () => {
    expect(FACILITATE_PIPELINE.nodes).toHaveLength(7);
  });

  it("edges match parse→clarify, parse→fetch, fetch→map, map→write, write→bind, bind→verify", () => {
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "parse", to: "clarify" });
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "parse", to: "fetch" });
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "fetch", to: "map" });
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "map", to: "write" });
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "write", to: "bind" });
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "bind", to: "verify" });
  });

  it("write node is llm; bind and verify are data (pure code)", () => {
    const write = FACILITATE_PIPELINE.nodes.find((n) => n.id === "write")!;
    const bind = FACILITATE_PIPELINE.nodes.find((n) => n.id === "bind")!;
    const verify = FACILITATE_PIPELINE.nodes.find((n) => n.id === "verify")!;
    expect(write.kind).toBe("llm");
    expect(bind.kind).toBe("data");
    expect(verify.kind).toBe("data");
  });

  it("fetch node desc mentions ONE section and closest-match", () => {
    const fetch = FACILITATE_PIPELINE.nodes.find((n) => n.id === "fetch")!;
    expect(fetch.desc.toLowerCase()).toContain("one");
    expect(fetch.desc.toLowerCase()).toContain("closest");
  });

  it("verify node desc mentions pure-code / fidelity and NOT llm", () => {
    const verify = FACILITATE_PIPELINE.nodes.find((n) => n.id === "verify")!;
    expect(verify.desc.toLowerCase()).toContain("fidelity");
    expect(verify.defaultModel.toLowerCase()).toContain("pure code");
  });

  it("has a clarify node reachable from parse", () => {
    const clarify = FACILITATE_PIPELINE.nodes.find((n) => n.id === "clarify");
    expect(clarify).toBeTruthy();
    expect(FACILITATE_PIPELINE.edges).toContainEqual({ from: "parse", to: "clarify" });
  });
});
