import React from "react";

import type { ChatSettings } from "../state/chat";

interface Props {
  open: boolean;
  settings: ChatSettings;
  onChange: (next: ChatSettings) => void;
  onClose: () => void;
}

/**
 * T20 — slide-in drawer exposing the user-controllable chat knobs
 * forwarded to ChatRequest: temperature, top_k, rerank.
 *
 * `null` on each field means "defer to mode default". The reset button
 * clears all three to null in one action.
 */
export default function SettingsDrawer({
  open,
  settings,
  onChange,
  onClose,
}: Props) {
  return (
    <aside
      className={open ? "sdr sdr--open" : "sdr"}
      role="dialog"
      aria-label="Chat settings"
      aria-hidden={!open}
    >
      <header className="sdr__head">
        <h3 className="sdr__title">Chat settings</h3>
        <button
          className="sdr__close"
          type="button"
          onClick={onClose}
          aria-label="Close settings"
        >
          ×
        </button>
      </header>

      <section className="sdr__section">
        <label className="sdr__label" htmlFor="sdr-temp">
          Temperature
          <span className="sdr__val">
            {settings.temperature == null ? "auto" : settings.temperature.toFixed(1)}
          </span>
        </label>
        <input
          id="sdr-temp"
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={settings.temperature ?? 0.0}
          onChange={(e) =>
            onChange({ ...settings, temperature: parseFloat(e.target.value) })
          }
        />
        <p className="sdr__hint">
          0.0 = deterministic, 2.0 = wild. Lower for grounded tutoring; higher
          for brainstorming.
        </p>
      </section>

      <section className="sdr__section">
        <label className="sdr__label" htmlFor="sdr-topk">
          Retrieval top-k
          <span className="sdr__val">
            {settings.top_k == null ? "auto" : settings.top_k}
          </span>
        </label>
        <input
          id="sdr-topk"
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
              top_k: raw === "" ? null : Math.max(1, Math.min(20, parseInt(raw, 10) || 5)),
            });
          }}
        />
        <p className="sdr__hint">
          Suggests how many passages the `retrieve` tool should pull per call
          (1–20). The LLM may still override per-call.
        </p>
      </section>

      <section className="sdr__section">
        <label className="sdr__label sdr__label--row">
          <input
            type="checkbox"
            checked={settings.rerank ?? true}
            onChange={(e) => onChange({ ...settings, rerank: e.target.checked })}
          />
          Cross-encoder rerank
        </label>
        <p className="sdr__hint">
          Adds ~200 ms but lifts retrieval precision. Disable for raw RRF
          ordering.
        </p>
      </section>

      <footer className="sdr__foot">
        <button
          className="sdr__reset"
          type="button"
          onClick={() =>
            onChange({ temperature: null, top_k: null, rerank: null })
          }
        >
          Reset to mode defaults
        </button>
      </footer>
    </aside>
  );
}
