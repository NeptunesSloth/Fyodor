import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { undoActor, undoRefusal } from "./undoPolicy";

const view = (game: Record<string, unknown> = {}, over: Record<string, unknown> = {}): GameView =>
  ({
    viewer: "p2",
    seat_order: ["p1", "p2", "p3"],
    turn: { active_player: "p3" },
    players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }, { id: "p3", name: "Cleo" }],
    game: { mode: "lan", seats: { p1: {}, p2: {}, p3: {} }, settings: {}, can_undo: true, can_redo: true, ...game },
    ...over,
  }) as unknown as GameView;

describe("undoActor", () => {
  it("is the seat at a LAN table, nobody for a spectator", () => {
    expect(undoActor(view(), "p1")).toBe("p2");
    expect(undoActor(view({}, { viewer: "__spectator__" }), null)).toBeNull();
  });
  it("is the player acting at a hot-seat table (the active player by default)", () => {
    const open = view({ mode: "local" }, { viewer: "__omniscient__" });
    expect(undoActor(open, "p1")).toBe("p1");
    expect(undoActor(open, null)).toBe("p3");
  });
});

describe("undoRefusal", () => {
  it("never refuses under the default setting (old servers send no policy)", () => {
    expect(undoRefusal(view(), "p2")).toBeNull();
    expect(undoRefusal(view({ settings: { undo_policy: "everyone" } }), "p2", "redo")).toBeNull();
  });
  it("leaves host-only undo to the host", () => {
    const g = { settings: { undo_policy: "host" } };
    expect(undoRefusal(view(g), "p2")).toBe("Only the host may undo at this table (the host's undo setting).");
    expect(undoRefusal(view(g), "p2", "redo")).toMatch(/^Only the host may redo/);
    expect(undoRefusal(view({ ...g, undo_host: true }), "p2")).toBeNull();
  });
  it("lets a player take back only their own action, naming whose it is", () => {
    const g = { settings: { undo_policy: "own" }, undo_by: "p1", redo_by: "p2" };
    expect(undoRefusal(view(g), "p2")).toBe("Players may only undo their own actions at this table: the last action was Alice's.");
    expect(undoRefusal(view(g), "p2", "redo")).toBeNull();
    expect(undoRefusal(view(g), "p1", "redo")).toBe("Players may only redo their own actions at this table: the next action to redo was Bob's.");
    expect(undoRefusal(view({ ...g, undo_host: true }), "p2")).toMatch(/Alice's/); // no host exception
    expect(undoRefusal(view(g), "p2", "undo", "p2")).toBeNull(); // the action just sent is the sender's own
    expect(undoRefusal(view({ ...g, undo_by: "p9" }), "p2")).toMatch(/another player's\.$/);
  });
  it("explains that spectators can't undo", () => {
    expect(undoRefusal(view(), null)).toBe("Spectators can't undo.");
  });
});

describe("undoRefusal for a player who is out of the game (app/game/out_of_game.py history_refusal)", () => {
  const OUT = "You're out of this game (you conceded): you can watch and chat, but not move the game.";
  const out = (game: Record<string, unknown> = {}, viewer = "p2") =>
    view(game, { viewer, rules: { conceded: ["p2"], lost: { p3: "0 or less life" } } });
  it("refuses their undo and redo with the server's words, under every setting", () => {
    expect(undoRefusal(out(), "p2")).toBe(OUT);
    expect(undoRefusal(out(), "p2", "redo")).toBe(OUT);
    expect(undoRefusal(out({ settings: { undo_policy: "own" }, undo_by: "p2" }), "p2", "undo", "p2")).toBe(OUT); // even their own action
    expect(undoRefusal(out({}, "p3"), "p3")).toBe(OUT.replace("conceded", "lost"));
  });
  it("lets the host take a concession back, and the players still in undo as before", () => {
    expect(undoRefusal(out({ undo_host: true }), "p2")).toBeNull();
    expect(undoRefusal(out({ undo_host: true }), "p2", "redo")).toBeNull();
    expect(undoRefusal(out({}, "p1"), "p1")).toBeNull();
    expect(undoRefusal(out({ mode: "local", undo_host: true }, "__omniscient__"), "p2")).toBeNull(); // a hot-seat table: everyone is at the host computer
  });
});
