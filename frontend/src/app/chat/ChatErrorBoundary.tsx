"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ChatErrorBoundaryProps {
  children: ReactNode;
  debugSnapshot?: () => unknown;
}

interface ChatErrorBoundaryState {
  error: Error | null;
}

export class ChatErrorBoundary extends Component<
  ChatErrorBoundaryProps,
  ChatErrorBoundaryState
> {
  state: ChatErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ChatErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    let snapshot: unknown = undefined;
    try {
      snapshot = this.props.debugSnapshot?.();
    } catch {
      /* ignore snapshot errors */
    }

    let snapshotText = "";
    try {
      snapshotText = JSON.stringify(snapshot, null, 2);
    } catch {
      snapshotText = String(snapshot);
    }

    console.error(
      "[ChatErrorBoundary] caught render error\n" +
        `message: ${error.message}\n` +
        `name: ${error.name}\n` +
        `stack:\n${error.stack}\n` +
        `componentStack:\n${errorInfo.componentStack}\n` +
        `snapshot:\n${snapshotText}`,
      { error, errorInfo, snapshot },
    );
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-20 text-center">
          <p className="text-sm font-medium text-[color:var(--text)]">
            Chat rendering error
          </p>
          <p className="max-w-md text-xs text-[color:var(--text-quiet)]">
            {this.state.error.message}
          </p>
          <p className="max-w-md text-[10px] text-[color:var(--text-quiet)] opacity-60">
            Full diagnostic printed to browser console. Click &quot;Reset&quot;
            to continue.
          </p>
          <button
            onClick={this.reset}
            className="rounded-md border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-1.5 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
          >
            Reset
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
