import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PlayerInitial } from "./PlayerInitial";

describe("a seat's portrait glyph (playtest nov 17: Bob and the bot both showed \"B\")", () => {
  it("a person shows their initial, a bot the robot glyph (labelled, not by colour alone)", () => {
    expect(renderToStaticMarkup(createElement(PlayerInitial, { p: { name: "bob", bot: null } }))).toBe("B");
    const bot = renderToStaticMarkup(createElement(PlayerInitial, { p: { name: "Bot", bot: "simple" } }));
    expect(bot).toContain("<svg");
    expect(bot).toContain('aria-label="Bot"');
    expect(renderToStaticMarkup(createElement(PlayerInitial, { name: "carol" }))).toBe("C");
  });
});
