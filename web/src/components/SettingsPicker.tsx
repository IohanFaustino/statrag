import { useEffect, useRef, useState } from "react";

import type { ChatSettings } from "../state/chat";
import { IconChevron, IconWrench } from "./Icons";

interface Props {
  settings: ChatSettings;
  onChange(next: ChatSettings): void;
}

/**
 * T21 — chat-bar Settings picker. Same affordance as ModelPicker / ModePicker:
 * a tool-btn that opens a popover card with the three knobs
 * (temperature / top_k / rerank). Replaces the floating gear FAB.
 */
export default function SettingsPicker({ settings, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Click outside closes.
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Esc closes.
  useEffect(() => {
    if (!open) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const isCustom =
    settings.temperature != null ||
    settings.top_k != null ||
    settings.rerank != null;

  return (
    <div className="settings-picker" ref={containerRef}>
      <button
        className={
          "tool-btn tool-btn--config" + (isCustom ? " is-active" : "")
        }
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        title="Config"
      >
        <span className="tool-btn__icon" aria-hidden="true">
          <IconWrench width={14} height={14} />
        </span>
        <span className="tool-btn__lbl">Config</span>
        <IconChevron width={12} height={12} />
      </button>

      {open && (
        <div
          className="settings-picker__panel"
          role="dialog"
          aria-label="Config"
        >
          <div className="settings-picker__hd">
            <span>CONFIG</span>
            <button
              type="button"
              className="settings-picker__reset"
              onClick={() =>
                onChange({ temperature: null, top_k: null, rerank: null })
              }
            >
              reset
            </button>
          </div>

          <section className="sp-row">
            <label htmlFor="sp-temp" className="sp-row__lbl">
              Temperature
              <span className="sp-row__val">
                {settings.temperature == null
                  ? "auto"
                  : settings.temperature.toFixed(1)}
              </span>
            </label>
            <input
              id="sp-temp"
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={settings.temperature ?? 0.0}
              onChange={(e) =>
                onChange({
                  ...settings,
                  temperature: parseFloat(e.target.value),
                })
              }
            />
            <p className="sp-row__hint">
              0.0 deterministic · 2.0 wild. Lower for grounded tutoring.
            </p>
          </section>

          <section className="sp-row">
            <label htmlFor="sp-topk" className="sp-row__lbl">
              Retrieval top-k
              <span className="sp-row__val">
                {settings.top_k == null ? "auto" : settings.top_k}
              </span>
            </label>
            <input
              id="sp-topk"
              type="number"
              min={1}
              max={20}
              step={1}
              value={settings.top_k ?? ""}
              placeholder="auto"
              onChange={(e) => {
                const raw = e.target.value;
                onChange({
                  ...settings,
                  top_k:
                    raw === ""
                      ? null
                      : Math.max(1, Math.min(20, parseInt(raw, 10) || 5)),
                });
              }}
            />
            <p className="sp-row__hint">
              Passages per `retrieve` call (1–20). LLM may override.
            </p>
          </section>

          <section className="sp-row sp-row--inline">
            <label className="sp-row__lbl sp-row__lbl--inline">
              <input
                type="checkbox"
                checked={settings.rerank ?? true}
                onChange={(e) =>
                  onChange({ ...settings, rerank: e.target.checked })
                }
              />
              Cross-encoder rerank
            </label>
            <p className="sp-row__hint">
              +~200 ms · lifts retrieval precision.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

