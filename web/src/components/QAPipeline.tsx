import { QA_PIPELINE } from "../data/qaPipeline";

/** Read-only Q&A pipeline diagram for the mode's (i) modal. */
export default function QAPipeline() {
  return (
    <div className="qa-pipeline">
      <ol className="qa-pipeline__nodes">
        {QA_PIPELINE.nodes.map((n) => (
          <li key={n.id} className={"qa-pipeline__node qa-pipeline__node--" + n.kind}>
            <div className="qa-pipeline__label">{n.label}</div>
            <div className="qa-pipeline__desc">{n.desc}</div>
            <div className="qa-pipeline__model">{n.defaultModel}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
