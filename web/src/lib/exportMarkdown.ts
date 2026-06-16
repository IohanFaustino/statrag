// Pure markdown serializer for chat export. No React. The only DOM-touching
// function is downloadBlob (covered by browser-verify, not unit tests).
import type {
  Message, UserMessage, AssistantMessage, AssistantBlock,
  TutorAnswer, TutorCitation, QAAnswer, QAStoryAnswer, StoryCitation, ChapterDigest, FacilitateStory,
} from "../types";
import { structuredToMarkdown } from "./exportStructured";

const MODE_LABEL: Record<string, string> = {
  tutor: "TUTOR", compare: "COMPARE", figures: "FIGURES", quiz: "QUIZ",
  navigate: "NAVIGATE", prereqs: "PREREQS", annotate: "ANNOTATE",
  research: "RESEARCH", math: "MATH", path: "PATH", roadmap: "ROADMAP",
};

export function slugify(s: string): string {
  const cleaned = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
  return cleaned || "conversation";
}

function blockToMarkdown(block: AssistantBlock): string {
  switch (block.type) {
    case "p":
      return block.text.trim() ? block.text.trim() : "";
    case "math":
      return "$$\n" + block.tex.trim() + "\n$$";
    case "figure": {
      const tag = `**${block.ref}** — ${block.caption} (${block.book} · ${block.chapter})`;
      const isUrl = block.chart && (block.chart.startsWith("/") || block.chart.startsWith("http"));
      const img = isUrl ? `\n> \n> ![${block.caption}](${block.chart})` : "";
      return `> ${tag}${img}`;
    }
    case "sources": {
      const chips = block.chips.map((c) => `\`${c.book} · ${c.section}\``).join(" ");
      return `**Sources:** ${chips}`;
    }
    default:
      return "";
  }
}

export function assistantMessageToMarkdown(msg: AssistantMessage): string {
  if (msg.status !== "complete") {
    return "> _(answer incomplete — not exported)_";
  }
  if (msg.structuredOutput) {
    const structured = structuredToMarkdown(msg.structuredOutput);
    if (structured) return structured;
  }
  const parts = msg.blocks.map(blockToMarkdown).filter((s) => s.length > 0);
  return parts.join("\n\n");
}

export function userMessageToMarkdown(msg: UserMessage): string {
  return `## You · ${msg.time}\n\n${msg.text.trim()}`;
}

export function conversationToMarkdown(
  messages: Message[],
  meta: { title: string; date?: string },
): string {
  const date = meta.date ?? new Date().toISOString().slice(0, 10);
  const head = `# ${meta.title}\n\n> Exported from statrag · ${date}`;
  const turns: string[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      turns.push(userMessageToMarkdown(m));
    } else {
      // In-flight/errored turns are dropped from full exports (single-answer path notes them instead).
      if (m.status !== "complete") continue;
      const label = MODE_LABEL[m.mode] ?? m.mode.toUpperCase();
      const heading = `## ${label} · ${m.model || "?"} · ${m.time}`;
      turns.push(`${heading}\n\n${assistantMessageToMarkdown(m)}`);
    }
  }
  return [head, ...turns].join("\n\n---\n\n") + "\n";
}

export function downloadBlob(filename: string, blob: Blob): void {
  try {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    // Best-effort, mirrors persist.ts: never throw from a UI handler.
    // eslint-disable-next-line no-console
    console.warn("[exportMarkdown] download failed", err);
  }
}

// ─── Single-answer markdown exporters (used by download buttons) ───────────

function formatTutorCitation(c: TutorCitation): string {
  const parts: string[] = [];
  if (c.authors_short) parts.push(c.authors_short);
  if (c.year) parts.push(String(c.year));
  if (c.book_name) parts.push(c.book_name);
  if (c.chapter) parts.push(c.chapter);
  if (c.section) parts.push(c.section);
  if (c.page_from) {
    const pageStr = c.page_to && c.page_to !== c.page_from
      ? `pp. ${c.page_from}–${c.page_to}`
      : `p. ${c.page_from}`;
    parts.push(pageStr);
  }
  return parts.join(" · ");
}

/**
 * Export TutorAnswer to markdown (used by download button).
 */
export function tutorToMarkdown(data: TutorAnswer): string {
  const lines: string[] = [];
  lines.push("# Tutor Answer");
  lines.push("");
  lines.push(data.text);
  lines.push("");

  if (data.math_blocks?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## Math");
    lines.push("");
    for (const tex of data.math_blocks) {
      lines.push("$$");
      lines.push(tex);
      lines.push("$$");
      lines.push("");
    }
  }

  if (data.citations?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## References");
    lines.push("");
    for (const c of data.citations) {
      lines.push(`[${c.index}] ${formatTutorCitation(c)}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

function formatStoryCitation(c: StoryCitation): string {
  const parts: string[] = [];
  if (c.book_name) parts.push(c.book_name);
  if (c.authors) parts.push(c.authors);
  if (c.year) parts.push(String(c.year));
  if (c.chapter) parts.push(c.chapter);
  if (c.pages) parts.push(`pp. ${c.pages}`);
  if (c.url) parts.push(c.url);
  return parts.join(" · ");
}

/**
 * Export QAStoryAnswer to markdown (used by download button).
 */
export function qaStoryToMarkdown(data: QAStoryAnswer): string {
  const lines: string[] = [];
  lines.push("# Q&A Answer");
  lines.push("");
  if (data.scope?.target_gap) {
    lines.push(`**Question:** ${data.scope.target_gap}`);
    lines.push("");
  }
  lines.push(data.intro);
  lines.push("");
  lines.push(data.deepening);
  lines.push("");
  lines.push(data.conclusion);
  lines.push("");

  if (data.math_blocks?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## Math");
    lines.push("");
    for (const tex of data.math_blocks) {
      lines.push("$$");
      lines.push(tex);
      lines.push("$$");
      lines.push("");
    }
  }

  if (data.citations?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## References");
    lines.push("");
    for (let i = 0; i < data.citations.length; i++) {
      const prefix = data.citations[i].kind === "wikipedia" ? "🌐 " : "";
      lines.push(`${prefix}[${i + 1}] ${formatStoryCitation(data.citations[i])}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * Export legacy QAAnswer to markdown (used by download button).
 */
export function qaToMarkdown(data: QAAnswer): string {
  const lines: string[] = [];
  lines.push("# Q&A Answer");
  lines.push("");
  if (data.scope?.target_gap) {
    lines.push(`**Question:** ${data.scope.target_gap}`);
    lines.push("");
  }

  const body = data.text?.trim()
    || [data.thesis, data.deepening, data.synthesis]
        .filter((s): s is string => !!s)
        .join("\n\n");
  if (body) {
    lines.push(body);
    lines.push("");
  }

  if (data.math_blocks?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## Math");
    lines.push("");
    for (const tex of data.math_blocks) {
      lines.push("$$");
      lines.push(tex);
      lines.push("$$");
      lines.push("");
    }
  }

  if (data.citations?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## References");
    lines.push("");
    for (const c of data.citations) {
      lines.push(`[${c.index}] ${formatTutorCitation(c)}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * Export ChapterDigest to markdown (used by download button).
 */
export function chapterDigestToMarkdown(data: ChapterDigest): string {
  const lines: string[] = [];
  const title = data.mode === "facilitate" ? "Facilitate Digest" : "Resume Digest";
  lines.push(`# ${title}`);
  lines.push("");
  lines.push(`**Book:** ${data.scope.book_slug}`);
  lines.push(`**Chapter:** ${data.scope.chapter_id}`);
  lines.push("");

  if (data.intro) {
    lines.push(data.intro);
    lines.push("");
  }

  for (const block of data.blocks) {
    lines.push(`## ${block.h2_path}`);
    lines.push("");
    if (block.page_from > 0) {
      const pageStr = block.page_to > block.page_from
        ? `pp. ${block.page_from}–${block.page_to}`
        : `p. ${block.page_from}`;
      lines.push(`*${pageStr}*`);
      lines.push("");
    }
    lines.push(block.body);
    lines.push("");
  }

  if (data.math_blocks?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## Math");
    lines.push("");
    for (const tex of data.math_blocks) {
      lines.push("$$");
      lines.push(tex);
      lines.push("$$");
      lines.push("");
    }
  }

  if (data.outro) {
    lines.push(data.outro);
    lines.push("");
  }

  if (data.citations?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## References");
    lines.push("");
    for (const c of data.citations) {
      lines.push(`[${c.index}] ${formatTutorCitation(c)}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/**
 * Export FacilitateStory to markdown (used by download button).
 */
export function facilitateStoryToMarkdown(data: FacilitateStory): string {
  const lines: string[] = [];
  lines.push("# Facilitate Story");
  lines.push("");
  lines.push(`**Section:** ${data.scope.requested_subtopics.join(", ")}`);
  lines.push("");

  if (data.hook) {
    lines.push(data.hook);
    lines.push("");
  }

  for (const m of data.movements) {
    if (m.formal) {
      lines.push(`## ${m.formal.kind.toUpperCase()}`);
      lines.push("");
      lines.push("> " + m.formal.statement.split("\n").join("\n> "));
      lines.push("");
      lines.push(m.formal.explanation);
      lines.push("");
    } else if (m.prose) {
      lines.push(m.prose);
      lines.push("");
    }
  }

  if (data.takeaway) {
    lines.push("---");
    lines.push("");
    lines.push(data.takeaway);
    lines.push("");
  }

  if (data.citations?.length) {
    lines.push("---");
    lines.push("");
    lines.push("## References");
    lines.push("");
    for (let i = 0; i < data.citations.length; i++) {
      const prefix = data.citations[i].kind === "wikipedia" ? "🌐 " : "";
      lines.push(`${prefix}[${i + 1}] ${formatStoryCitation(data.citations[i])}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}
