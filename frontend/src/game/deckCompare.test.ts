import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DeckEntry } from "../types/decks";
import { compareDecks, deckLines } from "./deckCompare";
import { DeckChanges } from "./DeckChanges";

// the list Deck Lab copies (backend format_deck_text: section headers, "qty Name (SET) number")
const BROUGHT = `Commander
1 Krenko, Mob Boss (DDN) 13

Deck
1 Lightning Bolt (CLB) 187
1 Pyroblast (ICE) 213
1 Sol Ring (C21) 263
14 Mountain (CMM) 1003

Sideboard
1 Red Elemental Blast (LEA) 172
`;

describe("Deck Lab: reading a deck list", () => {
  it("reads sections, quantities and names, without printings, foil marks or categories", () => {
    expect(deckLines(BROUGHT)).toEqual([
      { section: "commander", name: "Krenko, Mob Boss", quantity: 1 },
      { section: "main", name: "Lightning Bolt", quantity: 1 },
      { section: "main", name: "Pyroblast", quantity: 1 },
      { section: "main", name: "Sol Ring", quantity: 1 },
      { section: "main", name: "Mountain", quantity: 14 },
      { section: "sideboard", name: "Red Elemental Blast", quantity: 1 },
    ]);
    expect(deckLines("// Creatures (2)\n2x Goblin Guide *F* {Aggro}\nSkullclamp\nShock x3\n0 Nothing")).toEqual([
      { section: "main", name: "Goblin Guide", quantity: 2 },
      { section: "main", name: "Skullclamp", quantity: 1 },
      { section: "main", name: "Shock", quantity: 3 },
    ]);
  });
});

describe("Deck Lab: comparing the next-game version with the deck brought", () => {
  it("lists what comes in and goes out, by section then name, with the deck's size", () => {
    const edited = BROUGHT.replace("1 Pyroblast (ICE) 213\n", "1 Goblin Bombardment\n1 Skullclamp (C21) 109\n").replace("14 Mountain", "13 mountain");
    expect(compareDecks(deckLines(BROUGHT), deckLines(edited))).toEqual({
      added: [{ section: "main", name: "Goblin Bombardment", n: 1 }, { section: "main", name: "Skullclamp", n: 1 }],
      removed: [{ section: "main", name: "mountain", n: 1 }, { section: "main", name: "Pyroblast", n: 1 }],
      before: 18, after: 18,
    });
  });

  it("a new printing of the same card or a reordered list is no change; a card moved to the sideboard is", () => {
    const reordered = "Sideboard\n1 Red Elemental Blast\nDeck\n14 Mountain\n1 Sol Ring\n1 Lightning Bolt (M10) 146\n1 Pyroblast\nCommander\n1 Krenko, Mob Boss\n";
    expect(compareDecks(deckLines(BROUGHT), deckLines(reordered))).toEqual({ added: [], removed: [], before: 18, after: 18 });
    const moved = BROUGHT.replace("1 Sol Ring (C21) 263\n", "").replace("Sideboard\n", "Sideboard\n1 Sol Ring\n");
    expect(compareDecks(deckLines(BROUGHT), deckLines(moved))).toEqual({
      added: [{ section: "sideboard", name: "Sol Ring", n: 1 }], removed: [{ section: "main", name: "Sol Ring", n: 1 }], before: 18, after: 17,
    });
  });

  it("compares a library deck's entries the same way (the host computer's copy, edited in the deck editor)", () => {
    const entry = (section: DeckEntry["section"], quantity: number, name: string) => ({ section, quantity, name }) as DeckEntry;
    const entries = [entry("commander", 1, "Krenko, Mob Boss"), entry("main", 1, "Lightning Bolt"), entry("main", 2, "Pyroblast"), entry("main", 1, "Sol Ring"), entry("main", 14, "Mountain"), entry("sideboard", 1, "Red Elemental Blast")];
    expect(compareDecks(deckLines(BROUGHT), entries)).toEqual({ added: [{ section: "main", name: "Pyroblast", n: 1 }], removed: [], before: 18, after: 19 });
  });

  it("shows In and Out with the counts, the sections that aren't the deck, and the size before and after", () => {
    const html = renderToStaticMarkup(createElement(DeckChanges, { cmp: {
      added: [{ section: "main", name: "Skullclamp", n: 1 }, { section: "sideboard", name: "Sol Ring", n: 2 }],
      removed: [{ section: "main", name: "Mountain", n: 3 }], before: 100, after: 98,
    } }));
    expect(html).toContain('data-testid="deck-compare"');
    expect(html).toContain("100 → 98 cards");
    expect(html).toMatch(/In <span class="deck-compare-total">\+3<\/span>/);
    expect(html).toMatch(/Out <span class="deck-compare-total">−3<\/span>/);
    expect(html).toContain('<span class="deck-compare-n">+2</span><span class="deck-compare-name">Sol Ring</span><span class="deck-compare-sec">Sideboard</span>');
    expect(html).toContain('<span class="deck-compare-n">−3</span><span class="deck-compare-name">Mountain</span></li>');
    const same = renderToStaticMarkup(createElement(DeckChanges, { cmp: { added: [], removed: [], before: 100, after: 100 } }));
    expect(same).toContain("No changes yet: this is the deck you brought.");
    expect(same).toContain("100 cards");
  });
});
