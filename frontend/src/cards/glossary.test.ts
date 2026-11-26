import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { setGlossary, splitKeywords } from "./glossary";
import { ManaText } from "./ManaText";

const G = { flying: "Can't be blocked except by flying or reach.", fight: "Each deals damage equal to its power to the other.", landfall: "Ability word.", ward: "Counter it unless that player pays [cost]." };

describe("keyword help", () => {
  it("with the card's own keywords: each of them anywhere, in any case", () => {
    const parts = splitKeywords("Flying\nOther creatures with flying get +1/+1.", G, ["Flying"]);
    expect(parts.filter((p) => typeof p !== "string").map((p) => (p as { word: string }).word)).toEqual(["Flying", "flying"]);
  });
  it("without a list: only where a keyword stands (start of a clause), so a verb in a sentence is left alone", () => {
    const words = (t: string) => splitKeywords(t, G).filter((p) => typeof p !== "string").map((p) => (p as { word: string }).word);
    expect(words("Landfall — Whenever a land you control enters, it can fight target creature.")).toEqual(["Landfall"]);
    expect(words("Flying, ward")).toEqual(["Flying", "ward"]);
  });
  it("draws a focusable dotted mark carrying the reminder, only when asked", () => {
    setGlossary(G);
    const html = renderToStaticMarkup(createElement(ManaText, { text: "Ward {2}", keywords: true }));
    expect(html).toContain('<span class="kw" tabindex="0" data-sym-tip="Counter it unless that player pays [cost].">Ward</span>');
    expect(renderToStaticMarkup(createElement(ManaText, { text: "Ward {2}" }))).not.toContain("kw");
  });
});
