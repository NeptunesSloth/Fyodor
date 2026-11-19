import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { handoffTarget } from "./HotSeatCover";

const players = [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }, { id: "p3", name: "Bot", bot: "simple" }, { id: "p4", name: "Dummy", dummy: true }];
const view = (over: Record<string, unknown>): GameView =>
  ({ viewer: "p1", game: { mode: "local" }, players, turn: { active_player: "p1" }, rules: { priority: "p2", decision: null, conceded: [], lost: {} },
     ...over }) as unknown as GameView;

describe("handoffTarget", () => {
  it("hands the screen to the other local player the table waits on", () => {
    expect(handoffTarget(view({}))).toBe("p2");
    expect(handoffTarget(view({ rules: { priority: "p1", decision: { player: "p2" }, conceded: [], lost: {} } }))).toBe("p2");
  });
  it("stays put when it waits on the player shown, a bot or a dummy", () => {
    expect(handoffTarget(view({ viewer: "p2" }))).toBeNull();
    expect(handoffTarget(view({ rules: { priority: "p3", decision: null, conceded: [], lost: {} } }))).toBeNull();
    expect(handoffTarget(view({ rules: { priority: "p4", decision: null, conceded: [], lost: {} } }))).toBeNull();
  });
  it("never at a LAN table, with one person at this computer, or from the open table", () => {
    expect(handoffTarget(view({ game: { mode: "lan" } }))).toBeNull();
    expect(handoffTarget(view({ players: players.filter((p) => p.id !== "p2") }))).toBeNull();
    expect(handoffTarget(view({ viewer: "__omniscient__" }))).toBeNull();
    expect(handoffTarget(view({ rules: { priority: "p2", decision: null, conceded: ["p2"], lost: {} } }))).toBeNull();
  });
});
