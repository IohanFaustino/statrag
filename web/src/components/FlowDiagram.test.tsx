import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FlowDiagram, { type FlowNode } from "./FlowDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

const NODES: FlowNode[] = [
  { id: "scope", label: "Scope extract", desc: "narrows the gap", kind: "llm", defaultModel: "gpt-5.4-nano-2026-03-17" },
  { id: "retrieve", label: "Hybrid retrieval", desc: "dense + sparse", kind: "data", defaultModel: "text-embedding-3-large" },
];

describe("FlowDiagram", () => {
  it("renders dashed io nodes for input + output labels", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Question" outputLabel="Answer"
        providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Question");
    expect(html).toContain("Answer");
  });
  it("renders a dropdown for llm nodes and a fixed label for data nodes, with connectors", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Question" outputLabel="Answer"
        providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("node-dd__toggle");          // llm scope
    expect(html).toContain("pipe2__model-fixed");        // data retrieve
    expect(html).toContain("text-embedding-3-large");
    expect(html).toContain("flow__arrow");               // connectors present
    expect(html).toContain("narrows the gap");           // desc rendered
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram nodes={NODES} inputLabel="Q" outputLabel="A"
        providers={PROVIDERS} stageModels={{ scope: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
  it("tags each node with its phase (data-phase)", () => {
    const html = renderToStaticMarkup(
      <FlowDiagram
        nodes={[
          { id: "scope",    label: "Scope",    desc: "d", kind: "llm",  defaultModel: "m" },
          { id: "retrieve", label: "Retrieve", desc: "d", kind: "data", defaultModel: "" },
          { id: "generate", label: "Generate", desc: "d", kind: "llm",  defaultModel: "m" },
        ]}
        inputLabel="Question"
        outputLabel="Answer"
        providers={[]}
        stageModels={{}}
        onStageModelChange={() => {}}
      />,
    );
    expect(html).toContain('data-phase="planning"');   // scope
    expect(html).toContain('data-phase="retrieval"');  // retrieve
    expect(html).toContain('data-phase="generation"'); // generate
  });
});
