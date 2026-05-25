import { useCallback, useEffect, useRef, useState } from "react";

// Drop-in replacement for useState that mirrors to localStorage under `key`.
// Lazy-init reads localStorage once on mount; every subsequent set writes
// back synchronously. Falls back to `initial` on parse error or SSR.
//
// Use for cross-session config: tutor mode, model, per-stage overrides,
// drafting workflow, diversity knob, settings popover. Do NOT use for
// per-message ephemeral state (streaming, hover, modal open/close).
export function usePersistentState<T>(
  key: string,
  initial: T,
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return initial;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) return initial;
      return JSON.parse(raw) as T;
    } catch {
      return initial;
    }
  });

  // Guard against writing the initial value back before the first user change
  // would be wasteful but harmless; keep it simple and always mirror.
  const firstRun = useRef(true);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (firstRun.current) {
      firstRun.current = false;
      // Still write on first run so the key materialises with the resolved
      // default — makes manual inspection in DevTools predictable.
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Quota or privacy-mode failure — silently drop. Memory state still
      // works; persistence is best-effort.
    }
  }, [key, value]);

  // Stable setter identity for downstream useEffect deps.
  const setter = useCallback<React.Dispatch<React.SetStateAction<T>>>(
    (next) => setValue(next),
    [],
  );

  return [value, setter];
}
