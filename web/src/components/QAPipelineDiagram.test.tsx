import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAPipelineDiagram from "./QAPipelineDiagram";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "openai", name: "OpenAI", short: "OAI", color: "#10A37F",
    models: [{ id: "gpt-4o", name: "GPT-4o", tagline: "x", cost: "$$$", speed: "fast", ctx: "128k" }],
  },
];

describe("QAPipelineDiagram", () => {
  it("renders a swappable dropdown for each LLM node and a fixed label for the data node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram providers={PROVIDERS} stageModels={{}} onStageModelChange={() => {}} />,
    );
    // scope / generate / verify are llm → custom dropdown toggles
    expect(html).toContain("node-dd__toggle");
    expect(html).not.toContain("<select");
    // retrieve is a data node → fixed label, no dropdown for it
    expect(html).toContain("qa-pipeline__node--data");
    expect(html).toContain("text-embedding-3-large → RRF + rerank");
  });

  it("reflects a stageModels override on the matching node", () => {
    const html = renderToStaticMarkup(
      <QAPipelineDiagram
        providers={PROVIDERS}
        stageModels={{ generate: "gpt-4o" }}
        onStageModelChange={() => {}}
      />,
    );
    expect(html).toContain("GPT-4o");
  });
});
