# 22 — Frontend shell + tokens

## Purpose

Layout grid, design tokens, theme switching, glassmorphism surfaces, dark + light themes. Ports 1:1 from the design demo at `docs/upgrades/Demo/ChatSystem/`.

## Stack

- React 18 functional + hooks
- Vite 5 (dev server + build)
- TypeScript strict
- NO state library, NO router (v1)
- Plain CSS files (not modules) — preserves demo class names verbatim
- KaTeX 0.16 for math rendering

## File layout

```
web/
  package.json
  vite.config.ts                    # proxies /api → :8765
  tsconfig.json                     # noEmit: true
  index.html                        # data-theme="dark" data-density="comfortable"
  src/
    main.tsx                        # React mount + 3 CSS imports
    App.tsx                         # composition root
    types.ts                        # mirrors backend Pydantic 1:1
    state/
      tweaks.ts                     # localStorage-backed preferences hook
      chat.ts                       # useReducer over SSE ChatEvent stream
    api/
      client.ts                     # fetch helpers (books, models, conversations)
      sse.ts                        # POST-body SSE client (fetch + ReadableStream)
    styles/
      tokens.css                    # CSS custom properties (dark + light)
      app.css                       # component styles (kept demo class names)
      neon.css                      # glassmorphism overlay + financial-light theme
    components/
      Icons.tsx                     # inline SVGs (16x16, currentColor stroke)
      Topbar.tsx                    # menu, logo, breadcrumb, books btn, theme, gear, status
      Sidebar.tsx                   # New conv, grouped conversations, roadmaps, collapse
      ContextPanel.tsx              # Sources cards, Figures cards, retrieval metadata
      MessageThread.tsx             # User+Assistant messages, inline math/figures/chips
      InputBar.tsx                  # textarea + send + toolbar
      ModePicker.tsx                # popover w/ 11 modes
      ModelPicker.tsx               # popover grouped by provider
      TempChat.tsx                  # side-by-side temp pane (forked from msg)
      Math.tsx                      # KaTeX wrappers (MathBlock + MathInline)
      modals/
        FocusModal.tsx              # generic modal wrapper (esc/scroll-lock)
        BookModal.tsx               # KPI strip + chip toggles + book cards
        SourceModal.tsx             # full chunk w/ highlighted spans
      views/                        # mode-specific output renderers (M10)
        QuizView.tsx
        DAGView.tsx
        NavigationView.tsx
        ReportView.tsx
        StudyPathView.tsx
        RoadmapView.tsx
        AnnotateView.tsx
```

## Tokens (dark theme)

`web/src/styles/tokens.css`:

```css
:root[data-theme="dark"] {
  --bg-primary:    #050912;
  --bg-secondary:  rgba(15, 23, 38, 0.34);
  --bg-tertiary:   rgba(22, 32, 52, 0.34);
  --bg-elevated:   rgba(32, 44, 68, 0.58);
  --border-subtle:  rgba(120, 170, 255, 0.10);
  --border-default: rgba(120, 170, 255, 0.26);
  --text-primary:   #E6EEFB;
  --text-secondary: #8CA2C2;
  --text-tertiary:  #5C6E8B;
  --accent-primary:   #3FA9FF;
  --accent-secondary: #3DDC97;
  --accent-tertiary:  #FFB36B;
  --accent-danger:    #FF6B7E;
  --accent-neutral:   #B68BFF;
  --glow-accent: 0 0 16px rgba(63,169,255,0.45), 0 0 36px rgba(63,169,255,0.15);
  ...
}

:root[data-theme="light"] {
  --bg-primary:    #F2EEE5;    /* cream paper */
  --text-primary:  #001F3F;    /* deep navy */
  --accent-primary:   #001F3F;
  --accent-tertiary:  #B8860B; /* gold */
  ...
}
```

## Tweaks hook

`web/src/state/tweaks.ts`:

```ts
const KEY = "statrag.tweaks";

export function useTweaks(defaults: Tweaks) {
  const [t, setT] = useState<Tweaks>(() => {
    try { return { ...defaults, ...JSON.parse(localStorage.getItem(KEY) || "{}") } }
    catch { return defaults }
  });

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(t));
    const root = document.documentElement;
    root.setAttribute("data-theme", t.theme);
    root.setAttribute("data-density", t.density);
    root.style.setProperty("--accent-primary", t.accent);
    root.style.setProperty("--accent-primary-soft", t.accent + "26");
    const pair = FONT_PAIRS[t.fontPair] || FONT_PAIRS.plex;
    root.style.setProperty("--font-serif", pair.serif + ", Georgia, serif");
    root.style.setProperty("--font-sans", pair.sans + ", system-ui, sans-serif");
    root.style.setProperty("--font-mono", pair.mono + ", ui-monospace, monospace");
  }, [t]);

  return [t, (patch) => setT(prev => ({ ...prev, ...patch }))] as const;
}

export const THEME_ACCENT_DEFAULTS = {
  dark:  "#3FA9FF",
  light: "#001F3F",
};
```

Theme toggle swaps `theme` AND `accent` atomically so accent matches palette.

## Layout grid

`.app__body` = three columns: Sidebar (260px) · Main (fluid, max 720px thread) · ContextPanel (320px). Glassmorphism via `backdrop-filter: blur(22px) saturate(170%)` on the side panels; main `.thread` is fully transparent so the cosmic backdrop (`body::before` radial gradients) shows through.

## Responsive

```css
@media (max-width: 1280px) { .ctx-panel, .ctx-rail { display: none; } }
@media (max-width: 880px)  { .sidebar { display: none; } }
@media (max-width: 1120px) { .main--split { grid-template-columns: 1fr; ... } }
```

## Build cleanup (Phase 0 fix)

`tsconfig.json` has `"noEmit": true` and the build script is `tsc -b --noEmit && vite build` — prevents `.js` artifacts being emitted next to `.tsx` sources which would shadow them in Vite's module resolution (caused Phase 0's "stuck" bug).
