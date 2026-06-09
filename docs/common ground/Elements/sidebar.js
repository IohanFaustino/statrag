// Shared left-sidebar nav for the statrag system docs.
// Hand-maintained. Two item kinds:
//   - flat links (pages with no subpages)
//   - toggle groups (an index page + child subpages) — collapsible
// Links are prefixed with document.body.dataset.base ("" at root, "../" under
// modes/ or models/). A toggle auto-expands when the current page is inside it.
(function () {
  const PAGES = [
    ["home.html", "Home"],
    ["index.html", "Overview"],
    ["report.html", "Verification"]
  ];

  // Toggle groups: {label, index:[href,label], children:[[href,label]...]}
  const TOGGLES = [
    {
      label: "Ingestion",
      index: ["ingestion/index.html", "All ingestion"],
      children: [
        ["ingestion/pipeline.html", "Pipeline"],
        ["ingestion/chunking.html", "Chunking & payload"],
        ["ingestion/preprocessors.html", "Preprocessors"]
      ]
    },
    {
      label: "Features",
      index: ["features/index.html", "All features"],
      children: [
        ["modes/tutor.html", "Tutor"],
        ["modes/qa.html", "Q&A"],
        ["modes/facilitate.html", "Facilitate"],
        ["modes/resume.html", "Resume"]
      ]
    },
    {
      label: "Services",
      index: ["services/index.html", "All services"],
      children: [
        ["services/core.html", "Core"],
        ["services/ingestion.html", "Ingestion (code)"],
        ["services/retrieval.html", "Retrieval"],
        ["services/chat.html", "Chat"],
        ["services/eval.html", "Eval"]
      ]
    },
    {
      label: "Models",
      index: ["models/index.html", "All models"],
      children: [
        ["models/gpt-4o.html", "GPT-4o"],
        ["models/gpt-4o-mini.html", "GPT-4o mini"],
        ["models/gpt-5.4-nano-2026-03-17.html", "GPT-5.4 nano"],
        ["models/gpt-5.4-2026-03-05.html", "GPT-5.4"],
        ["models/deepseek-chat.html", "DeepSeek Chat"],
        ["models/deepseek-reasoner.html", "DeepSeek Reasoner"],
        ["models/deepseek-v4-pro.html", "DeepSeek V4 Pro"],
        ["models/meta-llama-llama-4-scout-17b-16e-instruct.html", "Llama 4 Scout 17B"],
        ["models/llama-3.3-70b-versatile.html", "Llama 3.3 70B"],
        ["models/openai-gpt-oss-120b.html", "GPT-OSS 120B"],
        ["models/openai-gpt-oss-20b.html", "GPT-OSS 20B"],
        ["models/gemini-2.5-flash.html", "Gemini 2.5 Flash"],
        ["models/gemini-2.5-pro.html", "Gemini 2.5 Pro"],
        ["models/qwen-plus.html", "Qwen Plus"],
        ["models/qwen-max.html", "Qwen Max"],
        ["models/qwen-turbo.html", "Qwen Turbo"]
      ]
    }
  ];

  const base = document.body.dataset.base || "";
  const path = location.pathname;
  let here;
  const SUBDIRS = ["modes", "models", "ingestion", "features", "services"];
  const seg = SUBDIRS.find(d => path.includes("/" + d + "/"));
  if (seg) here = seg + "/" + path.split("/").pop();
  else here = path.split("/").pop() || "index.html";

  function link(href, label) {
    const active = href === here ? ' class="active"' : "";
    return `<a href="${base}${href}"${active}>${label}</a>`;
  }

  const side = document.getElementById("side");
  if (!side) return;

  let html = '<div class="side-brand">statrag</div>';
  html += '<div class="side-group">Pages</div>';
  html += PAGES.map(p => link(p[0], p[1])).join("");

  TOGGLES.forEach((g, i) => {
    const all = [g.index, ...g.children];
    const open = all.some(c => c[0] === here);
    const gid = "tg" + i;
    html += `<button class="side-toggle${open ? " open" : ""}" data-target="${gid}" aria-expanded="${open}">`
      + `<span class="caret">&#9656;</span>${g.label}</button>`;
    html += `<div class="side-sub" id="${gid}"${open ? "" : " hidden"}>`;
    html += link(g.index[0], g.index[1]);
    html += g.children.map(c => link(c[0], c[1])).join("");
    html += "</div>";
  });

  side.innerHTML = html;

  side.querySelectorAll(".side-toggle").forEach(btn => {
    btn.addEventListener("click", () => {
      const sub = document.getElementById(btn.dataset.target);
      const isOpen = !sub.hasAttribute("hidden");
      if (isOpen) { sub.setAttribute("hidden", ""); btn.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); }
      else { sub.removeAttribute("hidden"); btn.classList.add("open"); btn.setAttribute("aria-expanded", "true"); }
    });
  });
})();
