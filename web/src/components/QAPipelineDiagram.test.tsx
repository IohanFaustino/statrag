import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAPipelineDiagram from "./QAPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

describe("QAPipelineDiagram", () => {
  it("renders io nodes and a dropdown per llm stage, fixed label for the data stages", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Question");
    expect(html).toContain("Answer");
    expect(html).toContain("node-dd__toggle");                       // llm nodes have dropdowns
    expect(html).toContain("pipe2__model-fixed");                    // data nodes (retrieve, bind) have fixed labels
    expect(html).not.toContain("<select");
  });

  it("reflects a stageModels override for the write node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{ write: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });

  it("renders the write node label", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html.toLowerCase()).toMatch(/story|write|narrative/);
  });

  it("renders the bind node as a data node (no dropdown)", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    // bind node is data kind — rendered as fixed model text, not as a dropdown
    expect(html).toContain("pipe2__model-fixed");
  });

  it("does NOT render a generate node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    // "generate" node should not appear in the diagram
    expect(html.toLowerCase()).not.toContain("scoped generate");
  });
});
