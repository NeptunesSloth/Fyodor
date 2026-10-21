import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { exportPersonalLibrary, personalDeckFile } from "./personalLibrary";
import { myDecks, rememberMyDeck, personalCollection } from "./games";

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (k: string) => values.get(k) ?? null,
    setItem: vi.fn((k: string, v: string) => { values.set(k, v); }), clear: () => values.clear() });
});
afterEach(() => vi.unstubAllGlobals());

it("saves normalized lists rather than URLs, survives reload, and retains more than twenty decks", () => {
  for (let i = 0; i < 25; i++) rememberMyDeck(`Deck ${i}`, { archidekt: `https://archidekt.com/decks/${i}` }, [], {
    name: `Deck ${i}`, text: `Deck\n${i + 1} Island\n`,
    entries: [{ name: "Island", printing_id: "island", quantity: i + 1, section: "main" }], commanders: [], companions: [],
  });
  expect(myDecks()).toHaveLength(25);
  expect(myDecks().every(d => d.body.text && !d.body.archidekt)).toBe(true);
  expect(personalCollection()).toHaveLength(1);
  expect(personalCollection()[0]?.quantity).toBe(325);
});

it("does not replace different decks with the same title, or silently claim storage succeeded", () => {
  rememberMyDeck("My deck", { text: "1 Island" }, []);
  rememberMyDeck("My deck", { text: "1 Mountain" }, []);
  expect(myDecks()).toHaveLength(2);
  vi.mocked(localStorage.setItem).mockImplementation(() => { throw new Error("Quota exceeded"); });
  expect(() => rememberMyDeck("Third", { text: "1 Sol Ring" }, [])).toThrow();
  vi.restoreAllMocks();
});


it("refreshes an imported source instead of double-counting an old version", () => {
  const body = { archidekt: "https://archidekt.com/decks/123/my-deck" };
  const entry = { name: "Island", quantity: 1, printing_id: "island", section: "main" as const };
  const imported = { name: "Deck", text: "1 Island", entries: [entry], commanders: [], companions: [] };
  rememberMyDeck("Deck", body, [], imported);
  rememberMyDeck("Deck", body, [], { ...imported, text: "2 Island", entries: [{ ...entry, quantity: 2 }] });
  expect(myDecks()).toHaveLength(1);
  expect(personalCollection()[0]?.quantity).toBe(2);
});


it("exports portable offline lists and refuses URL-only or malformed backups", () => {
  rememberMyDeck("One", { text: "1 Island" }, []);
  rememberMyDeck("Two", { text: "1 Sol Ring" }, []);
  const decoded = personalDeckFile(exportPersonalLibrary(), "backup.json");
  expect(decoded.map(d => d.body.text)).toEqual(["1 Sol Ring", "1 Island"]);
  expect(decoded.every(d => !d.body.archidekt && !d.body.deck_id)).toBe(true);
  expect(() => personalDeckFile(JSON.stringify({ format: "fyodor-personal-decks", version: 1, decks: [{ name: "Unsafe", body: { archidekt: "123" } }] }), "bad.json")).toThrow();
  rememberMyDeck("Legacy", { archidekt: "123" }, []);
  expect(() => exportPersonalLibrary()).toThrow(/once while online/);
});
