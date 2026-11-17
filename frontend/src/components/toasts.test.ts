import { describe, expect, it } from "vitest";
import { toast, useToasts } from "./Toasts";

describe("toasts", () => {
  it("the same message again replaces the one on screen instead of stacking (second pass, nov 17)", () => {
    useToasts.setState({ toasts: [] });
    for (let i = 0; i < 5; i++) toast("Tap your mana first: {4} isn't paid yet");
    toast("Something else");
    expect(useToasts.getState().toasts.map((t) => t.text)).toEqual(["Tap your mana first: {4} isn't paid yet", "Something else"]);
  });
});
