import { useEffect, useRef } from "react";
import katex from "katex";

// Strip trailing sentence punctuation that the LLM sometimes leaves inside
// math delimiters. KaTeX renders every char verbatim, so a stray ``.`` ``,``
// ``;`` ``:`` lands inside the boxed equation. Punctuation belongs AFTER the
// closing delimiter, never before. Whitespace before the punctuation is also
// trimmed so ``E = mc^2 .`` collapses to ``E = mc^2``.
export function stripTrailingMathPunct(tex: string): string {
  return tex.replace(/[\s]*[.,;:]+\s*$/u, "");
}

export function MathBlock({ tex }: { tex: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const clean = stripTrailingMathPunct(tex);
  useEffect(() => {
    if (!ref.current) return;
    try {
      katex.render(clean, ref.current, { displayMode: true, throwOnError: false, errorColor: "#888" });
    } catch {
      if (ref.current) ref.current.textContent = clean;
    }
  }, [clean]);
  return (
    <div className="math-block">
      <div ref={ref} aria-label={clean} />
    </div>
  );
}

export function MathInline({ tex }: { tex: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const clean = stripTrailingMathPunct(tex);
  useEffect(() => {
    if (!ref.current) return;
    try {
      katex.render(clean, ref.current, { displayMode: false, throwOnError: false, errorColor: "#888" });
    } catch {
      if (ref.current) ref.current.textContent = clean;
    }
  }, [clean]);
  return <span ref={ref} />;
}
