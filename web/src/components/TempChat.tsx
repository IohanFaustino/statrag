import { useEffect, useRef, useState } from "react";
import { IconSend } from "./Icons";

interface TempMessage {
  role: "user" | "assistant";
  text: string;
  time: string;
}

interface TempChatProps {
  onClose(): void;
  seedFromMsg?: number | null;
}

const SUGGESTIONS = [
  "Explain this in one paragraph",
  "What's the LASSO analogue?",
  "Give me a concrete example",
];

export default function TempChat({ onClose, seedFromMsg = null }: TempChatProps) {
  const [value, setValue] = useState("");
  const [messages, setMessages] = useState<TempMessage[]>([]);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-expand textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(160, Math.max(24, ta.scrollHeight)) + "px";
  }, [value]);

  function getTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function send(text?: string) {
    const v = (text ?? value).trim();
    if (!v) return;
    const userTime = getTime();
    setMessages((prev) => [
      ...prev,
      { role: "user", text: v, time: userTime },
      {
        role: "assistant",
        text: "Temporary chats don't query the corpus — they're for quick side threads. Wire me to the backend to make me answer.",
        time: getTime(),
      },
    ]);
    if (!text) setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const hasContent = value.trim().length > 0;

  return (
    <div className="temp-chat">
      <header className="temp-chat__hd">
        <div className="temp-chat__hd-left">
          <span className="temp-chat__badge">
            <svg
              viewBox="0 0 16 16"
              width="11"
              height="11"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <circle cx="8" cy="8" r="5" />
              <path d="M8 5v3l2 1" />
            </svg>
            TEMPORARY
          </span>
          <span className="temp-chat__title">Side thread</span>
          {seedFromMsg != null && (
            <span className="temp-chat__seed">forked from msg #{seedFromMsg + 1}</span>
          )}
        </div>
        <div className="temp-chat__hd-right">
          <span className="temp-chat__hint">won't be saved</span>
          <button
            className="temp-chat__close"
            type="button"
            onClick={onClose}
            aria-label="Close temporary chat"
          >
            <svg
              viewBox="0 0 16 16"
              width="12"
              height="12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </header>

      <div className="temp-chat__body">
        {messages.length === 0 ? (
          <div className="temp-chat__empty">
            <div className="temp-chat__empty-glyph" aria-hidden="true">
              ∿
            </div>
            <div className="temp-chat__empty-title">A side thread</div>
            <p className="temp-chat__empty-text">
              Ask a quick question without polluting your main conversation. Nothing here is saved, indexed, or carried forward.
            </p>
            <div className="temp-chat__empty-suggest">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="temp-chat__sugg"
                  type="button"
                  onClick={() => send(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="temp-chat__msgs">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="temp-msg temp-msg--user">
                  <div className="temp-msg__bubble">{m.text}</div>
                  <div className="temp-msg__meta">{m.time}</div>
                </div>
              ) : (
                <div key={i} className="temp-msg temp-msg--assistant">
                  <div className="temp-msg__meta">temp · {m.time}</div>
                  <p className="temp-msg__text">{m.text}</p>
                </div>
              ),
            )}
          </div>
        )}
      </div>

      <div className="temp-chat__input">
        <div className="temp-chat__field">
          <textarea
            ref={taRef}
            placeholder="Ask in this side thread…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            aria-label="Side thread message input"
          />
          <button
            className={"temp-chat__send" + (hasContent ? " is-active" : "")}
            type="button"
            onClick={() => send()}
            aria-label="Send"
            disabled={!hasContent}
          >
            <IconSend width={14} height={14} />
          </button>
        </div>
        <div className="temp-chat__footer">
          <span>
            <kbd>⏎</kbd> send
          </span>
          <span>·</span>
          <span>not saved to history</span>
        </div>
      </div>
    </div>
  );
}
