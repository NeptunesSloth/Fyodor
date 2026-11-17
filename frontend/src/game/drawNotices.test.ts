import { beforeEach, describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { drewLine, mergeBatch, newDraws, noticeFaces, NOTICE_FACES, useFreshDraws, wantsNotice } from "./drawNotices";

type Opts = { hand: string[]; cards?: Record<string, string>; phase?: string; active?: string; stack?: string[]; searching?: boolean; pregame?: boolean; game?: string };

/** A view of p1's table: their hand, where each known card is (id → zone), the step, the stack. */
function view(o: Opts): GameView {
  const cards = Object.fromEntries(Object.entries(o.cards ?? {}).map(([id, zone]) => [id, { id, zone, name: id }]));
  for (const id of o.hand) cards[id] ??= { id, zone: "p1:hand", name: id };
  return {
    game: { id: o.game ?? "g" },
    zones: { "p1:hand": o.hand, "p1:library": { count: 50, known: [] } },
    cards,
    turn: { number: 3, active_player: o.active ?? "p1", phase: o.phase ?? "main1" },
    stack: o.stack ?? [],
    searches: o.searching ? { p1: "p1:library" } : {},
    pregame: o.pregame ? { seats: {}, finished: false } : null,
  } as unknown as GameView;
}

describe("what I drew", () => {
  it("cards new in my hand from my library are a draw (by an effect, outside the draw step)", () => {
    expect(newDraws(view({ hand: ["a"] }), view({ hand: ["a", "b", "c"] }), "p1")).toEqual({ ids: ["b", "c"], effect: true });
  });

  it("the draw step's one card is a draw, but not an effect's", () => {
    const ev = newDraws(view({ hand: ["a"], phase: "draw" }), view({ hand: ["a", "b"], phase: "draw" }), "p1");
    expect(ev).toEqual({ ids: ["b"], effect: false });
    expect(wantsNotice("effects", ev!)).toBe(false);
    expect(wantsNotice("all", ev!)).toBe(true);
    expect(wantsNotice("off", ev!)).toBe(false);
    // two cards in the draw step (Howling Mine), or one while something resolves, are an effect's
    expect(newDraws(view({ hand: ["a"], phase: "draw" }), view({ hand: ["a", "b", "c"], phase: "draw" }), "p1")!.effect).toBe(true);
    expect(newDraws(view({ hand: ["a"], phase: "draw", stack: ["s"] }), view({ hand: ["a", "b"], phase: "draw", stack: ["s"] }), "p1")!.effect).toBe(true);
    // a card drawn in an opponent's draw step is an effect's
    expect(newDraws(view({ hand: [], phase: "draw", active: "p2" }), view({ hand: ["b"], phase: "draw", active: "p2" }), "p1")!.effect).toBe(true);
  });

  it("a card known to be on top of my library (I looked) is still a draw", () => {
    expect(newDraws(view({ hand: [], cards: { t: "p1:library" } }), view({ hand: ["t"] }), "p1")!.ids).toEqual(["t"]);
  });

  it("a card I could see elsewhere is not a draw: bounced, undone, returned", () => {
    expect(newDraws(view({ hand: [], cards: { x: "p1:battlefield" } }), view({ hand: ["x"] }), "p1")).toBeNull();
    expect(newDraws(view({ hand: [], cards: { x: "p1:graveyard" } }), view({ hand: ["x"] }), "p1")).toBeNull();
    expect(newDraws(view({ hand: [], cards: { x: "stack" } }), view({ hand: ["x"] }), "p1")).toBeNull();
  });

  it("no notice for a tutor's search, the opening hand, a new game, or the first view", () => {
    expect(newDraws(view({ hand: [], searching: true }), view({ hand: ["b"] }), "p1")).toBeNull();
    expect(newDraws(view({ hand: [], pregame: true }), view({ hand: ["a", "b"], pregame: true }), "p1")).toBeNull();
    expect(newDraws(view({ hand: [], game: "old" }), view({ hand: ["a"] }), "p1")).toBeNull();
    expect(newDraws(null, view({ hand: ["a"] }), "p1")).toBeNull();
  });

  it("cards leaving my hand, or the same hand, are nothing", () => {
    expect(newDraws(view({ hand: ["a", "b"] }), view({ hand: ["a"] }), "p1")).toBeNull();
    expect(newDraws(view({ hand: ["a"] }), view({ hand: ["a"] }), "p1")).toBeNull();
  });

  it("only my own hand: another player's draw is never mine to see", () => {
    expect(newDraws(view({ hand: ["a"] }), view({ hand: ["a", "b"] }), "p2")).toBeNull();
  });
});

describe("one notice per burst", () => {
  it("draws while the notice is up join it, without repeats", () => {
    let b = mergeBatch(null, ["a", "b"], 1);
    b = mergeBatch(b, ["b", "c"], 2);
    expect(b).toEqual({ key: 1, ids: ["a", "b", "c"] });
  });

  it("a 77-card loop shows the first faces and a count", () => {
    let b = mergeBatch(null, ["c0"], 1);
    for (let i = 1; i < 77; i++) b = mergeBatch(b, [`c${i}`], i + 1);
    const { faces, more } = noticeFaces(b);
    expect(faces.length).toBe(NOTICE_FACES);
    expect(faces[0]).toBe("c0");
    expect(more).toBe(77 - NOTICE_FACES);
  });

  it("reads like a sentence", () => {
    expect(drewLine(["Island"], 1)).toBe("Island");
    expect(drewLine(["Lightning Bolt", "Island"], 2)).toBe("Lightning Bolt and Island");
    expect(drewLine(["A", "B", "C"], 3)).toBe("A, B and C");
    expect(drewLine(["A", "B", "C", "D", "E", "F"], 12)).toBe("A, B, C, D and 8 more");
    expect(drewLine([], 0)).toBe("");
  });
});

describe("fresh cards in my hand", () => {
  beforeEach(() => useFreshDraws.setState({ ids: [], turn: 0 }));

  it("stay marked until hovered, and a new turn starts afresh", () => {
    const s = useFreshDraws.getState();
    s.add(["a", "b"], 3);
    s.add(["b", "c"], 3);
    expect(useFreshDraws.getState().ids).toEqual(["a", "b", "c"]);
    useFreshDraws.getState().seen("a");
    expect(useFreshDraws.getState().ids).toEqual(["b", "c"]);
    useFreshDraws.getState().add(["d"], 4);
    expect(useFreshDraws.getState().ids).toEqual(["d"]);
  });
});
