import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DecisionView, GameView } from "../../types/game";
import { attackTargetsFor, initialAttackPlan, mustAttack } from "./attackPlan";
import { DecisionPanel } from "./RulesHud";

// Server rendering reads a zustand store's initial state, so the two stores the panel reads are plain values here.
const { state, fakeStore } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null }, prefs: { choiceWheel: true } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
}));
vi.mock("../../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));
vi.mock("../../state/prefs", async (original) => ({ ...(await original<object>()), usePrefs: fakeStore(() => state.prefs) }));

/** Alice's declaration in a three-player game: Alexios (Bob's, "can't attack its owner") may attack only Carol; Khârn ("attacks or blocks
 * each combat if able") must attack, Bob or Carol; the Bears may attack anyone. */
const declaration = (display: Record<string, unknown> | null = {
  kind: "attackers", banding: [], band_qualities: [],
  targets: { alexios: ["p3"], kharn: ["p2", "p3"], bears: ["p2", "p3"] },
  must_attack: { kharn: ["p2", "p3"] },
}): DecisionView => ({
  id: "d1", player: "p1", kind: "declare_attackers", prompt: "Declare attackers (or attack with nothing)", source_id: null,
  options: [
    { id: "a:alexios", label: "Alexios, Deimos of Kosmos", card_id: "alexios" },
    { id: "a:kharn", label: "Khârn the Betrayer", card_id: "kharn" },
    { id: "a:bears", label: "Grizzly Bears", card_id: "bears" },
    { id: "t:p2", label: "Bob", card_id: null },
    { id: "t:p3", label: "Carol", card_id: null },
  ],
  min_choices: 0, max_choices: 3, rememberable: false, cancelable: false,
  ...(display ? { display: display as DecisionView["display"] } : {}),
});

function show(decision: DecisionView): string {
  state.game.view = {
    viewer: "p1", seat_order: ["p1", "p2", "p3"], game: { mode: "lan", host_seat: "p1", seats: { p1: {}, p2: {}, p3: {} } },
    players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }, { id: "p3", name: "Carol", color: "#3a3" }],
    turn: { active_player: "p1" }, cards: {}, zones: {}, stack: [], log: [],
    rules: { decision, hints: {}, options: {}, prefs: null },
  } as unknown as GameView;
  return renderToStaticMarkup(createElement(DecisionPanel));
}

/** The <select> of one attacker, as rendered. */
const row = (html: string, card: string) => html.match(new RegExp(`<select[^>]*data-testid="attack-${card}"[^>]*>(.*?)</select>`))?.[0] ?? "";

describe("the declare-attackers decision offers what the server allows", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {} });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null });
    vi.stubGlobal("getComputedStyle", () => ({ zoom: "1" }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("offers each attacker only its own legal targets (508.1c: Alexios can't attack its owner)", () => {
    const d = declaration();
    expect(attackTargetsFor(d, "a:alexios").map((t) => t.id)).toEqual(["t:p3"]);
    expect(attackTargetsFor(d, "a:bears").map((t) => t.id)).toEqual(["t:p2", "t:p3"]);
    const html = show(d);
    expect(row(html, "alexios")).toContain(">Carol<");
    expect(row(html, "alexios")).not.toContain(">Bob<");
    expect(row(html, "bears")).toContain(">Bob<");
  });

  it("disables an attacker with no legal target", () => {
    const d = declaration({ kind: "attackers", targets: { alexios: [], kharn: ["p2"], bears: ["p2"] }, must_attack: {} });
    expect(attackTargetsFor(d, "a:alexios")).toEqual([]);
    expect(row(show(d), "alexios")).toContain("disabled");
  });

  it("names and pre-selects a creature that must attack, at its first best place (508.1d: Khârn)", () => {
    const d = declaration();
    expect(mustAttack(d, "a:kharn")).toBe(true);
    expect(mustAttack(d, "a:bears")).toBe(false);
    expect(initialAttackPlan(d)).toEqual({ "a:kharn": "t:p2" });
    const html = show(d);
    expect(html).toContain("Khârn the Betrayer<em class=\"combat-must\"> (must attack)</em>");
    expect(row(html, "kharn")).toMatch(/<option value="t:p2" selected="">Bob<\/option>/);
    expect(row(html, "bears")).toMatch(/<option value="" selected="">Doesn&#x27;t attack<\/option>/);
    expect(html).toContain("Attack with 1");
  });

  it("offers every target and pre-selects nothing when the decision has no guide (an older table)", () => {
    const d = declaration(null);
    expect(attackTargetsFor(d, "a:alexios").map((t) => t.id)).toEqual(["t:p2", "t:p3"]);
    expect(initialAttackPlan(d)).toEqual({});
    expect(show(d)).toContain("No attack");
  });
});
