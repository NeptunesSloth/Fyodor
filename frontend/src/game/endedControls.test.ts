import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { GameView } from "../types/game";
import { RulesStack, TurnDial } from "./rules/RulesHud";
import { barMoment } from "./Hud";
import { gameEnded } from "./nightEnding";

// -- playtest (nov 16) -- the table's live controls once the game is over, and the card action bar's moment
const { state, fakeStore } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null, selection: [] as string[] } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
}));
vi.mock("../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));

function table(rules: Record<string, unknown>, night: unknown = null): GameView {
  return {
    viewer: "p1", seat_order: ["p1", "p2"], game: { id: "g1", mode: "local", host_seat: "p1", seats: { p1: {}, p2: {} }, night: { number: 1, result: night } },
    players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }],
    turn: { number: 4, active_player: "p1", phase: "main1" }, zones: { stack: ["t1"] }, stack: ["t1"], log: [],
    cards: { t1: { id: "t1", name: "Exquisite Blood", zone: "stack", owner: "p1", controller: "p1", card_id: null, ability: { kind: "triggered", text: "Exquisite Blood's ability", source: null } } },
    rules: { paused: false, conceded: [], lost: {}, winner: null, priority: "p1", decision: null, controlled_by: null, acting_as: null, prefs: null, hints: {}, options: {}, stack: {}, ...rules },
  } as unknown as GameView;
}

describe("after the game is over (Sanguine Bond won it with a trigger still on the stack)", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {}, setTimeout, clearTimeout });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null, body: { classList: { contains: () => false } } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("the stack keeps its record but offers no Respond and no Stop after", () => {
    state.game.view = table({});
    const live = renderToStaticMarkup(createElement(RulesStack));
    expect(live).toContain('data-testid="stack-respond"');
    expect(live).toContain("Stop after");
    state.game.view = table({ winner: "p1", lost: { p2: "0 or less life" } });
    const over = renderToStaticMarkup(createElement(RulesStack));
    expect(over).toContain("Exquisite Blood");
    expect(over).not.toContain('data-testid="stack-respond"');
    expect(over).not.toContain("Stop after");
    expect(over).toContain("The game is over");
  });

  it("the turn dial offers no Resolve over a result waiting to be confirmed", () => {
    state.game.view = table({});
    expect(renderToStaticMarkup(createElement(TurnDial))).toContain('data-testid="pass-priority"');
    state.game.view = table({ winner: "p1", lost: { p2: "0 or less life" } });
    const over = renderToStaticMarkup(createElement(TurnDial));
    expect(over).not.toContain('data-testid="pass-priority"');
    expect(over).not.toContain('data-testid="resolve-all"');
    expect(over).toContain("The game is over");
  });

  it("knows the game is over by the rules, by the night's result, or by this seat's test ending", () => {
    expect(gameEnded(table({}), "p1")).toBe(false);
    expect(gameEnded(table({ winner: "p2" }), "p1")).toBe(true);
    expect(gameEnded(table({ draw_reason: "A loop" }), "p1")).toBe(true);
    expect(gameEnded(table({}, { winner: "p1" }), "p1")).toBe(true);
    const bot = table({ lost: { p1: "0 or less life" } });
    bot.players[1] = { ...bot.players[1]!, bot: true } as never;
    expect(gameEnded(bot, "p1")).toBe(true); // (the Defeat strip of a game against the test opponent)
  });

  it("the action bar's moment changes with the stack and with the decision", () => {
    const a = table({});
    const b = { ...a, stack: ["t1", "t2"] } as GameView;
    const c = { ...a, rules: { ...a.rules!, decision: { id: "d1" } } } as unknown as GameView;
    expect(barMoment(a)).toBe(barMoment({ ...a } as GameView));
    expect(new Set([barMoment(a), barMoment(b), barMoment(c)]).size).toBe(3);
  });
});
