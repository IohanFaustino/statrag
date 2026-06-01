import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import ChapterPipelineDiagram from "./ChapterPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  { id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }] },
];

describe("ChapterPipelineDiagram", () => {
  it("renders io nodes, dropdowns for llm stages, fixed label for fetch (data)", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(html).toContain("pipe2__node--io");
    expect(html).toContain("Chapter digest");
    expect(html).toContain("node-dd__toggle");
    expect(html).toContain("pipe2__model-fixed");
    expect(html).toContain("qdrant scroll (book + chapter filter)");
    expect(html).not.toContain("<select");
  });
  it("uses mode-specific copy on the map node", () => {
    const fac = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    const res = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />);
    expect(fac).toContain("teach each section");
    expect(res).toContain("compress each section");
  });
  it("reflects a stageModels override", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{ map: "gpt-4o" }} onStageModelChange={() => {}} />);
    expect(html).toContain("GPT-4o");
  });
});
