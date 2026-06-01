import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ModelProvider, ProviderId } from "../types";

// Provider icons — duplicated from ModelPicker (kept self-contained so this
// component owns no cross-file deps). Same SVG language as the chatbox picker.
function ProviderIcon({ id, size = 14 }: { id: ProviderId | string; size?: number }) {
  if (id === "openai") {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M22.28 10.06a5.83 5.83 0 0 0-.5-4.78 5.9 5.9 0 0 0-6.36-2.83A5.86 5.86 0 0 0 11.04 0a5.9 5.9 0 0 0-5.62 4.09 5.85 5.85 0 0 0-3.9 2.83A5.9 5.9 0 0 0 2.24 13.95a5.83 5.83 0 0 0 .5 4.78 5.9 5.9 0 0 0 6.36 2.83 5.85 5.85 0 0 0 4.4 1.98 5.9 5.9 0 0 0 5.62-4.1 5.85 5.85 0 0 0 3.9-2.82 5.9 5.9 0 0 0-.74-6.56ZM13.5 22.04a4.39 4.39 0 0 1-2.82-1.02l.14-.08 4.7-2.71a.76.76 0 0 0 .38-.66v-6.63l1.99 1.15a.07.07 0 0 1 .04.05v5.49a4.4 4.4 0 0 1-4.43 4.4Zm-9.46-4.04a4.37 4.37 0 0 1-.52-2.93l.14.08 4.7 2.72a.77.77 0 0 0 .76 0l5.74-3.31v2.29a.07.07 0 0 1-.03.06l-4.75 2.74a4.42 4.42 0 0 1-6.04-1.65Zm-1.23-10.2A4.39 4.39 0 0 1 5.1 5.85V11.43a.75.75 0 0 0 .38.66l5.74 3.3-1.99 1.15a.07.07 0 0 1-.06 0L4.42 13.8a4.42 4.42 0 0 1-1.61-6Zm16.32 3.8L13.4 8.27l1.99-1.14a.07.07 0 0 1 .06 0l4.75 2.74a4.4 4.4 0 0 1-.68 7.94v-5.59a.78.78 0 0 0-.4-.65Zm1.98-2.98-.14-.08-4.69-2.74a.76.76 0 0 0-.76 0L9.78 9.11V6.82a.07.07 0 0 1 .03-.06l4.75-2.74a4.4 4.4 0 0 1 6.55 4.56ZM8.7 13.16l-2-1.14a.07.07 0 0 1-.03-.06V6.5a4.4 4.4 0 0 1 7.22-3.39l-.15.08-4.7 2.72a.76.76 0 0 0-.37.65l-.01 6.6Zm1.08-2.34L12.34 9.34l2.56 1.48v2.96l-2.55 1.47-2.57-1.47Z" />
      </svg>
    );
  }
  if (id === "deepseek") {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
        <path d="M3 12c2.5 0 5-1.5 6.5-4.5C11 4.5 13.5 3 16.5 3c3 0 4.5 1.5 4.5 4.5 0 1.7-1 2.5-2.5 3 .5.3 1 1 1 2 0 1.7-1.5 3-3.5 3-3 0-5.5-1-7-2.5-1.5 2.7-3.7 5-7 5 0 0 1.5-2 1.5-4S3 12 3 12Zm12.5-5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z" />
      </svg>
    );
  }
  if (id === "groq") {
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
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="12" r="6" />
    </svg>
  );
}

interface LeadingOption {
  label: string;
  value: string;
}

interface NodeModelDropdownProps {
  value: string;
  providers: ModelProvider[];
  onChange(id: string): void;
  leadingOptions?: LeadingOption[];
}

export default function NodeModelDropdown({ value, providers, onChange, leadingOptions }: NodeModelDropdownProps) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{
    left: number;
    top: number | undefined;
    bottom: number | undefined;
    width: number;
    maxHeight: number;
  } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Resolve current provider + model name for the toggle.
  // Check leading options first so e.g. "off" shows "Off (single-draft)".
  let curProvider: ModelProvider | null = null;
  let curName = value;
  const matchedLeading = leadingOptions?.find((lo) => lo.value === value);
  if (matchedLeading) {
    curName = matchedLeading.label;
  } else {
    for (const p of providers) {
      const m = p.models.find((mm) => mm.id === value);
      if (m) { curProvider = p; curName = m.name; break; }
    }
  }

  // Anchor the floating panel under (or above) the button (position: fixed so
  // it is never clipped by the node box or the modal's scroll container).
  // Flip direction and clamp max-height to available viewport space so the
  // panel never overflows — especially for nodes low in the modal.
  useEffect(() => {
    if (!open) return;

    const PANEL_CAP = 320; // hard upper limit in px
    const MARGIN    = 8;   // breathing room from viewport edge

    const reposition = () => {
      if (!btnRef.current) return;
      // Use rAF so the read happens after any pending layout from the modal body scroll.
      requestAnimationFrame(() => {
        if (!btnRef.current) return;
        const r = btnRef.current.getBoundingClientRect();
        const vh = window.innerHeight;

        const spaceBelow = vh - r.bottom - MARGIN;
        const spaceAbove = r.top - MARGIN;

        if (spaceBelow >= 120 || spaceBelow >= spaceAbove) {
          // Open downward
          const maxHeight = Math.min(PANEL_CAP, Math.max(spaceBelow, 60));
          setRect({ left: r.left, top: r.bottom + 4, bottom: undefined, width: r.width, maxHeight });
        } else {
          // Flip: open upward — anchor bottom edge to button top
          const maxHeight = Math.min(PANEL_CAP, Math.max(spaceAbove, 60));
          setRect({ left: r.left, top: undefined, bottom: vh - r.top + 4, width: r.width, maxHeight });
        }
      });
    };

    reposition();
    // capture=true catches the modal body's nested scroll, not just window.
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open]);

  // Close on outside-click + Esc.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (
        btnRef.current && !btnRef.current.contains(t) &&
        panelRef.current && !panelRef.current.contains(t)
      ) setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="node-dd__toggle"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model: ${curName}. Click to change.`}
        onClick={() => setOpen((o) => !o)}
      >
        {curProvider && !matchedLeading && (
          <span className="node-dd__icon" aria-hidden="true">
            <ProviderIcon id={curProvider.id} size={13} />
          </span>
        )}
        <span className="node-dd__name">{curName}</span>
        <svg className="node-dd__chev" viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="m4 6 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && rect && createPortal(
        <div
          ref={panelRef}
          className="node-dd__panel"
          role="listbox"
          style={{
            position: "fixed",
            left: rect.left,
            ...(rect.top !== undefined ? { top: rect.top } : {}),
            ...(rect.bottom !== undefined ? { bottom: rect.bottom } : {}),
            minWidth: Math.max(rect.width, 200),
            maxHeight: rect.maxHeight,
            overflowY: "auto",
          }}
        >
          {leadingOptions && leadingOptions.length > 0 && (
            <div className="node-dd__group">
              <div className="node-dd__group-body">
                {leadingOptions.map((lo) => {
                  const active = lo.value === value;
                  return (
                    <button
                      key={lo.value}
                      type="button"
                      role="option"
                      aria-selected={active}
                      className={"node-dd__row" + (active ? " is-active" : "")}
                      onClick={() => { onChange(lo.value); setOpen(false); }}
                    >
                      <span className="node-dd__row-name">{lo.label}</span>
                      {active && (
                        <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="m3 8 4 4 6-8" />
                        </svg>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {providers.map((p) => (
            <div key={p.id} className="node-dd__group">
              <div className="node-dd__group-hd">
                <span className="node-dd__icon" aria-hidden="true">
                  <ProviderIcon id={p.id} size={13} />
                </span>
                {p.name}
              </div>
              <div className="node-dd__group-body">
              {p.models.map((m) => {
                const active = m.id === value;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={"node-dd__row" + (active ? " is-active" : "")}
                    onClick={() => { onChange(m.id); setOpen(false); }}
                  >
                    <span className="node-dd__row-name">{m.name}</span>
                    {active && (
                      <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="m3 8 4 4 6-8" />
                      </svg>
                    )}
                  </button>
                );
              })}
              </div>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
