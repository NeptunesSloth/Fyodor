import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { ColorPips } from "../components/ColorPips";
import { ManaText, OracleText } from "./ManaText";
import { setSymbols } from "./symbols";

const HOST = {
  T: { svg: "T", english: "tap this permanent" },
  C: { svg: "C", english: "one colorless mana" },
  W: { svg: "W", english: "one white mana" },
  U: { svg: "U", english: "one blue mana" },
  "2/W": { svg: "2W", english: "two generic mana or one white mana" },
};
const text = (t: string) => renderToStaticMarkup(createElement(ManaText, { text: t }));
const pips = (colors: string[]) => renderToStaticMarkup(createElement(ColorPips, { colors }));

afterEach(() => setSymbols({}));

describe("ManaText: mana symbols in a card's text and costs", () => {
  it("draws letter circles while the host has no symbols (offline before the first download)", () => {
    const html = text("{T}: Add {C}{C}.");
    expect(html).not.toContain("<img");
    expect(html).toContain('class="mana tap"');
    expect(html.match(/class="mana c"/g)).toHaveLength(2);
    expect(html).toContain(": Add ");
  });

  it("shows the host's real symbols, named for screen readers, in the text's flow", () => {
    setSymbols(HOST);
    const html = text("{T}: Add {C}{C}.");
    expect(html).toContain('<img class="mana mana-sym" src="/api/symbols/T.svg" alt="tap this permanent"');
    expect(html.match(/src="\/api\/symbols\/C\.svg"/g)).toHaveLength(2);
    expect(html).toContain('draggable="false"');
    expect(html).not.toContain('class="mana c"');
    // a hybrid by its text, and one the host doesn't list keeps its letter circle
    const cost = text("{2/W}{G/U}{W}");
    expect(cost).toContain('src="/api/symbols/2W.svg"');
    expect(cost).toContain('class="mana hybrid g-u"');
    expect(cost).toContain('src="/api/symbols/W.svg"');
  });

  it("keeps the rules text's lines", () => {
    setSymbols(HOST);
    // (a server render also adds image preload hints first; the browser's render doesn't)
    const html = renderToStaticMarkup(createElement(OracleText, { text: "Flying\n{T}: Draw a card." })).replace(/<link [^>]*>/g, "");
    expect(html).toMatch(/^<p>Flying<\/p><p><img [^>]*T\.svg[^>]*\/?>: Draw a card\.<\/p>$/);
  });
});

describe("ColorPips: a deck's colour identity", () => {
  it("draws letter circles without the host's symbols, colorless as {C}", () => {
    const html = pips(["W", "U"]);
    expect(html).toMatch(/^<span class="pips">/);
    expect(html).toContain('class="mana w"');
    expect(html).toContain('aria-label="White"');
    expect(html).toContain(">U</span>");
    expect(pips([])).toContain('class="mana c"');
  });

  it("shows the real symbols, each named by its colour", () => {
    setSymbols(HOST);
    const html = pips(["W", "U"]);
    expect(html.match(/<img /g)).toHaveLength(2);
    expect(html).toContain('src="/api/symbols/W.svg" alt="White"');
    expect(html).toContain('src="/api/symbols/U.svg" alt="Blue"');
    expect(pips([])).toContain('src="/api/symbols/C.svg" alt="Colorless"');
    // a colour the host hasn't (yet) stays a letter circle beside the others
    expect(pips(["W", "B"])).toContain('class="mana b"');
  });
});
