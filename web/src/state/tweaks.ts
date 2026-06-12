import { useState, useEffect, useCallback } from "react";

export interface TweakState {
  theme: "dark" | "light";
  /** Resolved current accent (mirrors accentByTheme[theme]). */
  accent: string;
  /** Per-theme accent memory — toggling themes no longer clobbers a pick. */
  accentByTheme: { light: string; dark: string };
  /** Per-theme response-card tint ("" = no custom tint, use default surface). */
  cardByTheme: { light: string; dark: string };
  density: "compact" | "comfortable";
  userStyle: "bubble" | "document";
  fontPair: "plex" | "editorial" | "spectral";
  sidebarOpen: boolean;
  contextOpen: boolean;
}

const STORAGE_KEY = "statrag.tweaks";

const FONT_PAIRS: Record<TweakState["fontPair"], { serif: string; sans: string; mono: string }> = {
  plex: {
    serif: "'Crimson Pro'",
    sans:  "'Atkinson Hyperlegible'",
    mono:  "'JetBrains Mono'",
  },
  editorial: {
    serif: "'IBM Plex Serif'",
    sans:  "'Inter Tight'",
    mono:  "'JetBrains Mono'",
  },
  spectral: {
    serif: "'Crimson Pro'",
    sans:  "'Inter Tight'",
    mono:  "'JetBrains Mono'",
  },
};

// Broadsheet accent: brick on paper, vermilion on ink. These are the
// fallbacks used only when the user has never picked a color for that theme.
const THEME_ACCENT_DEFAULTS: Record<TweakState["theme"], string> = {
  dark:  "#E5484D",
  light: "#C23A2B",
};

/** Relative luminance of a #RRGGBB color (WCAG). */
function luminance(hex: string): number {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return 0.5;
  const n = parseInt(m[1], 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.2228 * ch[2];
}

/** Pick a readable foreground (ink or paper) for a solid fill of `hex`. */
function onColor(hex: string): string {
  return luminance(hex) > 0.5 ? "#1A1A1A" : "#FBF9F3";
}

function loadFromStorage(defaults: TweakState): TweakState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<TweakState> & { accent?: string };
    const next: TweakState = { ...defaults, ...parsed };
    // Migration: pre-feature stores held a single `accent` that the old theme
    // toggle auto-set to a theme default (not a deliberate pick). Ignore it and
    // fall back to the Broadsheet per-theme defaults.
    if (!parsed.accentByTheme) next.accentByTheme = { ...defaults.accentByTheme };
    if (!parsed.cardByTheme) next.cardByTheme = { ...defaults.cardByTheme };
    next.accent = next.accentByTheme[next.theme];
    return next;
  } catch {
    return defaults;
  }
}

function saveToStorage(state: TweakState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore quota errors in private browsing
  }
}

function applyToDOM(state: TweakState) {
  const root = document.documentElement;

  root.setAttribute("data-theme", state.theme);
  root.setAttribute("data-density", state.density);

  const accent = state.accentByTheme[state.theme] ?? THEME_ACCENT_DEFAULTS[state.theme];
  root.style.setProperty("--accent-primary", accent);
  // Append hex alpha: 1A = 10% (soft fill), 2E = 18% (focus ring).
  root.style.setProperty("--accent-primary-soft", accent + "1A");
  root.style.setProperty("--accent-primary-ring", accent + "2E");
  // Readable label color for anything that fills with the accent.
  root.style.setProperty("--on-accent", onColor(accent));

  // Response-card tint: clamp a picked color toward the theme surface so a
  // wild pick degrades to a tasteful wash by construction (never full-bleed).
  const card = state.cardByTheme[state.theme] ?? "";
  if (card) {
    root.style.setProperty(
      "--answer-surface",
      `color-mix(in srgb, ${card} 14%, var(--bg-secondary))`,
    );
  } else {
    root.style.removeProperty("--answer-surface");
  }

  const pair = FONT_PAIRS[state.fontPair] ?? FONT_PAIRS.plex;
  root.style.setProperty("--font-serif", pair.serif + ", Georgia, serif");
  root.style.setProperty("--font-sans",  pair.sans  + ", system-ui, -apple-system, sans-serif");
  root.style.setProperty("--font-mono",  pair.mono  + ", ui-monospace, SFMono-Regular, monospace");
}

/**
 * useTweaks — reads/writes localStorage key "statrag.tweaks".
 * Applies data-theme, data-density, and CSS vars to documentElement.
 * Returns [state, setTweak].
 *
 * setTweak accepts a partial object or (key, value). Special cases:
 *   - changing `theme` resolves `accent` from the per-theme memory
 *     (falling back to the Broadsheet default), so a toggle never wipes a pick.
 *   - setTweak("accent", hex) writes the current theme's slot in accentByTheme.
 *   - setTweak("card", hex|"") writes the current theme's card tint.
 */
export function useTweaks(defaults: TweakState) {
  const [state, setState] = useState<TweakState>(() => loadFromStorage(defaults));

  useEffect(() => {
    applyToDOM(state);
    saveToStorage(state);
  }, [state]);

  const setTweak = useCallback(
    (
      keyOrPartial: keyof TweakState | "accent" | "card" | Partial<TweakState>,
      value?: unknown,
    ) => {
      setState((prev) => {
        let next: TweakState;

        if (keyOrPartial === "accent") {
          const hex = String(value);
          next = {
            ...prev,
            accent: hex,
            accentByTheme: { ...prev.accentByTheme, [prev.theme]: hex },
          };
          return next;
        }
        if (keyOrPartial === "card") {
          const hex = String(value ?? "");
          return {
            ...prev,
            cardByTheme: { ...prev.cardByTheme, [prev.theme]: hex },
          };
        }

        if (typeof keyOrPartial === "string") {
          next = { ...prev, [keyOrPartial]: value } as TweakState;
        } else {
          next = { ...prev, ...keyOrPartial };
        }

        // Theme change → resolve accent from per-theme memory (no clobber).
        if (
          (typeof keyOrPartial === "object" && "theme" in keyOrPartial) ||
          keyOrPartial === "theme"
        ) {
          next.accent =
            next.accentByTheme[next.theme] ?? THEME_ACCENT_DEFAULTS[next.theme];
        }

        return next;
      });
    },
    [],
  );

  return [state, setTweak] as const;
}

export { THEME_ACCENT_DEFAULTS };
