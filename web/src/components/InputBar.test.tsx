// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import InputBar from "./InputBar";

const baseProps = {
  modes: [{ id: "tutor" as const, label: "Tutor", glyph: "T" }],
  onModeChange: () => {},
  onSend: vi.fn(),
};

describe("InputBar stop button", () => {
  it("shows a Stop button while streaming and calls onStop", () => {
    const onStop = vi.fn();
    render(<InputBar {...baseProps} activeMode="tutor" isStreaming onStop={onStop} />);
    fireEvent.click(screen.getByRole("button", { name: /stop/i }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("shows Send when not streaming", () => {
    render(<InputBar {...baseProps} activeMode="tutor" isStreaming={false} onStop={() => {}} />);
    expect(screen.getByRole("button", { name: /send message/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
  });
});
