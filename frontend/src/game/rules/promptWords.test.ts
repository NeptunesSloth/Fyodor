import { describe, expect, it } from "vitest";
import { prettyPrompt } from "./promptWords";

describe("a prompt's counts read as words (playtest nov 16)", () => {
  it("says 'a card' for one and the plural for more", () => {
    expect(prettyPrompt("Curiosity: Draw 1 card(s)?")).toBe("Curiosity: Draw a card?");
    expect(prettyPrompt("Draw 3 card(s)?")).toBe("Draw 3 cards?");
    expect(prettyPrompt("Put 1 +1/+1 counter(s) on it?")).toBe("Put 1 +1/+1 counter(s) on it?"); // (left alone: not a plain count)
    expect(prettyPrompt("Exile 1 item(s)")).toBe("Exile an item");
    expect(prettyPrompt("Pay {2}?")).toBe("Pay {2}?");
  });
});
