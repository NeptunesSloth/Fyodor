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
