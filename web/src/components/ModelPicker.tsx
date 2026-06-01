import { useEffect, useRef, useState } from "react";
import { IconChevron } from "./Icons";
import type { ModelProvider, ProviderId } from "../types";

interface ModelPickerProps {
  activeModel: string;
  providers: ModelProvider[];
  onChange(id: string): void;
}

// ─── Provider icons (inline SVG) ──────────────────────────────────────────────
function ProviderIcon({ id, size = 16 }: { id: ProviderId | string; size?: number }) {
  if (id === "openai") {
    // OpenAI knot — simplified
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M22.28 10.06a5.83 5.83 0 0 0-.5-4.78 5.9 5.9 0 0 0-6.36-2.83A5.86 5.86 0 0 0 11.04 0a5.9 5.9 0 0 0-5.62 4.09 5.85 5.85 0 0 0-3.9 2.83A5.9 5.9 0 0 0 2.24 13.95a5.83 5.83 0 0 0 .5 4.78 5.9 5.9 0 0 0 6.36 2.83 5.85 5.85 0 0 0 4.4 1.98 5.9 5.9 0 0 0 5.62-4.1 5.85 5.85 0 0 0 3.9-2.82 5.9 5.9 0 0 0-.74-6.56ZM13.5 22.04a4.39 4.39 0 0 1-2.82-1.02l.14-.08 4.7-2.71a.76.76 0 0 0 .38-.66v-6.63l1.99 1.15a.07.07 0 0 1 .04.05v5.49a4.4 4.4 0 0 1-4.43 4.4Zm-9.46-4.04a4.37 4.37 0 0 1-.52-2.93l.14.08 4.7 2.72a.77.77 0 0 0 .76 0l5.74-3.31v2.29a.07.07 0 0 1-.03.06l-4.75 2.74a4.42 4.42 0 0 1-6.04-1.65Zm-1.23-10.2A4.39 4.39 0 0 1 5.1 5.85V11.43a.75.75 0 0 0 .38.66l5.74 3.3-1.99 1.15a.07.07 0 0 1-.06 0L4.42 13.8a4.42 4.42 0 0 1-1.61-6Zm16.32 3.8L13.4 8.27l1.99-1.14a.07.07 0 0 1 .06 0l4.75 2.74a4.4 4.4 0 0 1-.68 7.94v-5.59a.78.78 0 0 0-.4-.65Zm1.98-2.98-.14-.08-4.69-2.74a.76.76 0 0 0-.76 0L9.78 9.11V6.82a.07.07 0 0 1 .03-.06l4.75-2.74a4.4 4.4 0 0 1 6.55 4.56ZM8.7 13.16l-2-1.14a.07.07 0 0 1-.03-.06V6.5a4.4 4.4 0 0 1 7.22-3.39l-.15.08-4.7 2.72a.76.76 0 0 0-.37.65l-.01 6.6Zm1.08-2.34L12.34 9.34l2.56 1.48v2.96l-2.55 1.47-2.57-1.47Z" />
      </svg>
    );
  }
  if (id === "deepseek") {
    // DeepSeek whale — simplified abstract
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M3 12c2.5 0 5-1.5 6.5-4.5C11 4.5 13.5 3 16.5 3c3 0 4.5 1.5 4.5 4.5 0 1.7-1 2.5-2.5 3 .5.3 1 1 1 2 0 1.7-1.5 3-3.5 3-3 0-5.5-1-7-2.5-1.5 2.7-3.7 5-7 5 0 0 1.5-2 1.5-4S3 12 3 12Zm12.5-5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"/>
      </svg>
    );
  }
  if (id === "groq") {
    // Groq mark — rounded square with "G"
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
        <rect x="2" y="2" width="20" height="20" rx="5" fill="currentColor" />
        <text x="12" y="16.5" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff" fontFamily="system-ui, sans-serif">G</text>
      </svg>
    );
  }
  if (id === "google") {
    // Gemini — four-point spark (Google AI mark, simplified)
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M12 2c.4 4.6 3.4 7.6 8 8-4.6.4-7.6 3.4-8 8-.4-4.6-3.4-7.6-8-8 4.6-.4 7.6-3.4 8-8Z" />
      </svg>
    );
  }
  if (id === "alibaba") {
    // Qwen / Alibaba — twin-peak mark (simplified)
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M7 3 3.2 13.2a1 1 0 0 0 .94 1.35H7.5L9.3 9.7l2.7 7.1a1 1 0 0 0 1.87 0l2.7-7.1 1.8 4.85h3.36a1 1 0 0 0 .94-1.35L19.36 3h-2.6l2.74 9H17.1l-2.2-5.9a1 1 0 0 0-1.87 0L10.83 12H8.34l2.74-9H7Z" />
      </svg>
    );
  }
  // Fallback dot
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="12" r="6" />
    </svg>
  );
}

export default function ModelPicker({ activeModel, providers, onChange }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  let curProvider: ModelProvider | null = null;
  let curModelName = "Pick a model";
  for (const p of providers) {
    const m = p.models.find((mm) => mm.id === activeModel);
    if (m) {
      curProvider = p;
      curModelName = m.name;
      break;
    }
  }

  // Provider expansion state — defaults to active provider open
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (open && curProvider) {
      setExpanded((prev) => ({ ...prev, [curProvider!.id]: true }));
    }
  }, [open, curProvider?.id]);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Esc
  useEffect(() => {
    if (!open) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <div className="model-picker" ref={containerRef}>
      <button
        className="tool-btn tool-btn--model"
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="tool-btn__lbl">Model:</span>
        <span className="tool-btn__val">
          {curProvider && (
            <span className="mp-icon" style={{ color: curProvider.color }} aria-hidden="true">
              <ProviderIcon id={curProvider.id} size={14} />
            </span>
          )}
          {curModelName}
        </span>
        <IconChevron width={12} height={12} />
      </button>

      {open && (
        <div className="model-picker__panel" role="dialog" aria-label="Choose model">
          <div className="model-picker__hd">
            <span>MODEL</span>
            <span className="model-picker__hd-hint">click a provider to expand</span>
          </div>

          {providers.map((p) => {
            const isExpanded = !!expanded[p.id];
            return (
              <div key={p.id} className={"mp-group" + (isExpanded ? " is-open" : "")}>
                <button
                  className="mp-group__hd mp-group__toggle"
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [p.id]: !prev[p.id] }))
                  }
                >
                  <span className="mp-group__logo" style={{ color: p.color }} aria-hidden="true">
                    <ProviderIcon id={p.id} size={18} />
                  </span>
                  <span className="mp-group__name">{p.name}</span>
                  <span className="mp-group__count">
                    {p.models.length} model{p.models.length === 1 ? "" : "s"}
                  </span>
                  <span className={"mp-group__chev" + (isExpanded ? " is-open" : "")} aria-hidden="true">
                    <IconChevron width={12} height={12} />
                  </span>
                </button>

                {isExpanded && (
                  <div className="mp-group__list">
                    {p.models.map((m) => {
                      const isActive = m.id === activeModel;
                      return (
                        <button
                          key={m.id}
                          className={"mp-item" + (isActive ? " is-active" : "")}
                          type="button"
                          aria-pressed={isActive}
                          onClick={() => {
                            onChange(m.id);
                            setOpen(false);
                          }}
                        >
                          <div className="mp-item__l">
                            <div className="mp-item__name">
                              {m.name}
                              {m.recommended && <span className="mp-row__rec" title="System-recommended">★</span>}
                            </div>
                            <div className="mp-item__tag">{m.tagline}</div>
                          </div>
                          <div className="mp-item__r">
                            <span className="mp-item__ctx">{m.ctx}</span>
                            <span className="mp-item__cost" title="Cost tier">{m.cost}</span>
                            <span className={`mp-item__speed mp-item__speed--${m.speed}`}>
                              {m.speed}
                            </span>
                          </div>
                          {isActive && (
                            <span className="mp-item__check" aria-hidden="true">
                              <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                                <path d="m3 8 4 4 6-8" />
                              </svg>
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
