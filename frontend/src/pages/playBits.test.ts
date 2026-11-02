import { describe, expect, it } from "vitest";
import type { DeckSummary } from "../types/decks";
import type { GameSummary, SaveSummary } from "../types/game";
import { deckSize, deckTitle, lastTable, mosaicGrid, shelfSaves, whenSaved } from "./playBits";

const deck = (over: Partial<DeckSummary> = {}): DeckSummary => ({
  id: "d1", name: "Superfriends", format: "commander", updated_at: "2026-11-01T10:00:00", counts: { commander: 1, main: 99, sideboard: 5 },
  commanders: ["Atraxa, Praetors' Voice"], color_identity: ["W", "U", "B", "G"], cover_id: "c1", unresolved: 0, ...over,
});
const game = (id: string, updated_at: number): GameSummary => ({
  id, name: id, format: "commander", mode: "local", code: null, has_password: false, turn: 1, players: [], spectators: 0, updated_at,
});
const save = (id: string, game_id: string, autosave: boolean): SaveSummary => ({
  id, game_id, name: id, autosave, version: 7, created_at: "2026-11-02T22:51:45", size: 1, game_name: game_id, format: "commander", turn: 1, players: [],
});

describe("the commander mosaic", () => {
  it("keeps every cell landscape so the art window fills it", () => {
    const ratio = (n: number) => { const [c, r] = mosaicGrid(n); return (10 / 7) * (r / c); };
    expect(mosaicGrid(1)).toEqual([1, 1]);
    expect(mosaicGrid(2)).toEqual([1, 2]); // two wide strips, not two tall halves
    expect(mosaicGrid(3)).toEqual([2, 2]); // the fourth cell stays empty felt
    expect(mosaicGrid(4)).toEqual([2, 2]);
    expect(mosaicGrid(6)).toEqual([2, 3]);
    for (const n of [1, 2, 3, 4, 5, 6]) expect(ratio(n)).toBeGreaterThanOrEqual(1.385); // the scan's art box is 1.385:1
  });
});

describe("when a save was made", () => {
  const now = new Date(2026, 10, 2, 23, 30);
  it("says today and yesterday in words, older saves by their date", () => {
    expect(whenSaved("2026-11-02T22:51:45", now)).toMatch(/^Today, /);
    expect(whenSaved("2026-11-01T20:10:00", now)).toMatch(/^Yesterday, /);
    expect(whenSaved("2026-10-31T20:15:00", now)).not.toMatch(/Today|Yesterday|2026/);
    expect(whenSaved("2025-10-31T20:15:00", now)).toMatch(/2025/);
    expect(whenSaved("not a date", now)).toBe("not a date");
  });
});

describe("decks by their commanders", () => {
  it("counts the cards a game uses and names a deck by its commanders", () => {
    expect(deckSize(deck())).toBe(100); // the sideboard isn't played
    expect(deckTitle(deck({ commanders: ["Kraum, Ludevic's Opus", "Tymna the Weaver"] }))).toBe("Kraum, Ludevic's Opus & Tymna the Weaver");
    expect(deckTitle(deck({ commanders: [] }))).toBe("Superfriends");
  });
});

describe("the shelf and Continue", () => {
  it("shows manual saves and only each game's newest autosave", () => {
    const list = [save("a3", "g1", true), save("m1", "g1", false), save("a2", "g1", true), save("b1", "g2", true), save("b0", "g2", true)];
    expect(shelfSaves(list).map((s) => s.id)).toEqual(["a3", "m1", "b1"]);
  });
  it("continues the latest table this device can open, else the newest save", () => {
    const games = [game("old", 10), game("new", 30), game("locked", 50)];
    const saves = [save("s1", "g9", false)];
    expect(lastTable(games, saves, (g) => g.id !== "locked")).toEqual({ kind: "table", game: games[1] });
    expect(lastTable([], saves, () => true)).toEqual({ kind: "save", save: saves[0] });
    expect(lastTable(games, null, () => false)).toBeNull();
  });
});
