import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import NodeModelDropdown from "./NodeModelDropdown";
import type { ModelProvider } from "../types";

const PROVIDERS: ModelProvider[] = [
  {
    id: "google", name: "Google", short: "GAI", color: "#1A73E8",
    models: [{ id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", tagline: "x", cost: "$$", speed: "fast", ctx: "1M" }],
  },
  {
    id: "alibaba", name: "Alibaba", short: "QW", color: "#FF6A00",
    models: [{ id: "qwen-max", name: "Qwen Max", tagline: "x", cost: "$$", speed: "fast", ctx: "32k" }],
  },
];

describe("NodeModelDropdown provider icons", () => {
  it("renders an icon for a google-provider model and shows its name", () => {
    const html = renderToStaticMarkup(
      <NodeModelDropdown value="gemini-2.5-pro" providers={PROVIDERS} onChange={() => {}} />,
    );
    expect(html).toContain("node-dd__icon");
    expect(html).toContain("Gemini 2.5 Pro");
    expect(html).toContain("<svg");
  });

  it("renders an icon for an alibaba-provider model and shows its name", () => {
    const html = renderToStaticMarkup(
      <NodeModelDropdown value="qwen-max" providers={PROVIDERS} onChange={() => {}} />,
    );
    expect(html).toContain("node-dd__icon");
    expect(html).toContain("Qwen Max");
  });
});
