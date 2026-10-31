import { describe, expect, it } from "vitest";
import { linkProblem } from "./deckLinks";

describe("deck links at the table importer", () => {
  it("places Archidekt links, with or without the scheme, and bare deck numbers", () => {
    expect(linkProblem("https://archidekt.com/decks/123456/krenko_tokens")).toBeNull();
    expect(linkProblem("archidekt.com/decks/42")).toBeNull();
    expect(linkProblem("  987654 ")).toBeNull();
  });

  it("says how to bring a deck from a site it can't fetch", () => {
    expect(linkProblem("https://moxfield.com/decks/AbC123")).toMatch(/^Moxfield links can't be fetched.*export it as text/);
    expect(linkProblem("https://tappedout.net/mtg-decks/krenko/")).toMatch(/^TappedOut/);
    expect(linkProblem("https://example.com/decks/1")).toMatch(/^That site/);
  });

  it("isn't fooled by text that isn't a link", () => {
    expect(linkProblem("1 Sol Ring")).toMatch(/isn't a deck link/);
    expect(linkProblem("")).toBeNull();
  });
});
