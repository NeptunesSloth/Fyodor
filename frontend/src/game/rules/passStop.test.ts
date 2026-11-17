import { beforeEach, describe, expect, it } from "vitest";
import type { GameView } from "../../types/game";
import { drewStop, drewText, loopNote, logText, usePassStop } from "./passStop";

// -- playtest (nov 16) -- why Resolve all stopped (Shabraz + Marina Vendrell's Grimoire), said by the pass controls
const LOOP = "This keeps repeating: 20 objects resolved in a row (Alice drew 10). Automatic passing stopped so you can respond.";
function table(o: { hand?: string[]; library?: string[]; stack?: string[]; log?: string[]; castable?: string[]; pass_until?: string | null; priority?: string; decision?: unknown } = {}): GameView {
  const cards: Record<string, unknown> = {};
  for (const id of [...(o.hand ?? []), ...(o.library ?? [])]) {
    cards[id] = { id, name: id === "bolt" ? "Lightning Bolt" : id === "bs" ? "Brainstorm" : "Island", zone: o.hand?.includes(id) ? "p1:hand" : "p1:library", owner: "p1", controller: "p1" };
  }
  return {
    viewer: "p1", game: { id: "g" }, turn: { number: 3, phase: "main1", active_player: "p1" }, searches: {}, my_views: [],
    zones: { "p1:hand": o.hand ?? [], "p1:library": { count: 30, known: [] } },
    stack: o.stack ?? ["s1"], cards,
    log: (o.log ?? []).map((t, i) => ({ seq: i + 1, parts: [{ t }] })),
    rules: { paused: false, priority: o.priority ?? "p1", decision: o.decision ?? null, prefs: { pass_until: o.pass_until ?? null }, hints: { has_priority: true, castable: o.castable ?? [] } },
  } as unknown as GameView;
}

describe("why automatic passing stopped", () => {
  beforeEach(() => usePassStop.setState({ armed: null, stop: null }));

  it("reads a log line's words, cards included", () => {
    expect(logText({ parts: [{ t: "Resolved " }, { card: { name: "Opt", card_id: null } }] })).toBe("Resolved Opt");
  });

  it("finds the loop-pause line that arrived with the new view, whole", () => {
    const before = table({ log: ["Alice cast Opt"] });
    const after = table({ log: ["Alice cast Opt", "Alice drew a card", LOOP] });
    expect(loopNote(before, after)).toBe(LOOP);
    expect(loopNote(after, after)).toBeNull(); // (already seen)
    expect(loopNote(before, table({ log: ["Alice cast Opt", "Alice drew a card"] }))).toBeNull();
  });

  it("Resolve all stopped on a card I drew and can cast now: names it", () => {
    expect(drewStop(table({ hand: ["bolt", "isl"], castable: ["bolt"] }), "p1", ["bolt", "isl"])).toEqual(["Lightning Bolt"]);
    expect(drewText(["Lightning Bolt"])).toBe("Stopped: you drew Lightning Bolt and can cast it now.");
    // not that: it is still passing, the stack emptied, a decision is open, or nothing drawn is castable
    expect(drewStop(table({ hand: ["bolt"], castable: ["bolt"], pass_until: "stack_empty" }), "p1", ["bolt"])).toBeNull();
    expect(drewStop(table({ hand: ["bolt"], castable: ["bolt"], stack: [] }), "p1", ["bolt"])).toBeNull();
    expect(drewStop(table({ hand: ["bolt"], castable: ["bolt"], decision: { id: "d" } }), "p1", ["bolt"])).toBeNull();
    expect(drewStop(table({ hand: ["bolt", "isl"], castable: [] }), "p1", ["bolt", "isl"])).toBeNull();
  });

  it("the store: armed by Resolve all, it explains the stop once, and the banner goes when the stack moves on", () => {
    const s = usePassStop.getState();
    const before = table({ hand: [], library: ["bolt", "isl"] });
    s.arm();
    const stopped = table({ hand: ["isl", "bolt"], castable: ["bolt"], log: [] });
    usePassStop.getState().update(before, stopped, "p1");
    expect(usePassStop.getState().stop).toMatchObject({ kind: "drew", text: "Stopped: you drew Lightning Bolt and can cast it now." });
    expect(usePassStop.getState().armed).toBeNull();
    usePassStop.getState().update(stopped, { ...stopped, stack: [] } as GameView, "p1");
    expect(usePassStop.getState().stop).toBeNull();
  });

  it("a loop pause shows without Resolve all (the engine's own step budget), and a finished Resolve all says nothing", () => {
    const before = table({ log: ["x"] });
    usePassStop.getState().update(before, table({ log: ["x", LOOP] }), "p1");
    expect(usePassStop.getState().stop).toMatchObject({ kind: "loop", text: LOOP });
    usePassStop.setState({ stop: null });
    usePassStop.getState().arm();
    usePassStop.getState().update(before, table({ log: ["x"], stack: [] }), "p1");
    expect(usePassStop.getState()).toMatchObject({ stop: null, armed: null });
  });
});

describe("the Hold priority hint (playtest nov 16: Opt resolved before I could respond to it)", () => {
  const at = (log: [number, string][], rules: Record<string, unknown>, stack: string[] = []) => ({
    game: { id: "g" }, stack, log: log.map(([seq, t]) => ({ seq, actor: "p1", kind: "action", parts: [{ t }] })),
    rules: { paused: false, priority: "p2", decision: null, prefs: { response: "auto", hold_priority: false, full_control: false }, ...rules },
  }) as unknown as GameView;
  it("fires when my own cast went by without my priority over it, with responses on Auto and Hold priority off", async () => {
    const { autoPassedMyCast } = await import("./passStop");
    const before = at([[1, "x"]], {});
    expect(autoPassedMyCast(before, at([[1, "x"], [2, "Alice cast Opt"]], { decision: { id: "scry" }, priority: "p1" }, ["opt"]), "p1")).toBe(true);
    expect(autoPassedMyCast(before, at([[1, "x"], [2, "Alice cast Opt"]], { priority: "p1" }, ["opt"]), "p1")).toBe(false); // (I hold priority over it)
    const held = at([[1, "x"], [2, "Alice cast Opt"]], { prefs: { response: "auto", hold_priority: true } });
    expect(autoPassedMyCast(before, held, "p1")).toBe(false);
    expect(autoPassedMyCast(before, at([[1, "x"], [2, "Alice played Island"]], {}), "p1")).toBe(false);
  });
});

describe("an extra turn is marked (playtest nov 16)", () => {
  it("reads the engine's line for the active player, this turn only", async () => {
    const { extraTurn } = await import("./passStop");
    const v = (active: string, number: number, lines: [number, string][]) => ({
      players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }], turn: { number, active_player: active },
      log: lines.map(([turn, t], i) => ({ seq: i, turn, parts: [{ t }] })),
    }) as unknown as GameView;
    const lines: [number, string][] = [[3, "Alice cast Final Fortune"], [3, "Alice takes an extra turn (Final Fortune, 500.7)"]];
    expect(extraTurn(v("p1", 4, lines))).toBe("Final Fortune");
    expect(extraTurn(v("p2", 5, [...lines, [4, "Alice passed"]]))).toBeNull(); // the next turn is a normal one
    expect(extraTurn(v("p1", 4, [[3, "Alice cast Opt"]]))).toBeNull();
  });
});
