import { describe, expect, it } from "vitest";
import type { GameView, MajorEvent } from "../types/game";
import { EventTracker, MAX_BURST, commandersOf, liveHash, liveLine, liveOver, tableNotices } from "./eliminationHub";

const ev = (id: string, kind: MajorEvent["kind"] = "out", players: string[] = ["p3"]): MajorEvent =>
  ({ id, game: 1, kind, text: `event ${id}`, players });

const live = (over: Record<string, unknown> = {}): GameView =>
  ({
    viewer: "p3",
    seat_order: ["p1", "p2", "p3", "p4"],
    players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }, { id: "p3", name: "Carol" }, { id: "p4", name: "Dan", left: true }],
    turn: { number: 7, active_player: "p2" },
    rules: { conceded: ["p3"], lost: {} },
    game: { night: { number: 1, result: null } },
    ...over,
  }) as unknown as GameView;

describe("EventTracker", () => {
  it("never announces what was already there when it first looks", () => {
    const t = new EventTracker();
    expect(t.take([ev("a-1"), ev("a-2")])).toEqual([]);
    expect(t.take([ev("a-1"), ev("a-2")])).toEqual([]);
  });
  it("hands out each new event once, in order", () => {
    const t = new EventTracker();
    t.take([]);
    expect(t.take([ev("a-1")]).map((e) => e.id)).toEqual(["a-1"]);
    expect(t.take([ev("a-1"), ev("a-2"), ev("a-3")]).map((e) => e.id)).toEqual(["a-2", "a-3"]);
    expect(t.take([ev("a-2"), ev("a-3")])).toEqual([]);
    expect(t.take(undefined)).toEqual([]);
  });
  it("keeps a burst short (no spam)", () => {
    const t = new EventTracker();
    t.take([]);
    const burst = ["1", "2", "3", "4", "5"].map((n) => ev(`b-${n}`));
    expect(t.take(burst).map((e) => e.id)).toEqual(burst.slice(-MAX_BURST).map((e) => e.id));
  });
});

describe("tableNotices", () => {
  it("leaves the result to the result spotlight and your own departure to your ELIMINATED moment", () => {
    const list = [ev("1", "out", ["p3"]), ev("2", "out", ["p2"]), ev("3", "final_two", ["p1", "p3"]), ev("4", "result", ["p1"])];
    expect(tableNotices(list, "p3").map((e) => e.id)).toEqual(["2", "3"]);
    expect(tableNotices(list, null).map((e) => e.id)).toEqual(["1", "2", "3"]);
  });
});

describe("the practice pill", () => {
  it("goes back to the live seat (by viewer at a hot-seat table)", () => {
    expect(liveHash({ of: "abc", seat: "p3", local: false })).toBe("#/game/abc");
    expect(liveHash({ of: "abc", seat: "p3", local: true })).toBe("#/game/abc?viewer=p3");
  });
  it("brings the player back once the live game has a result or has moved on", () => {
    expect(liveOver({ game: 1 }, live())).toBe(false);
    expect(liveOver({ game: 1 }, live({ game: { night: { number: 1, result: { winners: ["p1"] } } } }))).toBe(true);
    expect(liveOver({ game: 1 }, live({ game: { night: { number: 2, result: null } } }))).toBe(true);
  });
  it("sums up the live game in one public line", () => {
    expect(liveLine(live())).toBe("Turn 7 · Bob's turn · 2 still in");
  });
});

describe("Deck Lab", () => {
  it("reads the commanders from an edited list", () => {
    const text = "Commander\n1 Lim-Dûl the Necromancer (TSP) 114\n1x Tymna the Weaver\n\nDeck\n10 Forest (CMM) 1002\n1 Grizzly Bears\n";
    expect(commandersOf(text)).toEqual(["Lim-Dûl the Necromancer", "Tymna the Weaver"]);
    expect(commandersOf("Deck\n1 Forest\n")).toEqual([]);
    expect(commandersOf("Commander\nAtraxa, Praetors' Voice\nDeck\nSol Ring\n")).toEqual(["Atraxa, Praetors' Voice"]);
  });
});
