import { describe, expect, it, vi } from "vitest";
import type { GameView } from "../types/game";
import { OWN_RUN, ownTriggerRun, resolveVerb } from "./rules/resolveRun";

// -- I have a response -- / -- smart resolve -- the pure parts (the server decides: backend/tests/test_response_call.py and
// test_rules_smart_resolve.py)
const { state } = vi.hoisted(() => ({ state: { resolving: null as unknown } }));
vi.mock("../state/gameStore", async (original) => ({
  ...(await original<object>()),
  useGame: Object.assign(() => null, { getState: () => ({ resolving: state.resolving }) }),
}));

const trig = (id: string, controller: string) =>
  ({ id, name: "Omnath", zone: "stack", owner: controller, controller, card_id: null, ability: { kind: "triggered", text: "landfall", source_id: null, source_card_id: null, source_name: "Omnath" } });
const spell = (id: string, controller: string) => ({ id, name: "Lightning Bolt", zone: "stack", owner: controller, controller, card_id: "c" });

function table(stack: Record<string, unknown>[], rules: Record<string, unknown> = {}): GameView {
  return {
    viewer: "p1", seat_order: ["p1", "p2"], game: { id: "g1", mode: "lan", host_seat: "p1", seats: {}, night: { number: 1, result: null } },
    players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }],
    turn: { number: 4, active_player: "p1", phase: "main1" }, stack: stack.map((c) => c.id), log: [],
    cards: Object.fromEntries(stack.map((c) => [c.id, c])),
    rules: { paused: false, conceded: [], lost: {}, winner: null, priority: "p1", decision: null, controlled_by: null, acting_as: null, prefs: null, hints: {}, ...rules },
  } as unknown as GameView;
}

describe("smart resolve", () => {
  it("counts my own triggers from the top, stopping at a spell or someone else's object", () => {
    expect(ownTriggerRun(table([spell("s", "p1"), trig("a", "p1"), trig("b", "p1")]), "p1")).toBe(2);
    expect(ownTriggerRun(table([trig("a", "p1"), trig("b", "p2")]), "p1")).toBe(0);
    expect(resolveVerb(table([trig("a", "p1"), trig("b", "p1"), trig("c", "p1")]), "p1")).toBe("Resolve 3 triggers");
    expect(resolveVerb(table([trig("a", "p1")]), "p1")).toBe("Resolve");
    expect(resolveVerb(table([spell("s", "p1")]), "p1")).toBe("Resolve");
    const many = Array.from({ length: OWN_RUN + 5 }, (_, i) => trig(`t${i}`, "p1"));
    expect(resolveVerb(table(many), "p1")).toBe(`Resolve ${OWN_RUN}+ triggers`);
  });
});

describe("I have a response", () => {
  it("is offered to a player in the game who doesn't hold priority, never to the holder or someone out", async () => {
    const { canCallResponse, holdWhen } = await import("./ResponseCall");
    const view = table([spell("s", "p2")], { priority: "p2" });
    expect(canCallResponse(view, "p1")).toBe(true);
    expect(canCallResponse(view, "p2")).toBe(false); // (it's theirs to act)
    expect(canCallResponse(table([], { priority: "p2", conceded: ["p1"] }), "p1")).toBe(false);
    expect(canCallResponse(table([], { priority: "p2", paused: true }), "p1")).toBe(false);
    expect(canCallResponse({ ...view, viewer: "__spectator__" } as GameView, "p1")).toBe(false);
    expect(canCallResponse(table([], { priority: "p2", decision: { player: "p1", kind: "choose_one" } }), "p1")).toBe(false); // (my own choice)
    expect(holdWhen(view)).toBe("before Lightning Bolt resolves");
    expect(holdWhen(table([]))).toBe("before this step ends");
    state.resolving = { resolved: 3, left: 40, by: "p1" }; // (a long chain of my own: nobody holds priority while it resolves)
    expect(canCallResponse(table([], { priority: "p1" }), "p1")).toBe(true);
    state.resolving = null;
  });
});
