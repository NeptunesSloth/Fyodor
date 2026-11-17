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
