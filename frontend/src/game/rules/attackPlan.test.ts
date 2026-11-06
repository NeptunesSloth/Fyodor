import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DecisionView, GameView } from "../../types/game";
import { attackDeclarations, attackingCount, attackTargetsFor, initialAttackPlan, mustAttack } from "./attackPlan";
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

describe("attacking with part of a token stack", () => {
  const plan = { "a:stack": "t:p2", "a:bear": "t:p3" };
  const sizes = { "a:stack": 512, "a:bear": 1 };
  it("a stack attacks with all its members unless a count names fewer (the server splits the rest off)", () => {
    expect(attackDeclarations(plan, {}, sizes)).toEqual([{ card_id: "stack", target: "p2" }, { card_id: "bear", target: "p3" }]);
    expect(attackDeclarations(plan, { "a:stack": 40 }, sizes)).toEqual([{ card_id: "stack", target: "p2", count: 40 }, { card_id: "bear", target: "p3" }]);
    expect(attackingCount(plan, {}, sizes)).toBe(513);
    expect(attackingCount(plan, { "a:stack": 40 }, sizes)).toBe(41);
  });
  it("a count of the whole stack, or nonsense, sends no count", () => {
    for (const k of [512, 600, 0, -3, Number.NaN]) {
      expect(attackDeclarations(plan, { "a:stack": k }, sizes)[0]).toEqual({ card_id: "stack", target: "p2" });
    }
    expect(attackDeclarations({ "a:bear": "t:p3" }, { "a:bear": 1 }, sizes)).toEqual([{ card_id: "bear", target: "p3" }]);
  });
  it("the declaration offers 'how many' for an attacking stack, and counts its members", () => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {} });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null });
    vi.stubGlobal("getComputedStyle", () => ({ zoom: "1" }));
    const d = declaration();
    show(d); // (sets the view)
    (state.game.view as GameView).cards = { kharn: { id: "kharn", quantity: 300 }, bears: { id: "bears" } } as unknown as GameView["cards"];
    const html = renderToStaticMarkup(createElement(DecisionPanel));
    vi.unstubAllGlobals();
    // Khârn must attack, so it is in the plan: as a ×300 stack it gets a count, all 300 by default; the Bears (not attacking yet) don't
    expect(html).toMatch(/data-testid="attack-count-kharn"[^>]*value="300"|value="300"[^>]*data-testid="attack-count-kharn"/);
    expect(html).toContain("of 300");
    expect(html).not.toContain("attack-count-bears");
    expect(html).toContain("Attack with 300");
  });
});
