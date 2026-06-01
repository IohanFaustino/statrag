#!/usr/bin/env python3
"""Generate the per-model doc pages + the shared sidebar nav.

Source of truth: src/services/chat/llm/router.py (_PROVIDERS), cost.py (PRICE_PER_1M),
router routing rules (get_llm). This script only emits STATIC html/js — it is a
maintenance convenience, not a runtime/build dependency. Re-run after the model
registry changes:

    cd "docs/common ground/Elements/models" && python3 _generate.py

Emits (relative to this dir):
  ../sidebar.js        shared left-sidebar nav (pages + models grouped by provider)
  index.html           model comparison table
  <safe-id>.html       one page per model (16)
"""
from __future__ import annotations
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Root pages, used by the sidebar (links are base-prefixed at runtime in JS).
PAGES = [
    ("index.html", "Overview"),
    ("ingestion.html", "Ingestion"),
    ("retrieval.html", "Retrieval"),
    ("chat.html", "Chat &amp; deep-tutor"),
    ("report.html", "Verification"),
]

# Verified from router.py:35-204 + cost.py:15-37 + get_llm router.py:253-261.
# fields: id, name, tagline, cost_tier, speed, ctx, in$, out$, client, route, draft, role
MODELS = [
    # --- OpenAI (client OpenAIChat — default fall-through, router.py:261) ---
    ("openai", "OpenAI", "#10A37F", [
        ("gpt-4o", "GPT-4o", "Multimodal flagship", "$$$", "fast", "128k", 2.50, 10.00,
         "OpenAIChat", "default (no prefix/membership match)", "native",
         "Vision-capable flagship; high-quality draft/synthesis when depth beats cost. Also the figure-judge vision model (gpt-4o-vision rate)."),
        ("gpt-4o-mini", "GPT-4o mini", "Cheap + fast", "$", "fast", "128k", 0.15, 0.60,
         "OpenAIChat", "default (no prefix/membership match)", "native",
         "Cheap sibling; economical expansion / image-judge / cheap draft."),
        ("gpt-5.4-nano-2026-03-17", "GPT-5.4 nano", "Project default — cheap nano", "$", "fast", "200k", 0.10, 0.40,
         "OpenAIChat", "default (no prefix/membership match)", "native",
         "Project default (config.py llm_model). Drives the auxiliary nano stages: concept/query planner, coverage check, image-judge, critique. Short structured tasks, not long synthesis."),
        ("gpt-5.4-2026-03-05", "GPT-5.4", "Full reasoning", "$$$$", "med", "400k", 5.00, 15.00,
         "OpenAIChat", "default (no prefix/membership match)", "native",
         "Full reasoning, highest cost + quality. Code-default draft model: _DRAFT_MODEL_DEFAULT = settings.openai_model_full (deep_tutor.py:787), used when no picker/.env override."),
    ]),
    # --- DeepSeek (client DeepSeekChat — id startswith 'deepseek', router.py:253) ---
    ("deepseek", "DeepSeek", "#4D6BFE", [
        ("deepseek-chat", "DeepSeek Chat", "General purpose", "$", "fast", "128k", 0.27, 1.10,
         "DeepSeekChat", "id startswith \"deepseek\"", "best-effort",
         "General-purpose, cheap. Tutor draft runs the best-effort JSON path (no native schema streaming)."),
        ("deepseek-reasoner", "DeepSeek Reasoner", "Chain-of-thought", "$$", "slow", "128k", 0.55, 2.20,
         "DeepSeekChat", "id startswith \"deepseek\"", "best-effort",
         "Explicit chain-of-thought; strong multi-step, slower. Best-effort JSON draft."),
        ("deepseek-v4-pro", "DeepSeek V4 Pro", "Latest pro tier", "$$", "med", "128k", 0.55, 2.20,
         "DeepSeekChat", "id startswith \"deepseek\"", "best-effort",
         "Draft-battle strong #2 / fallback (changelog 2026-05-31). Default organize-workflow model (TUTOR_ORGANIZE_MODEL). v4 ids default to THINKING mode → empty content; the chat path disables thinking (changelog 2026-05-31)."),
    ]),
    # --- Groq (client GroqChat — id in GROQ_MODEL_IDS, router.py:255) ---
    ("groq", "Groq", "#F55036", [
        ("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B", "Groq default — fast multimodal", "$", "fast", "128k", 0.11, 0.34,
         "GroqChat", "id ∈ GROQ_MODEL_IDS (explicit membership)", "native-json",
         "Groq default. OpenAI-compatible endpoint; passes response_format json_object/json_schema natively. Chat-only (ingestion never routes to Groq)."),
        ("llama-3.3-70b-versatile", "Llama 3.3 70B", "Versatile large", "$", "fast", "128k", 0.59, 0.79,
         "GroqChat", "id ∈ GROQ_MODEL_IDS (explicit membership)", "native-json",
         "Large versatile Llama. Native JSON verified live. Chat-only."),
        ("openai/gpt-oss-120b", "GPT-OSS 120B", "Open-weight flagship", "$$", "fast", "128k", 0.15, 0.75,
         "GroqChat", "id ∈ GROQ_MODEL_IDS (membership avoids the openai/ prefix collision)", "native-json",
         "Open-weight flagship hosted on Groq. The openai/ prefix collides with OpenAI ids — routed by explicit membership, not prefix. Chat-only."),
        ("openai/gpt-oss-20b", "GPT-OSS 20B", "Open-weight small", "$", "fast", "128k", 0.10, 0.50,
         "GroqChat", "id ∈ GROQ_MODEL_IDS (membership avoids the openai/ prefix collision)", "native-json",
         "Small open-weight. xfails strict JSON (reasoning-prefix tokens trip the validator) — the orchestrator repair loop is the safety net. Chat-only."),
    ]),
    # --- Google (client GeminiChat — id startswith 'gemini', router.py:257) ---
    ("google", "Google", "#4285F4", [
        ("gemini-2.5-flash", "Gemini 2.5 Flash", "Fast multimodal — draft candidate", "$", "fast", "1M", 0.15, 0.60,
         "GeminiChat", "id startswith \"gemini\"", "native-json",
         "1M-context fast multimodal via the OpenAI-compat endpoint. Entered the draft battle; not selected as the draft default."),
        ("gemini-2.5-pro", "Gemini 2.5 Pro", "Flagship reasoning", "$$$", "med", "1M", 1.25, 10.00,
         "GeminiChat", "id startswith \"gemini\"", "native-json",
         "1M-context flagship reasoning."),
    ]),
    # --- Alibaba Qwen (client QwenChat — id startswith 'qwen', router.py:259) ---
    ("alibaba", "Alibaba", "#615CED", [
        ("qwen-plus", "Qwen Plus", "Cheap 1M-ctx — prime draft candidate", "$", "fast", "1M", 0.40, 1.20,
         "QwenChat", "id startswith \"qwen\"", "native-json",
         "DRAFT-MODEL BATTLE WINNER (changelog 2026-05-31). Set as TUTOR_DRAFT_MODEL=qwen-plus in .env: cheapest survivor holding consistency + clean LaTeX + decomposition, ~7.7× cheaper than the gpt-5.4 incumbent (~$0.0055/answer). 1M context."),
        ("qwen-max", "Qwen Max", "Flagship reasoning", "$$$", "med", "32k", 1.60, 6.40,
         "QwenChat", "id startswith \"qwen\"", "native-json",
         "Flagship reasoning. Lost the draft battle: 32k cap + ~97s latency on the bias-variance draft. 32k context (smallest of the Qwen tier)."),
        ("qwen-turbo", "Qwen Turbo", "Fastest + cheapest", "$", "fast", "1M", 0.05, 0.20,
         "QwenChat", "id startswith \"qwen\"", "native-json",
         "Fastest + cheapest Qwen ($0.05/$0.20 per 1M). 1M context."),
    ]),
]

DRAFT_LABEL = {
    "native": "Native JSON-schema streaming",
    "best-effort": "Best-effort JSON path",
    "native-json": "Native JSON (OpenAI-compatible response_format)",
}


def safe(model_id: str) -> str:
    return model_id.replace("/", "-")


def page_shell(title: str, body: str) -> str:
    # base="../" because model pages live one level under Elements/.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>statrag — {title}</title>
<link rel="stylesheet" href="../style.css" />
</head>
<body data-base="../">
<aside id="side" class="side"></aside>
<div class="content">
{body}
</div>
<script src="../sidebar.js"></script>
</body>
</html>
"""


def model_page(provider_name: str, color: str, m: tuple) -> str:
    (mid, name, tagline, cost_tier, speed, ctx, pin, pout,
     client, route, draft, role) = m
    e = html.escape
    body = f"""<header>
  <h1><span class="accent">{e(name)}</span> <span class="pill" style="border-color:{color};color:{color}">{e(provider_name)}</span></h1>
  <div class="sub">{e(tagline)}</div>
</header>
<main>
  <section>
    <h2>Identity &amp; routing</h2>
    <table>
      <tr><th>Model id</th><td><code>{e(mid)}</code></td></tr>
      <tr><th>Provider</th><td>{e(provider_name)}</td></tr>
      <tr><th>Client</th><td><code>{e(client)}</code></td></tr>
      <tr><th>Routing rule</th><td>{route}</td></tr>
      <tr><th>Context window</th><td>{e(ctx)}</td></tr>
      <tr><th>Speed</th><td>{e(speed)}</td></tr>
      <tr><th>Cost tier</th><td>{e(cost_tier)}</td></tr>
    </table>
    <p class="caption">Registry: <code>src/services/chat/llm/router.py</code> · routing: <code>get_llm()</code> router.py:253-261.</p>
  </section>
  <section>
    <h2>Pricing <span class="pill">USD / 1M tokens</span></h2>
    <table>
      <tr><th>Input</th><th>Output</th></tr>
      <tr><td>${pin:.2f}</td><td>${pout:.2f}</td></tr>
    </table>
    <p class="caption">Source: <code>src/services/chat/cost.py</code> PRICE_PER_1M (conservative estimates).</p>
  </section>
  <section>
    <h2>Tutor draft path</h2>
    <div class="card"><p style="margin:0"><b>{e(DRAFT_LABEL.get(draft, draft))}.</b></p></div>
  </section>
  <section>
    <h2>Role in the pipeline</h2>
    <div class="card"><p style="margin:0">{e(role)}</p></div>
  </section>
</main>"""
    return page_shell(name, body)


def index_page() -> str:
    rows = []
    for _pid, pname, color, models in MODELS:
        for m in models:
            (mid, name, tagline, cost_tier, speed, ctx, pin, pout,
             client, route, draft, role) = m
            rows.append(
                f'<tr><td><a href="{safe(mid)}.html">{html.escape(name)}</a></td>'
                f'<td><span style="color:{color}">{html.escape(pname)}</span></td>'
                f'<td><code>{html.escape(mid)}</code></td>'
                f'<td>{html.escape(ctx)}</td><td>${pin:.2f}</td><td>${pout:.2f}</td>'
                f'<td>{html.escape(cost_tier)}</td></tr>'
            )
    table = "\n      ".join(rows)
    body = f"""<header>
  <h1>statrag — <span class="accent">Models</span></h1>
  <div class="sub">Every selectable LLM in the chat layer, from the backend registry. <span class="pill">16 models · 5 providers</span></div>
</header>
<main>
  <section>
    <h2>All models</h2>
    <table>
      <tr><th>Model</th><th>Provider</th><th>Id</th><th>Context</th><th>$ in /1M</th><th>$ out /1M</th><th>Cost tier</th></tr>
      {table}
    </table>
    <p class="caption">Source of truth: <code>src/services/chat/llm/router.py</code> (_PROVIDERS) + <code>cost.py</code>. Click a model for routing, pricing, and pipeline role.</p>
  </section>
  <section>
    <h2>Draft-model battle (2026-05-31)</h2>
    <div class="verdict v-ok"><b>Winner: qwen-plus</b> — set as <code>TUTOR_DRAFT_MODEL=qwen-plus</code> in <code>.env</code>; ~7.7× cheaper than gpt-5.4 while holding consistency + clean LaTeX. <code>deepseek-v4-pro</code> is the strong #2 / fallback; <code>gpt-5.4</code> (full) is the code-default fallback. See <code>docs/system/changelog.md</code> (2026-05-31).</div>
  </section>
</main>"""
    return page_shell("Models", body)


def sidebar_js() -> str:
    # Build the model groups literal for the shared sidebar.
    groups = []
    for _pid, pname, _color, models in MODELS:
        items = ", ".join(
            f'["models/{safe(m[0])}.html", {m[1]!r}]' for m in models
        )
        groups.append(f'  ["{pname}", [{items}]]')
    groups_js = ",\n".join(groups)
    return f"""// Shared left-sidebar nav for the statrag system docs.
// GENERATED by models/_generate.py — do not hand-edit; re-run the generator.
// Pages link relative to document.body.dataset.base ("" at root, "../" under models/).
(function () {{
  const PAGES = [
    ["index.html", "Overview"],
    ["ingestion.html", "Ingestion"],
    ["retrieval.html", "Retrieval"],
    ["chat.html", "Chat & deep-tutor"],
    ["report.html", "Verification"],
    ["models/index.html", "Models"]
  ];
  const MODEL_GROUPS = [
{groups_js}
  ];
  const base = document.body.dataset.base || "";
  // Current page path relative to Elements/ root, for active-highlighting.
  const path = location.pathname;
  const here = path.includes("/models/")
    ? "models/" + path.split("/").pop()
    : path.split("/").pop() || "index.html";

  function link(href, label) {{
    const active = (href === here) ? ' class="active"' : "";
    return `<a href="${{base}}${{href}}"${{active}}>${{label}}</a>`;
  }}

  let html = '<div class="side-brand">statrag</div>';
  html += '<div class="side-group">Pages</div>';
  html += PAGES.map(p => link(p[0], p[1])).join("");
  for (const [prov, models] of MODEL_GROUPS) {{
    html += `<div class="side-group">Models · ${{prov}}</div>`;
    html += models.map(m => link(m[0], m[1])).join("");
  }}
  const el = document.getElementById("side");
  if (el) el.innerHTML = html;
}})();
"""


def main() -> None:
    (HERE.parent / "sidebar.js").write_text(sidebar_js())
    (HERE / "index.html").write_text(index_page())
    n = 0
    for _pid, pname, color, models in MODELS:
        for m in models:
            (HERE / f"{safe(m[0])}.html").write_text(model_page(pname, color, m))
            n += 1
    print(f"wrote sidebar.js + models/index.html + {n} model pages")


if __name__ == "__main__":
    main()
