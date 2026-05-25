import React, { useCallback } from "react";
import type { Roadmap, Scene } from "../../types";

interface Props {
  data: Roadmap;
}

function toYaml(value: unknown, indent = 0): string {
  const pad = "  ".repeat(indent);
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") {
    const safe = value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    return value.includes("\n") || value.includes(":") || value.includes("#")
      ? `"${safe}"`
      : safe || '""';
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return value
      .map((item) => `\n${pad}- ${toYaml(item, indent + 1).trimStart()}`)
      .join("");
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return Object.entries(obj)
      .map(([k, v]) => {
        const vStr = toYaml(v, indent + 1);
        const needsNewline =
          typeof v === "object" && v !== null && !Array.isArray(v)
            ? true
            : Array.isArray(v) && (v as unknown[]).length > 0;
        return `\n${pad}${k}:${needsNewline ? vStr : " " + vStr}`;
      })
      .join("");
  }
  return String(value);
}

function sceneToPlain(scene: Scene): Record<string, unknown> {
  return {
    id: scene.id,
    title: scene.title,
    concept: scene.concept,
    source: `${scene.source.book} / ${scene.source.section}`,
    suggested_visual: scene.suggested_visual,
    duration_hint: scene.duration_hint,
    ...(scene.figure ? { figure: scene.figure } : {}),
  };
}

export default function RoadmapView({ data }: Props) {
  const handleCopy = useCallback(() => {
    const plain = {
      topic: data.topic,
      duration_total_min: data.duration_total_min,
      scenes: data.scenes.map(sceneToPlain),
    };
    const yaml = `topic: ${toYaml(plain.topic)}\nduration_total_min: ${plain.duration_total_min}\nscenes:${toYaml(plain.scenes, 1)}`;
    navigator.clipboard.writeText(yaml).catch(() => undefined);
  }, [data]);

  return (
    <div className="roadmap-view">
      <div className="roadmap-view__topbar">
        <span className="roadmap-view__topic">{data.topic}</span>
        <span className="roadmap-view__dur">
          {data.duration_total_min > 0 ? `${data.duration_total_min} min` : ""}
        </span>
        <button
          type="button"
          className="roadmap-view__copy"
          onClick={handleCopy}
          aria-label="Copy roadmap as YAML"
        >
          Copy YAML
        </button>
      </div>

      <div className="roadmap-view__scenes">
        {data.scenes.map((scene) => (
          <div key={scene.id} className="scene-card">
            <div className="scene-card__num" aria-hidden="true">
              {String(scene.id).padStart(2, "0")}
            </div>
            <div className="scene-card__body">
              <div className="scene-card__title">{scene.title}</div>
              <div className="scene-card__concept">{scene.concept}</div>
              <div className="scene-card__meta">
                <span className="scene-card__src">
                  {scene.source.book} · {scene.source.section}
                  {scene.source.page != null ? ` · p.${scene.source.page}` : ""}
                </span>
                <span className="scene-card__sep">·</span>
                <span className="scene-card__dur">{scene.duration_hint}</span>
              </div>
              <div className="scene-card__visual">{scene.suggested_visual}</div>
              {scene.figure && (
                <div className="scene-card__fig">
                  <span className="dot dot--figure" aria-hidden="true" />
                  {scene.figure}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
