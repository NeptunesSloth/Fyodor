import { beforeEach, describe, expect, it } from "vitest";
import { OMNISCIENT, type GameView } from "../types/game";
import { perspective, playerName, useGame } from "./gameStore";

const view = (viewer: string): GameView =>
  ({
    viewer,
    seat_order: ["p1", "p2"],
    players: [
      { id: "p1", name: "Alice" },
      { id: "p2", name: "Bob" },
    ],
    game: { seats: { p1: {}, p2: {} } },
    turn: { active_player: "p2" },
  }) as unknown as GameView;

describe("game store selection", () => {
  beforeEach(() => useGame.setState({ selection: [] }));

  it("replaces, toggles and adds", () => {
    const { select } = useGame.getState();
    select(["a", "b"]);
    expect(useGame.getState().selection).toEqual(["a", "b"]);
    select(["b", "c"], "toggle");
    expect(useGame.getState().selection).toEqual(["a", "c"]);
    select(["c", "d"], "add");
    expect(useGame.getState().selection).toEqual(["a", "c", "d"]);
    useGame.getState().clearSelection();
    expect(useGame.getState().selection).toEqual([]);
  });
});

describe("perspective", () => {
  it("uses the viewer's own seat", () => {
    expect(perspective(view("p2"), "p1")).toBe("p2");
  });
  it("falls back to the acting seat for open-table views", () => {
    expect(perspective(view(OMNISCIENT), "p2")).toBe("p2");
    expect(perspective(view(OMNISCIENT), null)).toBe("p1");
  });
  it("resolves player names", () => {
    expect(playerName(view("p1"), "p2")).toBe("Bob");
    expect(playerName(null, "p2")).toBe("");
  });
});
