import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { GameView } from "../../types/game";
import { TurnDial } from "./RulesHud";

// Server rendering reads a zustand store's initial state, so the store the dial reads is a plain value here (as wheelPanel.test.ts).
const { state, fakeStore } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
}));
vi.mock("../../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));

function dial(viewer: string, rules: Record<string, unknown> | null, mode: "lan" | "local" = "lan"): string {
  state.game.view = {
    viewer, seat_order: ["p1", "p2", "p3"], game: { id: "g1", mode, host_seat: "p1", seats: { p1: {}, p2: {}, p3: {} }, night: { number: 1, result: null } },
    players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }, { id: "p3", name: "Carol", color: "#3a3" }],
    turn: { number: 4, active_player: "p1", phase: "main1" }, cards: {}, zones: {}, stack: [], log: [],
    rules: rules && { paused: false, conceded: [], lost: {}, priority: "p1", decision: null, controlled_by: null, acting_as: null, prefs: null, hints: {}, options: {}, ...rules },
  } as unknown as GameView;
  return renderToStaticMarkup(createElement(TurnDial));
}

describe("the turn dial for a player who is out of the game", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {}, setTimeout, clearTimeout });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null, body: { classList: { contains: () => false } } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("a player who conceded watches: no steps, no turn, no stack controls", () => {
    const html = dial("p3", { conceded: ["p3"] });
    expect(html).toContain("You&#x27;re out: watching");
    expect(html).toContain('data-testid="turn-dial-out"');
    expect(html).not.toContain("Manual play");
    for (const control of ["Next turn", "To combat", "Previous step", "Resolve top", 'data-testid="pass-priority"', "Hold priority"]) expect(html).not.toContain(control);
    expect(html).toMatch(/data-testid="current-phase"[^>]*disabled/); // the step menu is shut too
    expect(html).toContain("Turn 4 · Alice"); // still shows whose turn and which step
  });

  it("a player who lost watches the same way, with the rules paused or not", () => {
    for (const paused of [false, true]) {
      const html = dial("p2", { lost: { p2: "0 or less life" }, paused });
      expect(html).toContain("You&#x27;re out: watching");
      expect(html).not.toContain("Next turn");
    }
  });

  it("the players still in keep their controls: the rules engine's pass, or the manual steps while it is paused", () => {
    expect(dial("p1", { conceded: ["p3"] })).toContain('data-testid="pass-priority"');
    const paused = dial("p2", { conceded: ["p3"], paused: true });
    expect(paused).toContain("Automation paused: move the steps yourself");
    expect(paused).toContain("Next turn");
  });

  it("a table without the rules engine keeps its manual dial; a spectator just watches", () => {
    const manual = dial("p3", null);
    expect(manual).toContain("Manual play: you move the steps");
    expect(manual).toContain("To combat");
    const spectator = dial("__spectator__", { conceded: ["p3"] });
    expect(spectator).toContain(">Watching<");
    expect(spectator).not.toContain("Next turn");
  });
});

describe("the untap step (playtest nov 16: a new game opened there saying \"Your priority\")", () => {
  it("says nobody has priority yet (502.4), and the pass button still moves on", async () => {
    const { dialState } = await import("./RulesHud");
    const v = { viewer: "p1", turn: { number: 1, active_player: "p1", phase: "untap" }, stack: [],
      rules: { paused: false, conceded: [], lost: {}, priority: "p1", decision: null, controlled_by: null, acting_as: null } } as unknown as GameView;
    expect(dialState(v, "p1")).toMatchObject({ mine: true, status: "Untap step: no priority yet" });
    expect(dialState({ ...v, turn: { ...v.turn, phase: "upkeep" } } as GameView, "p1").status).toBe("Your priority");
  });
});
