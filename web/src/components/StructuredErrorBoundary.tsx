import React from "react";

interface Props {
  children: React.ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Wraps a structured-answer render so a malformed or schema-drifted payload
 * degrades to an inline notice instead of unmounting the whole React tree.
 */
export default class StructuredErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.warn("[structured-render] failed to render answer", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="msg__render-error" role="alert">
          This answer can{"'"}t be displayed (unsupported format from an earlier
          version). The rest of the conversation is unaffected.
        </div>
      );
    }
    return this.props.children;
  }
}
