import { describe, expect, it, vi } from "vitest";
import { toast, useToasts } from "./Toasts";

describe("toasts", () => {
  it("the same message again replaces the one on screen instead of stacking (second pass, nov 17)", () => {
    useToasts.setState({ toasts: [] });
    for (let i = 0; i < 5; i++) toast("Tap your mana first: {4} isn't paid yet");
    toast("Something else");
    expect(useToasts.getState().toasts.map((t) => t.text)).toEqual(["Tap your mana first: {4} isn't paid yet", "Something else"]);
  });

  it("a sticky toast (a refused action) stays until dismissed; others time out (playtest B5)", () => {
    vi.useFakeTimers();
    try {
      useToasts.setState({ toasts: [] });
      toast("This would create 1,000 Warrior tokens …", "error", undefined, { sticky: true });
      toast("Passed", "info");
      vi.advanceTimersByTime(60_000);
      expect(useToasts.getState().toasts.map((t) => t.text)).toEqual(["This would create 1,000 Warrior tokens …"]);
      useToasts.getState().dismiss(useToasts.getState().toasts[0]!.id);
      expect(useToasts.getState().toasts).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("toast text with card symbols (playtest nov 17)", () => {
  it("a toast naming a cost or {T} draws the symbols; plain text stays plain", async () => {
    const { createElement } = await import("react");
    const { renderToStaticMarkup } = await import("react-dom/server");
    const { ToastText } = await import("./Toasts");
    const html = (text: string) => renderToStaticMarkup(createElement(ToastText, { text }));
    const coffers = html("Add {2} to your mana pool first to activate Cabal Coffers. Nothing changed.");
    expect(coffers).not.toContain("{2}");
    expect(coffers).toContain('aria-label="2 generic mana"');
    expect(coffers).toContain("to your mana pool first to activate Cabal Coffers");
    const tap = html("Double-click a land to use its {T} ability");
    expect(tap).not.toContain("{T}");
    expect(tap).toContain('aria-label="Tap"');
    expect(html("Passed")).toBe('<span class="toast-text">Passed</span>');
  });
});
