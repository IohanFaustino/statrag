// App composition + Tweaks
const { useState: useS, useEffect: useEf, useMemo: useMm } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#3FA9FF",
  "density": "comfortable",
  "userStyle": "bubble",
  "sidebarOpen": true,
  "contextOpen": true,
  "fontPair": "plex",
  "theme": "dark"
}/*EDITMODE-END*/;

const ACCENT_OPTIONS = [
  { value: "#3FA9FF", label: "Neon" },
  { value: "#3DDC97", label: "Sage" },
  { value: "#FFB36B", label: "Amber" },
  { value: "#B68BFF", label: "Lilac" },
  { value: "#001F3F", label: "Navy" },
];

const THEME_ACCENT_DEFAULTS = {
  dark:  "#3FA9FF",
  light: "#001F3F",
};

const FONT_PAIRS = {
  plex:   { serif: "'IBM Plex Serif'", sans: "'IBM Plex Sans'", mono: "'IBM Plex Mono'" },
  editorial: { serif: "'Newsreader'", sans: "'Inter Tight'", mono: "'JetBrains Mono'" },
  spectral:  { serif: "'Spectral'",   sans: "'Manrope'",     mono: "'IBM Plex Mono'" },
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [sidebarCollapsed, setSidebarCollapsed] = useS(!t.sidebarOpen);
  const [contextCollapsed, setContextCollapsed] = useS(!t.contextOpen);

  // Book filter — now multi-select state, not a single value
  const [books, setBooks] = useS(window.STATRAG_BOOKS);
  const toggleBook = (id) => setBooks(prev => prev.map(b => b.id === id ? { ...b, selected: !b.selected } : b));

  // Modals
  const [booksModalOpen, setBooksModalOpen] = useS(false);
  const [openSource, setOpenSource] = useS(null); // resolved source object

  // Temp chat
  const [tempChatOpen, setTempChatOpen] = useS(false);
  const [tempSeed, setTempSeed] = useS(null);

  // Model selection
  const [activeModel, setActiveModel] = useS(window.STATRAG_DEFAULT_MODEL);

  // sync collapsed states when tweaks change
  useEf(() => { setSidebarCollapsed(!t.sidebarOpen); }, [t.sidebarOpen]);
  useEf(() => { setContextCollapsed(!t.contextOpen); }, [t.contextOpen]);

  // apply theme/density/accent/fonts as CSS variables on root
  useEf(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", t.theme);
    root.setAttribute("data-density", t.density);
    root.style.setProperty("--accent-primary", t.accent);
    root.style.setProperty("--accent-primary-soft", t.accent + "26");
    root.style.setProperty("--accent-primary-ring", t.accent + "26");
    const pair = FONT_PAIRS[t.fontPair] || FONT_PAIRS.plex;
    root.style.setProperty("--font-serif", pair.serif + ", Georgia, serif");
    root.style.setProperty("--font-sans", pair.sans + ", system-ui, -apple-system, sans-serif");
    root.style.setProperty("--font-mono", pair.mono + ", ui-monospace, SFMono-Regular, monospace");
  }, [t.theme, t.density, t.accent, t.fontPair]);

  // Cmd+B opens book modal; Cmd+K opens mode picker (handled in input bar in future)
  useEf(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setBooksModalOpen(o => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Resolve a source chip → source object. Chips store "ch07 §7.4"; sources split chapter + section.
  const handleChipClick = (chip) => {
    const found = window.STATRAG_SOURCES.find(s =>
      s.book === chip.book && (
        chip.section === s.section ||
        chip.section === `${s.chapter} ${s.section}` ||
        chip.section.endsWith(s.section)
      )
    );
    if (found) setOpenSource(found);
  };

  // Active conversation title
  const activeConvTitle = "Ridge vs OLS in Hansen";

  return (
    <div className="app">
      <Topbar
        activeConvTitle={activeConvTitle}
        books={books}
        online={true}
        onToggleSidebar={() => setSidebarCollapsed(c => !c)}
        onOpenBooks={() => setBooksModalOpen(true)}
        onOpenSettings={() => {}}
        theme={t.theme}
        onToggleTheme={() => {
          const nextTheme = t.theme === "dark" ? "light" : "dark";
          setTweak({ theme: nextTheme, accent: THEME_ACCENT_DEFAULTS[nextTheme] });
        }}
      />
      <div className="app__body">
        <Sidebar
          collapsed={sidebarCollapsed}
          convs={window.STATRAG_CONVERSATIONS}
          roadmaps={window.STATRAG_ROADMAPS}
        />
        <main className={"main" + (tempChatOpen ? " main--split" : "")}>
          <section className="main__pane main__pane--primary">
            <MessageThread
              thread={window.STATRAG_THREAD}
              bubble={t.userStyle === "bubble"}
              onSourceClick={handleChipClick}
              onFork={(idx) => { setTempSeed(idx); setTempChatOpen(true); }}
              forkDisabled={tempChatOpen}
            />
            <InputBar
              activeMode="tutor"
              modes={window.STATRAG_MODES}
              onModeChange={() => {}}
              activeModel={activeModel}
              providers={window.STATRAG_PROVIDERS}
              onModelChange={setActiveModel}
            />
          </section>
          {tempChatOpen && (
            <section className="main__pane main__pane--temp">
              <TempChat
                onClose={() => { setTempChatOpen(false); setTempSeed(null); }}
                seedFromMsg={tempSeed}
              />
            </section>
          )}
        </main>
        <ContextPanel
          sources={window.STATRAG_SOURCES}
          figures={window.STATRAG_FIGURES}
          metadata={window.STATRAG_METADATA}
          collapsed={contextCollapsed}
          onToggle={() => setContextCollapsed(c => !c)}
          onSourceClick={(src) => setOpenSource(src)}
        />
      </div>

      <BookModal
        open={booksModalOpen}
        onClose={() => setBooksModalOpen(false)}
        books={books}
        onToggle={toggleBook}
      />
      <SourceModal
        open={!!openSource}
        onClose={() => setOpenSource(null)}
        source={openSource}
      />

      <TweaksPanel title="Tweaks">
        <TweakSection label="Theme" />
        <TweakRadio label="Mode" value={t.theme}
          options={["dark", "light"]}
          onChange={(v) => setTweak("theme", v)} />
        <TweakColor label="Accent" value={t.accent}
          options={ACCENT_OPTIONS.map(o => o.value)}
          onChange={(v) => setTweak("accent", v)} />

        <TweakSection label="Typography" />
        <TweakSelect label="Font pair" value={t.fontPair}
          options={[
            { value: "plex",       label: "IBM Plex (default)" },
            { value: "editorial",  label: "Newsreader / Inter Tight" },
            { value: "spectral",   label: "Spectral / Manrope" },
          ]}
          onChange={(v) => setTweak("fontPair", v)} />

        <TweakSection label="Layout" />
        <TweakRadio label="Density" value={t.density}
          options={["compact", "comfortable"]}
          onChange={(v) => setTweak("density", v)} />
        <TweakRadio label="User msg" value={t.userStyle}
          options={["bubble", "document"]}
          onChange={(v) => setTweak("userStyle", v)} />
        <TweakToggle label="Sidebar open" value={t.sidebarOpen}
          onChange={(v) => setTweak("sidebarOpen", v)} />
        <TweakToggle label="Sources panel" value={t.contextOpen}
          onChange={(v) => setTweak("contextOpen", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
