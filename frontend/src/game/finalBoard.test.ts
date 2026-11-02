import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "../components/Toasts";
import { useGame } from "../state/gameStore";
import { SPECTATOR, type GameView } from "../types/game";
import { FINAL_BOARD_NOTE, boardBar, finalBoardRefusal } from "./finalBoard";

const SEATS = ["p1", "p2", "p3"];
type Result = NonNullable<NonNullable<GameView["game"]["night"]>["result"]>;

function view(over: { viewer?: string; mode?: "lan" | "local"; result?: Partial<Result> | null; votes?: Record<string, "rematch" | "lobby">; open?: string[] } = {}): GameView {
  const result = over.result === null || over.result === undefined ? null
    : { result_type: "single", winners: ["p2"], winner_names: ["Ben"], agreed: false, ...over.result };
  const seats = Object.fromEntries(SEATS.map((id) => [id, { claimed: !(over.open ?? []).includes(id) }]));
  return {
    viewer: over.viewer ?? "p1",
    seat_order: SEATS,
    players: SEATS.map((id, i) => ({ id, name: ["Ann", "Ben", "Cat"][i] })),
    turn: { active_player: "p1" },
    cards: {},
    game: { id: "g", mode: over.mode ?? "lan", seats, night: { number: 3, proposal: null, result, votes: over.votes ?? {}, rolls: [], history: [] } },
  } as unknown as GameView;
}

describe("the final board refuses changes once the game has a result", () => {
  it("lets everything through while the game goes on", () => {
    expect(finalBoardRefusal(view(), "tap")).toBeNull();
    expect(finalBoardRefusal(null, "tap")).toBeNull();
  });
  it("refuses table changes after the result, but keeps table talk open", () => {
    const over = view({ result: {} });
    for (const type of ["tap", "move", "set_position", "life", "pass_priority", "concede", "restart_game"]) {
      expect(finalBoardRefusal(over, type)).toBe(FINAL_BOARD_NOTE);
    }
    expect(finalBoardRefusal(over, "chat")).toBeNull();
    expect(finalBoardRefusal(over, "end_view")).toBeNull();
    expect(finalBoardRefusal(over, "search_end")).toBe(FINAL_BOARD_NOTE); // it can shuffle a library
  });
});

describe("the bar over the final board", () => {
  it("says the result and how far the vote is", () => {
    expect(boardBar(view(), "p1")).toBeNull();
    expect(boardBar(view({ result: {}, votes: { p1: "rematch", p3: "lobby" } }), "p1")).toEqual({ line: "Game 3 · Ben wins", votes: "Votes 2/3", mine: "rematch" });
    expect(boardBar(view({ result: { result_type: "draw", winners: [], winner_names: [] } }), "p2")).toEqual({ line: "Game 3 · Draw", votes: "Votes 0/3", mine: null });
    expect(boardBar(view({ result: { result_type: "multiple", winners: ["p1", "p3"], winner_names: ["Ann", "Cat"] } }), "p1")!.line).toBe("Game 3 · Ann & Cat win");
  });
  it("counts only claimed seats at a LAN table, and nobody's vote at a hot-seat one", () => {
    expect(boardBar(view({ result: {}, open: ["p3"] }), "p1")!.votes).toBe("Votes 0/2");
    expect(boardBar(view({ result: {}, mode: "local", votes: { p1: "rematch" } }), "p1")!.votes).toBeNull();
  });
  it("never shows a spectator a vote of their own", () => {
    expect(boardBar(view({ viewer: SPECTATOR, result: {}, votes: { p1: "rematch" } }), "p1")!.mine).toBeNull();
  });
});

describe("the store doesn't send what the final board refuses", () => {
  const requestAction = vi.fn(() => Promise.resolve());
  beforeEach(() => {
    requestAction.mockClear();
    useToasts.setState({ toasts: [] });
    useGame.setState({ conn: { requestAction } as never, view: view({ result: {} }), actingAs: null, pendingPositions: { c1: [1, 2] } });
  });

  it("drops a drag on the finished table, puts the card back and says why once", async () => {
    expect(await useGame.getState().send({ type: "set_position", moves: [["c1", 1, 2]] } as never)).toBe(false);
    expect(await useGame.getState().send({ type: "tap", card_ids: ["c1"] } as never)).toBe(false);
    expect(requestAction).not.toHaveBeenCalled();
    expect(useGame.getState().pendingPositions).toEqual({});
    expect(useToasts.getState().toasts.map((t) => t.text)).toEqual([FINAL_BOARD_NOTE]);
  });

  it("still sends chat, and everything while the game goes on", async () => {
    expect(await useGame.getState().send({ type: "chat", text: "gg" } as never)).toBe(true);
    useGame.setState({ view: view() });
    expect(await useGame.getState().send({ type: "tap", card_ids: ["c1"] } as never)).toBe(true);
    expect(requestAction).toHaveBeenCalledTimes(2);
  });
});
