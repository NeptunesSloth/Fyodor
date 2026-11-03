import { describe, expect, it } from "vitest";
import { OTHER_SITES, linkProblem } from "./deckLinks";

describe("deck links at the table importer", () => {
  it("places Archidekt links, with or without the scheme, and bare deck numbers", () => {
    expect(linkProblem("https://archidekt.com/decks/123456/krenko_tokens")).toBeNull();
    expect(linkProblem("archidekt.com/decks/42")).toBeNull();
    expect(linkProblem("  987654 ")).toBeNull();
  });

  it("says why each site's link can't be fetched and gives that site's steps", () => {
    const cases: [string, RegExp][] = [
      ["https://moxfield.com/decks/AbC123", /^Moxfield has no public export link .*API key.*More → Export → Copy Plain Text, then paste it in the box below\.$/],
      ["moxfield.com/decks/AbC123", /^Moxfield has no public export link/],
      ["https://www.mtggoldfish.com/deck/8022091#paper", /^MTGGoldfish .*robots\.txt.*Download → Text File \(Default\)/],
      ["https://tappedout.net/mtg-decks/krenko/", /^TappedOut asks every visitor for a browser check.*\?fmt=txt/],
      ["https://deckstats.net/decks/12345/678910-atraxa/en", /^Deckstats asks every visitor for a browser check.*\?export_txt=1/],
    ];
    for (const [link, message] of cases) {
      expect(OTHER_SITES.test(link)).toBe(true); // Place stays disabled for these
      expect(linkProblem(link)).toMatch(message);
    }
    expect(linkProblem("https://scryfall.com/@someone/decks/abc")).toMatch(/^Scryfall links can't be fetched/);
    expect(linkProblem("https://example.com/decks/1")).toMatch(/^That site/);
  });

  it("isn't fooled by text that isn't a link", () => {
    expect(linkProblem("1 Sol Ring")).toMatch(/isn't a deck link/);
    expect(linkProblem("")).toBeNull();
  });
});
