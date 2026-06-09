import { useEffect, useRef, useState, type ComponentType, type SVGProps } from "react";
import { IconBook, IconChevron } from "./Icons";
import type { ModeId } from "../types";

export interface ModeMeta {
  id: ModeId;
  label: string;
  glyph: string;
}

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

const MODE_ICON_MAP: Record<string, IconComponent> = {
  tutor: IconBook,
  qa: IconBook, // TODO(icon): swap to a target/zap glyph when added to Icons.tsx
  facilitate: IconBook,
  resume: IconBook,
  extension: IconBook,
};

interface ModePickerProps {
  activeMode: string;
  modes: ModeMeta[];
  onChange(id: string): void;
  // Opens the About-model modal (info icon lives on the Tutor card).
  onAbout?(): void;
  // Opens the Q&A info modal (info icon lives on the Q&A card).
  onAboutQA?(): void;
  // Opens the Facilitate info modal (info icon lives on the Facilitate card).
  onAboutFacilitate?(): void;
  // Opens the Resume info modal (info icon lives on the Resume card).
  onAboutResume?(): void;
  // Opens the Extension info modal (info icon lives on the Extension card).
  onAboutExtension?(): void;
}

export default function ModePicker({ activeMode, modes, onChange, onAbout, onAboutQA, onAboutFacilitate, onAboutResume, onAboutExtension }: ModePickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const cur = modes.find((m) => m.id === activeMode) ?? modes[0];
  const CurIcon = cur ? MODE_ICON_MAP[cur.id] : undefined;

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
    <div className="mode-picker" ref={containerRef}>
      <button
        className="tool-btn tool-btn--mode"
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="tool-btn__lbl">Mode:</span>
        <span className="tool-btn__val">
          {CurIcon && <CurIcon width={12} height={12} />}
          {cur?.label ?? "Tutor"}
        </span>
        <IconChevron width={12} height={12} />
      </button>

      {open && (
        <div
          className="mode-picker__panel"
          role="dialog"
          aria-label="Switch mode"
        >
          <div className="mode-picker__hd">
            Switch mode <kbd>⌘K</kbd>
          </div>
          <div className="mode-picker__grid">
            {modes.map((m) => {
              const Icon = MODE_ICON_MAP[m.id];
              const item = (
                <button
                  key={m.id}
                  className={"mode-picker__item" + (m.id === activeMode ? " is-active" : "")}
                  type="button"
                  onClick={() => {
                    onChange(m.id);
                    setOpen(false);
                    // Selecting Tutor also opens the About-model / pipeline modal.
                    if (m.id === "tutor" && onAbout) onAbout();
                  }}
                  aria-pressed={m.id === activeMode}
                >
                  {Icon && <Icon width={14} height={14} />}
                  <span>{m.label}</span>
                </button>
              );
              // The Tutor card carries an info (i) button → opens About-model modal.
              if (m.id === "tutor" && onAbout) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the tutor model & pipeline"
                      title="About the tutor model & pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAbout();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              // The Q&A card carries an info (i) button → opens Q&A mode modal.
              if (m.id === "qa" && onAboutQA) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Q&A pipeline"
                      title="About the Q&A pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutQA();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              // The Facilitate card carries an info (i) button → opens Facilitate modal.
              if (m.id === "facilitate" && onAboutFacilitate) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Facilitate pipeline"
                      title="About the Facilitate pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutFacilitate();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              // The Resume card carries an info (i) button → opens Resume modal.
              if (m.id === "resume" && onAboutResume) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Resume pipeline"
                      title="About the Resume pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutResume();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              // The Extension card carries an info (i) button → opens Extension modal.
              if (m.id === "extension" && onAboutExtension) {
                return (
                  <div key={m.id} className="mode-picker__cell">
                    {item}
                    <button
                      type="button"
                      className="mode-picker__about"
                      aria-label="About the Extension pipeline"
                      title="About the Extension pipeline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAboutExtension();
                        setOpen(false);
                      }}
                    >
                      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 7.2v4" strokeLinecap="round" />
                        <circle cx="8" cy="4.6" r="0.85" fill="currentColor" stroke="none" />
                      </svg>
                    </button>
                  </div>
                );
              }
              return item;
            })}
          </div>
        </div>
      )}
    </div>
  );
}
