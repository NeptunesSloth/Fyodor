import { describe, expect, it, vi } from "vitest";
import type { GameView, UndoRequestInfo } from "../types/game";
import { undoMode, undoRequestSeat } from "./undoPolicy";

const asked: unknown[][] = [];
vi.mock("../services/undoRequest", () => ({ undoRequest: (...args: unknown[]) => { asked.push(args); return Promise.resolve({}); } }));
vi.mock("../components/Toasts", () => ({ toast: () => undefined }));

const view = (game: Record<string, unknown> = {}, over: Record<string, unknown> = {}): GameView =>
  ({
    viewer: "p2",
    seat_order: ["p1", "p2", "p3"],
    turn: { active_player: "p3" },
    players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }, { id: "p3", name: "Cleo" }],
    game: { mode: "lan", seats: { p1: {}, p2: {}, p3: {} }, settings: {}, can_undo: true, can_redo: false, ...game },
    ...over,
  }) as unknown as GameView;

const DRAW = "This undo would take back a draw that players already saw.";
const request = (over: Partial<UndoRequestInfo> = {}): UndoRequestInfo => ({
  id: "r1", by: "p2", by_name: "Bob", label: "draw", shown: "draw", why: DRAW,
  voters: ["p1", "p3"], approved: ["p1"], waiting: ["p3"], ...over,
});

describe("undoMode", () => {
  it("undoes directly when the server asks for nothing (old servers send no fields)", () => {
    expect(undoMode(view(), "p2")).toEqual({ kind: "direct" });
    expect(undoMode(view({ can_undo: false }), "p2")).toEqual({ kind: "none" });
  });
  it("asks the table when the server says why", () => {
    expect(undoMode(view({ undo_ask: DRAW }), "p2")).toEqual({ kind: "ask", why: DRAW });
    const own = { settings: { undo_policy: "own" }, undo_by: "p1" };
    const why = "Players may only undo their own actions at this table: the last action was Alice's.";
    expect(undoMode(view({ ...own, undo_ask: why }), "p2")).toEqual({ kind: "ask", why });
  });
  it("stays refused when nobody could approve (the server sends no ask)", () => {
    const own = { settings: { undo_policy: "own" }, undo_by: "p1" };
    expect(undoMode(view(own), "p2").kind).toBe("refused");
  });
  it("a player who is out is refused, not asked to ask the table (the host still undoes)", () => {
    const out = (game: Record<string, unknown>) => view(game, { rules: { conceded: ["p2"], lost: {} } });
    const why = "You're out of this game (you conceded): you can watch and chat, but not move the game.";
    expect(undoMode(out({ undo_ask: DRAW }), "p2")).toEqual({ kind: "refused", why });
    expect(undoMode(out({}), "p2")).toEqual({ kind: "refused", why });
    expect(undoMode(out({ undo_ask: DRAW, undo_host: true }), "p2")).toEqual({ kind: "ask", why: DRAW });
    expect(undoMode(out({ undo_host: true }), "p2")).toEqual({ kind: "direct" });
    expect(undoMode(out({ undo_request: request({ by: "p1", by_name: "Alice" }) }), "p2").kind).toBe("waiting"); // what the table waits for still shows
  });
  it("waits while a request is on the table", () => {
    expect(undoMode(view({ undo_request: request() }), "p2")).toEqual({ kind: "waiting", why: "Your undo request is waiting for the table." });
    expect(undoMode(view({ undo_request: request(), undo_ask: DRAW }), "p1")).toEqual({ kind: "waiting", why: "Bob's undo request is waiting for the table." });
  });
});

describe("undoRequestSeat", () => {
  it("gives the voters still waiting Approve / Decline", () => {
    const seat = undoRequestSeat(view({ undo_request: request() }, { viewer: "p3" }), "p3");
    expect(seat).toEqual({ title: "Bob asks to undo: draw", why: DRAW, waiting: ["Cleo"], mustAnswer: true, mine: false });
    expect(undoRequestSeat(view({ undo_request: request() }, { viewer: "p1" }), "p1")?.mustAnswer).toBe(false); // approved already
  });
  it("shows the requester their request waiting, to withdraw", () => {
    expect(undoRequestSeat(view({ undo_request: request({ why: null, shown: null, label: "cast Sol Ring" }) }), "p2")).toEqual({
      title: "You asked to undo: cast Sol Ring", why: null, waiting: ["Cleo"], mustAnswer: false, mine: true,
    });
  });
  it("shows nothing to spectators, players out of the game, hot-seat tables or when nothing waits", () => {
    expect(undoRequestSeat(view({ undo_request: request() }, { viewer: "__spectator__" }), null)).toBeNull();
    expect(undoRequestSeat(view({ undo_request: request({ voters: ["p1"] }) }, { viewer: "p3" }), "p3")).toBeNull();
    expect(undoRequestSeat(view({ undo_request: request(), mode: "local" }), "p3")).toBeNull();
    expect(undoRequestSeat(view(), "p2")).toBeNull();
  });
});

describe("UndoRequestBar", () => {
  it("asks the voters, shows the requester it waiting, and shows nothing to a spectator", async () => {
    const { createElement } = await import("react");
    const { renderToStaticMarkup } = await import("react-dom/server");
    const { UndoRequestStrip } = await import("./UndoRequestBar");
    const render = (v: GameView, me: string | null = v.viewer) => renderToStaticMarkup(createElement(UndoRequestStrip, { view: v, me }));
    const voter = render(view({ undo_request: request() }, { viewer: "p3" }));
    expect(voter).toContain("Bob asks to undo: draw");
    expect(voter).toContain(DRAW);
    expect(voter).toContain('data-testid="undo-approve"');
    expect(voter).toContain('data-testid="undo-decline"');
    const mine = render(view({ undo_request: request() }));
    expect(mine).toContain("You asked to undo: draw");
    expect(mine).toContain("Waiting for Cleo");
    expect(mine).toContain('data-testid="undo-withdraw"');
    expect(mine).not.toContain("undo-approve");
    expect(render(view({ undo_request: request() }, { viewer: "__spectator__" }), null)).toBe("");
    expect(render(view())).toBe("");
  });
});

describe("Undo (button and Ctrl+Z)", () => {
  it("asks the table when the server says so, and undoes directly otherwise", async () => {
    const { useGame } = await import("../state/gameStore");
    const sent: unknown[] = [];
    const conn = { request: (m: unknown) => { sent.push(m); return Promise.resolve({}); } };
    useGame.setState({ conn: conn as never, actingAs: null, view: view({ id: "g1", undo_ask: DRAW }) });
    expect(await useGame.getState().undo()).toBe(false); // not undone yet
    expect(asked).toEqual([["g1", "request"]]);
    expect(sent).toEqual([]);
    useGame.setState({ view: view({ id: "g1", undo_request: request() }) });
    expect(await useGame.getState().undo()).toBe(false); // already waiting: nothing sent
    expect(asked).toHaveLength(1);
    useGame.setState({ view: view({ id: "g1" }) });
    expect(await useGame.getState().undo()).toBe(true);
    expect(sent).toEqual([{ type: "undo", as: undefined }]);
  });
});
