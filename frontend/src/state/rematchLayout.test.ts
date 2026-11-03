import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GameView, LobbyView } from "../types/game";

// The store's connection, replaced by one whose handlers the test calls (a view arriving from the server).
const { socket } = vi.hoisted(() => ({ socket: { onState: null as null | ((view: GameView, replace?: boolean) => void) } }));
vi.mock("../services/gameSocket", async (original) => ({
  ...(await original<object>()),
  GameConnection: class {
    constructor(_id: string, _params: unknown, handlers: { onState: (view: GameView, replace?: boolean) => void }) {
      socket.onState = handlers.onState;
    }
    connect() {}
    close() {}
  },
}));

const { useGame } = await import("./gameStore");

/** A table's view: the game of the night ``night`` on table ``id``. */
const game = (night: number, id = "g1", revision = night): GameView =>
  ({
    viewer: "p1", seat_order: ["p1", "p2"], cards: {}, zones: {}, stack: [], log: [],
    players: [{ id: "p1", name: "Alice", commanders: [] }, { id: "p2", name: "Bob", commanders: [] }],
    game: { id, revision, mode: "lan", seats: { p1: {}, p2: {} }, night: { number: night } },
    turn: { active_player: "p1" },
  }) as unknown as GameView;

const arrive = (view: GameView, replace = true) => socket.onState!(view, replace);

describe("the 2D table's focus belongs to one game of the night", () => {
  beforeEach(() => {
    useGame.setState({ view: null, lobby: null, focus: null, stackOpen: true, logOpen: false });
    useGame.getState().connect("g1", {});
  });

  it("keeps the focus while the same game goes on (a fresh snapshot after a reconnect too)", () => {
    arrive(game(1));
    useGame.getState().setLayout({ focus: "p2" });
    arrive(game(1, "g1", 5));
    expect(useGame.getState().focus).toBe("p2");
  });

  it("goes back to the whole table when a rematch starts (same table id, next game of the night)", () => {
    arrive(game(1));
    useGame.getState().setLayout({ focus: "p2", logOpen: true }); // the end scene focused the winner's side (GameNight)
    arrive(game(2));
    expect(useGame.getState().focus).toBeNull();
    expect(useGame.getState().logOpen).toBe(true); // (open panels are the player's choice, not the game's)
  });

  it("goes back to the whole table when the next game starts after the pod went back to the lobby", () => {
    arrive(game(1));
    useGame.getState().setLayout({ focus: "p2" });
    useGame.getState().applyLobby({ game: { id: "g1" }, revision: 99 } as unknown as LobbyView);
    expect(useGame.getState().view).toBeNull();
    arrive(game(2));
    expect(useGame.getState().focus).toBeNull();
  });

  it("keeps the focus when the player comes back to the same game", () => {
    arrive(game(1));
    useGame.getState().setLayout({ focus: "p2" });
    useGame.getState().connect("g1", {});
    arrive(game(1));
    expect(useGame.getState().focus).toBe("p2");
  });
});
