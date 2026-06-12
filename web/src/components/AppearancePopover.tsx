import { useEffect, useRef } from "react";

/** Curated accent palette — picks that stay legible on both paper and ink. */
const ACCENT_PRESETS: { hex: string; name: string }[] = [
  { hex: "#C23A2B", name: "Brick" },
  { hex: "#E5484D", name: "Vermilion" },
  { hex: "#B0780E", name: "Amber" },
  { hex: "#1F7A52", name: "Forest" },
  { hex: "#0E7C7B", name: "Teal" },
  { hex: "#2D5D7C", name: "Steel" },
  { hex: "#3743C4", name: "Indigo" },
  { hex: "#6B4F8C", name: "Plum" },
];

interface Props {
  open: boolean;
  theme: "dark" | "light";
  /** Resolved current accent hex. */
  accent: string;
  /** Current per-theme card tint ("" = none). */
  card: string;
  onAccent(hex: string): void;
  onCard(hex: string): void;
  onResetAccent(): void;
  onResetCard(): void;
  onClose(): void;
}

/**
 * Appearance popover — Broadsheet color personalization.
 * Two swatch pickers (accent/Σ + answer tint) writing through the tweaks
 * engine, each with a "reset to theme default" link. Per-theme: edits the
 * currently active theme's slot.
 */
export default function AppearancePopover({
  open,
  theme,
  accent,
  card,
  onAccent,
  onCard,
  onResetAccent,
  onResetCard,
  onClose,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const sameHex = (a: string, b: string) =>
    a.trim().toLowerCase() === b.trim().toLowerCase();

  return (
    <>
      <div className="popover-scrim" onClick={onClose} />
      <div className="appr" role="dialog" aria-label="Appearance" ref={ref}>
        <div className="appr__hd">
          Appearance
          <span className="appr__theme">{theme}</span>
        </div>

        <div className="appr__row">
          <label className="appr__lbl" htmlFor="appr-accent">
            Accent &amp; Σ
          </label>
          <div className="appr__ctl">
            <input
              id="appr-accent"
              className="appr__swatch"
              type="color"
              value={accent}
              onChange={(e) => onAccent(e.target.value)}
              aria-label="Accent and sigma color"
            />
            <button type="button" className="appr__reset" onClick={onResetAccent}>
              reset
            </button>
          </div>
        </div>

        {/* Pre-defined accent palette — quick picks that read on both themes */}
        <div className="appr__presets" role="group" aria-label="Preset accent colors">
          {ACCENT_PRESETS.map((p) => (
            <button
              key={p.hex}
              type="button"
              className={
                "appr__preset" + (sameHex(accent, p.hex) ? " is-active" : "")
              }
              style={{ background: p.hex }}
              title={p.name}
              aria-label={p.name}
              aria-pressed={sameHex(accent, p.hex)}
              onClick={() => onAccent(p.hex)}
            />
          ))}
        </div>

        <div className="appr__row">
          <label className="appr__lbl" htmlFor="appr-card">
            Answer tint
          </label>
          <div className="appr__ctl">
            <input
              id="appr-card"
              className="appr__swatch"
              type="color"
              value={card || "#808080"}
              onChange={(e) => onCard(e.target.value)}
              aria-label="Answer card tint"
            />
            <button type="button" className="appr__reset" onClick={onResetCard}>
              {card ? "clear" : "none"}
            </button>
          </div>
        </div>

        <p className="appr__hint">
          Tints are clamped toward the page so wild picks stay readable.
        </p>

        <footer className="appr__ft">
          <button
            type="button"
            className="appr__reset-all"
            onClick={() => {
              onResetAccent();
              onResetCard();
            }}
          >
            Reset to defaults
          </button>
        </footer>
      </div>
    </>
  );
}
