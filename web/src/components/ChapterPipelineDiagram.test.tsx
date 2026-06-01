import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import ChapterPipelineDiagram from "./ChapterPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }],
  },
];

describe("ChapterPipelineDiagram", () => {
  it("renders dropdowns for LLM nodes and a fixed label for the fetch (data) node", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    expect(html).toContain("node-dd__toggle");
    expect(html).not.toContain("<select");
    expect(html).toContain("qa-pipeline__node--data");
    expect(html).toContain("qdrant scroll (book + chapter filter)");
  });

  it("uses mode-specific copy on the map node", () => {
    const fac = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="facilitate" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    const res = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    expect(fac).toContain("teach each section");
    expect(res).toContain("compress each section");
  });

  it("reflects a stageModels override on the matching node", () => {
    const html = renderToStaticMarkup(
      <ChapterPipelineDiagram mode="resume" providers={PROVIDERS} stageModels={{ map: "gpt-4o" }} onStageModelChange={() => {}} />,
    );
    expect(html).toContain("GPT-4o");
  });
});
