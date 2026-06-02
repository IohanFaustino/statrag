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
  it("renders io nodes and a dropdown per llm stage, fixed label for the data stage", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Question");
    expect(html).toContain("Answer");
    expect(html).toContain("node-dd__toggle");                       // llm nodes
    expect(html).toContain("pipe2__model-fixed");                    // retrieve (data)
    expect(html).toContain("RRF + rerank");
    expect(html).not.toContain("<select");
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{ generate: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
});
