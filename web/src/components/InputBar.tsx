import { useEffect, useRef, useState } from "react";
import { IconSend } from "./Icons";
import ModePicker from "./ModePicker";
import type { ModeMeta } from "./ModePicker";

interface InputBarProps {
  activeMode: string;
  modes: ModeMeta[];
  onModeChange(id: string): void;
  onModeAbout?(): void;
  onModeAboutQA?(): void;
  onModeAboutFacilitate?(): void;
  onModeAboutResume?(): void;
  onModeAboutExtension?(): void;
  onSend(text: string): void;
  /** Disables the textarea + Send button. Does NOT affect the Stop button,
   *  which is always clickable while streaming. */
  disabled?: boolean;
  isStreaming?: boolean;
  onStop?(): void;
}

export default function InputBar({
  activeMode,
  modes,
  onModeChange,
  onModeAbout,
  onModeAboutQA,
  onModeAboutFacilitate,
  onModeAboutResume,
  onModeAboutExtension,
  onSend,
  disabled = false,
  isStreaming = false,
  onStop,
}: InputBarProps) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-expand textarea: 1 line min, grow up to 10 lines then scroll
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const cs = getComputedStyle(ta);
    const lineH = parseFloat(cs.lineHeight) || 22;
    const padY  = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const maxH  = Math.round(lineH * 10 + padY);
    const minH  = Math.round(lineH);
    ta.style.height = "auto";
    const next = Math.min(maxH, Math.max(minH, ta.scrollHeight));
    ta.style.height = next + "px";
    ta.style.overflowY = ta.scrollHeight > maxH ? "auto" : "hidden";
  }, [value]);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled || isStreaming) return;
    onSend(trimmed);
    setValue("");
    // Reset textarea height
    if (taRef.current) {
      taRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const hasContent = value.trim().length > 0;

  return (
    <div className="input-bar">
      <div className="input-bar__inner">
        <div className="input-bar__field">
          <textarea
            ref={taRef}
            className="input-bar__ta"
            placeholder="Ask anything about statistics…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={disabled}
            aria-label="Message input"
            aria-multiline="true"
          />
          {isStreaming ? (
            <button
              className="input-bar__send input-bar__stop is-active"
              type="button"
              aria-label="Stop generating"
              onClick={() => onStop?.()}
            >
              <span className="input-bar__stop-square" aria-hidden="true" />
            </button>
          ) : (
            <button
              className={"input-bar__send" + (hasContent && !disabled ? " is-active" : "")}
              type="button"
              aria-label="Send message"
              disabled={!hasContent || disabled}
              onClick={handleSend}
            >
              <IconSend width={16} height={16} />
            </button>
          )}
        </div>

        <div className="input-bar__toolbar">
          <ModePicker
            activeMode={activeMode}
            modes={modes}
            onChange={onModeChange}
            onAbout={onModeAbout}
            onAboutQA={onModeAboutQA}
            onAboutFacilitate={onModeAboutFacilitate}
            onAboutResume={onModeAboutResume}
            onAboutExtension={onModeAboutExtension}
          />
        </div>
      </div>
    </div>
  );
}
