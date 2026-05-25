import { useState, useEffect, useCallback } from "react";

export interface TweakState {
  theme: "dark" | "light";
  accent: string;
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

const THEME_ACCENT_DEFAULTS: Record<TweakState["theme"], string> = {
  dark:  "#E5484D",
  light: "#1E3A8A",
};

function loadFromStorage(defaults: TweakState): TweakState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) };
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

  root.style.setProperty("--accent-primary", state.accent);
  // Append "26" hex = 15% alpha for soft/ring variants
  root.style.setProperty("--accent-primary-soft", state.accent + "26");
  root.style.setProperty("--accent-primary-ring", state.accent + "26");

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
 * setTweak can be called with a partial object for partial updates,
 * or as setTweak("key", value) for a single field.
 */
export function useTweaks(defaults: TweakState) {
  const [state, setState] = useState<TweakState>(() => loadFromStorage(defaults));

  // Apply to DOM whenever state changes
  useEffect(() => {
    applyToDOM(state);
    saveToStorage(state);
  }, [state]);

  // Overloaded setter: either partial object or (key, value)
  const setTweak = useCallback(
    (
      keyOrPartial: keyof TweakState | Partial<TweakState>,
      value?: TweakState[keyof TweakState],
    ) => {
      setState((prev) => {
        let next: TweakState;
        if (typeof keyOrPartial === "string") {
          next = { ...prev, [keyOrPartial]: value };
        } else {
          next = { ...prev, ...keyOrPartial };
        }

        // Theme toggle: atomically swap accent to theme default
        if (
          typeof keyOrPartial === "object" &&
          "theme" in keyOrPartial &&
          !("accent" in keyOrPartial)
        ) {
          const newTheme = keyOrPartial.theme as TweakState["theme"];
          next.accent = THEME_ACCENT_DEFAULTS[newTheme];
        }

        return next;
      });
    },
    [],
  );

  return [state, setTweak] as const;
}

export { THEME_ACCENT_DEFAULTS };
