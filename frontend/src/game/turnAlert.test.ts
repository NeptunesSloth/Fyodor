import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { waitReason } from "./turnAlert";

const view = (over: Record<string, unknown>): GameView =>
  ({ viewer: "p1", game: { mode: "lan" }, turn: { active_player: "p2" }, rules: null, response: null, ...over }) as unknown as GameView;

describe("waitReason", () => {
  it("is my turn when I'm the active player and nothing else waits", () =>
    expect(waitReason(view({ turn: { active_player: "p1" } }), "p1")).toBe("Your turn"));
  it("is quiet when the table waits on someone else", () => expect(waitReason(view({}), "p1")).toBeNull());
  it("names a decision, a response and priority", () => {
    expect(waitReason(view({ rules: { decision: { player: "p1" } } }), "p1")).toBe("Your decision");
    expect(waitReason(view({ response: { waiting: ["p3", "p1"] } }), "p1")).toBe("Your response");
    expect(waitReason(view({ rules: { priority: "p1" } }), "p1")).toBe("Your priority");
  });
  it("never alerts at a hot-seat table or a spectator", () => {
    expect(waitReason(view({ game: { mode: "local" }, turn: { active_player: "p1" } }), "p1")).toBeNull();
    expect(waitReason(view({ viewer: "__spectator__", turn: { active_player: "p1" } }), "p1")).toBeNull();
  });
});
