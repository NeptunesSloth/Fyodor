import { describe, expect, it } from "vitest";
import type { CardData } from "../types/cards";
import type { DeckEntry } from "../types/decks";
import { checkSummary, curveStats, deckMatches, deckRecords, groupGlyph, groupTitle, playedWhen, recordText } from "./deckBits";

const player = (deck_key: string | null, outcome: "win" | "loss" | "draw" | "none") => ({
  seat: "p1", player_id: "x", name: "X", deck_key, deck_name: null, commanders: [], outcome,
});

describe("deck records from the pod's results", () => {
  it("counts games and wins per library deck and keeps the newest game", () => {
    const recs = deckRecords([
      { recorded_at: "2026-11-02T21:00:00", players: [player("deck:a", "win"), player("deck:b", "loss"), player("named:x|y", "loss")] },
      { recorded_at: "2026-10-30T20:00:00", players: [player("deck:a", "loss"), player(null, "win")] },
      { recorded_at: "2026-10-31T20:00:00", players: [player("deck:b", "draw"), player("deck:b", "draw")] },
    ]);
    expect(recs.get("a")).toEqual({ games: 2, wins: 1, last: "2026-11-02T21:00:00" });
    // two seats with the same deck in one game: one game for the deck
    expect(recs.get("b")).toEqual({ games: 2, wins: 0, last: "2026-11-02T21:00:00" });
    expect(recs.has("x|y")).toBe(false);
    expect([...recs.keys()].sort()).toEqual(["a", "b"]);
  });

  it("says the record in words", () => {
    expect(recordText({ games: 5, wins: 2 })).toBe("2 wins in 5 games");
    expect(recordText({ games: 4, wins: 1 })).toBe("1 win in 4 games");
    expect(recordText({ games: 3, wins: 0 })).toBe("No wins in 3 games");
    expect(recordText({ games: 1, wins: 1 })).toBe("1 win in 1 game");
    expect(recordText({ games: 1, wins: 0 })).toBe("No wins in 1 game");
  });

  it("says when a deck last played", () => {
    const now = new Date(2026, 10, 3, 1, 0);
    expect(playedWhen(new Date(2026, 10, 3, 0, 10).toISOString(), now)).toBe("today");
    expect(playedWhen(new Date(2026, 10, 2, 23, 0).toISOString(), now)).toBe("yesterday");
    expect(playedWhen(new Date(2026, 9, 31, 20, 0).toISOString(), now)).toMatch(/^on .*31/);
    expect(playedWhen(new Date(2025, 9, 31, 20, 0).toISOString(), now)).toMatch(/2025/);
    expect(playedWhen("not a date", now)).toBe("");
  });
});

describe("library search", () => {
  const d = { name: "Superfriends", commanders: ["Atraxa, Praetors' Voice"] };
  it("matches the deck name or a commander, ignoring case", () => {
    expect(deckMatches(d, "")).toBe(true);
    expect(deckMatches(d, "  super ")).toBe(true);
    expect(deckMatches(d, "atraxa")).toBe(true);
    expect(deckMatches(d, "krenko")).toBe(false);
  });
});

describe("the editor's numbers", () => {
  const card = (id: string, cmc: number, type_line: string) => ({ id, cmc, type_line }) as unknown as CardData;
  const entry = (printing_id: string | null, quantity = 1, section: DeckEntry["section"] = "main") =>
    ({ section, quantity, name: printing_id ?? "?", printing_id, set_code: null, collector_number: null }) as DeckEntry;
  const cards = {
    sol: card("sol", 1, "Artifact"),
    bolt: card("bolt", 1, "Instant"),
    big: card("big", 9, "Creature — Eldrazi"),
    mtn: card("mtn", 0, "Basic Land — Mountain"),
    cmd: card("cmd", 4, "Legendary Creature — Goblin"),
  };

  it("draws the main deck's curve with 7+ together, its average and its lands", () => {
    const s = curveStats([entry("sol"), entry("bolt", 2), entry("big"), entry("mtn", 30), entry("cmd", 1, "commander"), entry(null), entry("gone")], cards);
    expect(s.buckets).toEqual([0, 3, 0, 0, 0, 0, 0, 1]);
    expect(s.lands).toBe(30);
    expect(s.spells).toBe(4);
    expect(s.average).toBeCloseTo((1 + 2 + 9) / 4);
    expect(curveStats([entry("mtn", 3)], cards).average).toBeNull();
  });

  it("sums up the checks by their worst level", () => {
    expect(checkSummary([])).toEqual({ level: "ok", text: "No problems found" });
    expect(checkSummary([{ level: "info" }, { level: "info" }])).toEqual({ level: "info", text: "2 notes" });
    expect(checkSummary([{ level: "info" }, { level: "warning" }])).toEqual({ level: "warning", text: "1 warning" });
    expect(checkSummary([{ level: "warning" }, { level: "error" }])).toEqual({ level: "error", text: "2 problems" });
  });

  it("names type groups in the plural with the proxy's icon", () => {
    expect(groupTitle("Sorcery")).toBe("Sorceries");
    expect(groupTitle("Creature")).toBe("Creatures");
    expect(groupTitle("Ramp")).toBe("Ramp");
    expect(groupGlyph("Land")).toBe("land");
    expect(groupGlyph("Other")).toBe("other");
    expect(groupGlyph("Ramp")).toBeNull();
  });
});
