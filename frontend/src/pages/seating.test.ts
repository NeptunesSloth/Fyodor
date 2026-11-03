import { describe, expect, it } from "vitest";
import type { LobbyView } from "../types/game";
import { canNudge, miniSeats, moveSeat, nudgeSeat, previewLine, previewParts, rollsText } from "./seating";

const ORDER = ["p1", "p2", "p3", "p4"];

describe("arranging seats", () => {
  it("moves a dragged seat to the target's place, the others shifting by one", () => {
    expect(moveSeat(ORDER, "p4", "p1")).toEqual(["p4", "p1", "p2", "p3"]);
    expect(moveSeat(ORDER, "p1", "p3")).toEqual(["p2", "p3", "p1", "p4"]);
    expect(moveSeat(ORDER, "p2", "p2")).toBe(ORDER);
    expect(moveSeat(ORDER, "p9", "p2")).toBe(ORDER);
  });
  it("swaps a seat with its neighbour for the arrows, never past either end", () => {
    expect(nudgeSeat(ORDER, "p2", -1)).toEqual(["p2", "p1", "p3", "p4"]);
    expect(nudgeSeat(ORDER, "p2", 1)).toEqual(["p1", "p3", "p2", "p4"]);
    expect(nudgeSeat(ORDER, "p1", -1)).toBe(ORDER);
    expect(nudgeSeat(ORDER, "p4", 1)).toBe(ORDER);
    expect(canNudge(ORDER, "p1", -1)).toBe(false);
    expect(canNudge(ORDER, "p1", 1)).toBe(true);
    expect(canNudge(ORDER, "p4", 1)).toBe(false);
    expect(canNudge(ORDER, "p9", 1)).toBe(false);
  });
  it("always lists every seat once", () => {
    for (const from of ORDER) for (const to of ORDER) expect([...moveSeat(ORDER, from, to)].sort()).toEqual(ORDER);
  });
});

describe("the next game's order", () => {
  const lobby = (turn_order: "pod" | "random" | "seats", preview?: LobbyView["turn_preview"]) =>
    ({
      settings: { turn_order },
      seats: [
        { id: "p1", name: "Ann", claimed: true },
        { id: "p2", name: "Ben", claimed: true },
        { id: "p3", name: "", claimed: false },
        { id: "p4", name: "Cat", claimed: true },
      ],
      turn_preview: preview,
    }) as unknown as LobbyView;

  it("says the d20 decides under the pod rule's first game", () => {
    expect(previewLine(lobby("pod", { source: "d20", order: ["p1", "p2", "p4"], previous_winner: null }))).toMatch(/d20/);
  });
  it("puts last game's winner last under the pod rule", () => {
    expect(previewLine(lobby("pod", { source: "winner_last", order: ["p1", "p4", "p2"], previous_winner: "p2" })))
      .toBe("Ann → Cat → Ben · Ben won last game and goes last.");
  });
  it("names seat 1 for the seat order, and a random first player otherwise", () => {
    expect(previewLine(lobby("seats", { source: "seats", order: ["p4", "p1", "p2"], previous_winner: null }))).toBe("Cat → Ann → Ben · Cat goes first.");
    expect(previewLine(lobby("random", { source: "random", order: ["p1", "p2", "p4"], previous_winner: null }))).toMatch(/^Ann → Ben → Cat · a random player/);
  });
  it("falls back to the claimed seats for a server without the preview, and says nothing for one player", () => {
    expect(previewLine(lobby("seats"))).toBe("Ann → Ben → Cat · Ann goes first.");
    expect(previewLine(lobby("seats", { source: "seats", order: ["p1"], previous_winner: null }))).toBe("");
  });
  it("writes a game's recorded rolls, tie-breaks after", () => {
    expect(rollsText([{ Ann: 15, Ben: 4, Cat: 15 }, { Ann: 2, Cat: 9 }])).toBe("Ann 15, Ben 4, Cat 15 · tie-break Ann 2, Cat 9");
    expect(rollsText([])).toBe("");
  });
});

describe("the next game's order, in parts for the lobby", () => {
  const lobby = (turn_order: "pod" | "random" | "seats", preview?: LobbyView["turn_preview"]) =>
    ({
      settings: { turn_order },
      seats: [
        { id: "p1", name: "Ann", claimed: true },
        { id: "p2", name: "Ben", claimed: true },
        { id: "p3", name: "", claimed: false },
        { id: "p4", name: "Cat", claimed: true },
      ],
      turn_preview: preview,
    }) as unknown as LobbyView;

  it("names who goes first only when it is known", () => {
    expect(previewParts(lobby("pod", { source: "winner_last", order: ["p1", "p4", "p2"], previous_winner: "p2" })))
      .toEqual({ order: ["p1", "p4", "p2"], first: "p1", note: "Ben won last game and goes last.", source: "winner_last" });
    expect(previewParts(lobby("seats"))).toMatchObject({ order: ["p1", "p2", "p4"], first: "p1", note: "Ann goes first." });
    expect(previewParts(lobby("random", { source: "random", order: ["p1", "p2", "p4"], previous_winner: null })))
      .toMatchObject({ first: null, note: "A random player goes first, then around the table." });
  });
  it("gives no order while a d20 decides, and nothing at all for one player", () => {
    const d20 = previewParts(lobby("pod", { source: "d20", order: ["p1", "p2", "p4"], previous_winner: null }));
    expect(d20.order).toEqual([]);
    expect(d20.note).toMatch(/d20/);
    expect(previewParts(lobby("seats", { source: "seats", order: ["p1"], previous_winner: null })))
      .toMatchObject({ order: [], note: "" });
  });
});

describe("the miniature table", () => {
  it("puts the viewer on the near side and goes clockwise: along their row to the left, then back across", () => {
    const at = Object.fromEntries(miniSeats(["a", "b", "c", "d"], "c").map((s) => [s.id, s]));
    expect(at.c!.y).toBe(1);
    expect(at.d!.y).toBe(1);
    expect(at.d!.x).toBeLessThan(at.c!.x);
    expect([at.a!.y, at.b!.y]).toEqual([0, 0]);
    expect(at.a!.x).toBeLessThan(at.b!.x);
  });
  it("seats a watcher's table from the first player, and keeps every seat on the table", () => {
    const placed = miniSeats(["a", "b", "c"], "spectator");
    expect(placed.find((s) => s.id === "a")!.y).toBe(1);
    for (const s of miniSeats(["a", "b", "c", "d", "e", "f"], "a")) {
      expect(s.x).toBeGreaterThan(0);
      expect(s.x).toBeLessThan(1);
    }
    expect(miniSeats([], "a")).toEqual([]);
    expect(miniSeats(["a"], "a")).toEqual([{ id: "a", x: 0.5, y: 1 }]);
  });
});
