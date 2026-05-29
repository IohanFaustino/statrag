// Pure markdown serializer for chat export. No React. The only DOM-touching
// function is downloadBlob (covered by browser-verify, not unit tests).
import type {
  Message, UserMessage, AssistantMessage, AssistantBlock,
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
