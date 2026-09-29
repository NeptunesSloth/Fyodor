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

describe("lobby updates arriving out of order", () => {
  const lobby = (revision: number, bobReady: boolean) =>
    ({
      phase: "lobby",
      revision,
      game: { id: "g1" },
      seats: [{ id: "p1", ready: true }, { id: "p2", ready: bobReady }],
      start_blockers: bobReady ? [] : ["Bob isn't ready"],
    }) as unknown as import("../types/game").LobbyView;

  beforeEach(() => useGame.setState({ lobby: null, view: null }));

  it("keeps the newest lobby when an older HTTP response lands after a newer push", () => {
    const { applyLobby } = useGame.getState();
    applyLobby(lobby(7, true)); // WebSocket push: Bob just got ready
    applyLobby(lobby(6, false)); // Alice's own ready response, built earlier, arrives late
    expect(useGame.getState().lobby?.revision).toBe(7);
    expect(useGame.getState().lobby?.start_blockers).toEqual([]);
    applyLobby(lobby(8, false));
    expect(useGame.getState().lobby?.revision).toBe(8);
  });

  it("ignores a lobby once the game has started", () => {
    useGame.setState({ view: { game: { id: "g1" } } as unknown as GameView });
    useGame.getState().applyLobby(lobby(9, true));
    expect(useGame.getState().lobby).toBeNull();
  });
});
