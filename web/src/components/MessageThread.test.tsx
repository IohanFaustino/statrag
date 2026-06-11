// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MessageThread from "./MessageThread";
import type { Message, QAStoryAnswer } from "../types";

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

describe("MessageThread — QAStoryAnswer structured output routing", () => {
  const storyAnswer: QAStoryAnswer = {
    intro: "Bias and variance are foundational concepts.",
    deepening: "The tradeoff arises because reducing complexity increases bias.",
    conclusion: "Understanding this tradeoff guides model selection.",
    citations: [
      { kind: "corpus", label: "Hansen Ch3" },
      { kind: "wikipedia", label: "Bias-variance tradeoff", url: "https://en.wikipedia.org/wiki/Bias-variance_tradeoff" },
    ],
    math_blocks: [],
    grounding: { ok: true, confidence: 0.9 },
  };

  const msgWithStory: Message = {
    role: "assistant",
    id: "a2",
    time: "12:01",
    timestamp: "2026-06-04T12:01:00Z",
    mode: "qa",
    model: "gpt-5.4-nano-2026-03-17",
    books: ["hansen"],
    sourceCount: 2,
    latencyMs: 1000,
    blocks: [],
    status: "complete",
    structuredOutput: { schema: "QAStoryAnswer", data: storyAnswer },
  };

  it("routes QAStoryAnswer schema to QAAnswerCard and renders intro text", () => {
    render(<MessageThread thread={[msgWithStory]} isStreaming={false} streamingPhase="idle" />);
    expect(screen.getByText(/foundational concepts/)).toBeInTheDocument();
  });

  it("routes QAStoryAnswer schema and renders wiki chip link", () => {
    render(<MessageThread thread={[msgWithStory]} isStreaming={false} streamingPhase="idle" />);
    // wiki chip renders as a link
    const link = screen.getByRole("link", { name: /bias-variance tradeoff/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Bias-variance_tradeoff");
  });
});
