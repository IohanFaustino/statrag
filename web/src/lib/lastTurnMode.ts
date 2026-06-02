import type { Message } from "../types";

// The mode to default the picker to when a conversation is opened: the mode of
// its most recent assistant turn, falling back to the conversation mode when the
// conversation has no assistant message yet.
export function lastTurnMode(messages: Message[], fallback: string): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && typeof m.mode === "string" && m.mode) {
      return m.mode;
    }
  }
  return fallback;
}
