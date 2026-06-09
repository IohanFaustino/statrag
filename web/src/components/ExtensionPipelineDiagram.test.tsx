// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ExtensionPipelineDiagram from "./ExtensionPipelineDiagram";

describe("ExtensionPipelineDiagram", () => {
  it("renders the topology C stages", () => {
    render(<ExtensionPipelineDiagram />);
    for (const label of ["Resolve", "Fetch", "Analyst", "Polish", "Augmentor", "Judge"]) {
      const matches = screen.getAllByText(new RegExp(label, "i"));
      expect(matches.length).toBeGreaterThanOrEqual(1);
    }
  });
});
