// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MessageThread from "./MessageThread";
import type { Message } from "../types";

// Minimal assistant message in "pending" state (thinking indicator shows)
const pendingMsg: Message = {
  role: "assistant",
  id: "a1",
  time: "12:00",
  timestamp: "2026-06-04T12:00:00Z",
  mode: "tutor",
  model: "gpt-4",
  books: [],
  sourceCount: 0,
  latencyMs: 0,
  blocks: [],
  status: "pending",
};

describe("MessageThread — thinkingLabel prop", () => {
  it("renders custom thinkingLabel when provided", () => {
    render(
      <MessageThread
        thread={[pendingMsg]}
        thinkingLabel="Synthesizing across authors… (~45 s)"
        isStreaming={true}
        streamingPhase="thinking"
      />,
    );
    expect(
      screen.getByText("Synthesizing across authors… (~45 s)"),
    ).toBeInTheDocument();
  });

  it("renders default 'Thinking' label when thinkingLabel is omitted", () => {
    render(
      <MessageThread
        thread={[pendingMsg]}
        isStreaming={true}
        streamingPhase="thinking"
      />,
    );
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });
});
