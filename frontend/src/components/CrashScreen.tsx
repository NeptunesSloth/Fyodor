import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * What a crash leaves on screen. Without this, one error while drawing (an old browser missing something, a graphics driver
 * refusing the 3D table) blanks the whole page to black. Instead it says what broke, in which browser, and offers a reload;
 * the details can be copied and sent along. Inline styles: it must not depend on anything that may have failed to load.
 */
export class CrashScreen extends Component<{ children: ReactNode; quiet?: ReactNode }, { error: Error | null; stack: string }> {
  state = { error: null as Error | null, stack: "" };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Fyodor crashed while drawing", error, info.componentStack);
    this.setState({ stack: (info.componentStack ?? "").trim().split("\n").slice(0, 6).join("\n") });
  }

  render() {
    const { error, stack } = this.state;
    if (!error) return this.props.children;
    if (this.props.quiet !== undefined) return this.props.quiet; // a part that may fail on its own (the 3D backdrop)
    const details = `${error.name}: ${error.message}\n${(error.stack ?? "").split("\n").slice(1, 6).join("\n")}\n${stack}\n\nBrowser: ${navigator.userAgent}`;
    return <CrashPanel details={details} />;
  }
}

export function CrashPanel({ details }: { details: string }) {
  const btn = { font: "600 14px system-ui, sans-serif", padding: "8px 16px", borderRadius: 6, border: "1px solid #8a6d36", cursor: "pointer" } as const;
  return (
    <div role="alert" style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center", background: "#14110d", color: "#eadfc8", font: "15px/1.5 system-ui, sans-serif", padding: 16, zIndex: 99999 }}>
      <div style={{ maxWidth: 680, width: "100%" }}>
        <h1 style={{ font: "600 24px Georgia, serif", color: "#e0bd73", margin: "0 0 8px" }}>Fyodor hit a problem drawing this page</h1>
        <p style={{ margin: "0 0 12px" }}>Your games are safe on the host. Reload to try again. If it keeps happening, update your browser (Edge or Chrome), or open Settings and switch the table to 2D. Send the details below to whoever looks after your Fyodor.</p>
        <pre data-testid="crash-details" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: "40vh", overflow: "auto", background: "#0b0907", border: "1px solid #3a2f20", borderRadius: 6, padding: 10, font: "12px/1.45 ui-monospace, Consolas, monospace", color: "#cbbf9f" }}>{details}</pre>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button style={{ ...btn, background: "#c9a45c", color: "#1a1408" }} onClick={() => location.reload()}>Reload</button>
          <button style={{ ...btn, background: "transparent", color: "#eadfc8" }} onClick={() => void navigator.clipboard?.writeText(details).catch(() => undefined)}>Copy details</button>
        </div>
      </div>
    </div>
  );
}
