import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DecisionView, GameView } from "../../types/game";

const { state } = vi.hoisted(() => ({ state: { view: null as unknown, actingAs: null as string | null } }));
vi.mock("../../state/gameStore", async (original) => ({
  ...(await original<object>()),
  useGame: Object.assign(() => null, { getState: () => state }),
}));
vi.mock("../../components/Toasts", () => ({ toast: vi.fn() }));

import { toast } from "../../components/Toasts";
import { attackDrop, attackHint, cyclePlan, fronts, livePlan, planAll, reachableTargets, summaryLine, useAttackDraft } from "./attackDraft";

/** Alice declares: Alexios may attack only Carol, Khârn must attack (Bob or Carol), two Human tokens and a star-power creature anyone. */
const decision: DecisionView = {
  id: "d1", player: "p1", kind: "declare_attackers", prompt: "Declare attackers", source_id: null,
  options: [
    { id: "a:alexios", label: "Alexios, Deimos of Kosmos", card_id: "alexios" },
    { id: "a:kharn", label: "Khârn the Betrayer", card_id: "kharn" },
    { id: "a:h1", label: "Human", card_id: "h1" },
    { id: "a:h2", label: "Human", card_id: "h2" },
    { id: "a:star", label: "Nighthowler", card_id: "star" },
    { id: "t:p2", label: "Bob", card_id: null },
    { id: "t:p3", label: "Carol", card_id: null },
  ],
  min_choices: 0, max_choices: 5,
  display: {
    kind: "attackers",
    targets: { alexios: ["p3"], kharn: ["p2", "p3"], h1: ["p2", "p3"], h2: ["p2", "p3"], star: ["p2", "p3"] },
    must_attack: { kharn: ["p2", "p3"] },
    stats: { alexios: { pt: "4/4", keywords: ["trample"] }, kharn: { pt: "5/1", keywords: [] }, h1: { pt: "1/1", keywords: [] },
      h2: { pt: "1/1", keywords: [] }, star: { pt: "*/*", keywords: [] } },
  },
};

beforeEach(() => {
  state.view = { viewer: "p1", players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }, { id: "p3", name: "Carol", color: "#3a3" }],
    seat_order: ["p1", "p2", "p3"], game: { seats: {} }, cards: {}, rules: { decision } } as unknown as GameView;
  state.actingAs = null;
  useAttackDraft.setState({ decision: null, plan: {}, counts: {}, hint: null });
});

describe("attack with all (playtest nov 18)", () => {
  it("sends every creature that may attack a defender at it, and leaves the others alone", () => {
    expect(planAll(decision, { "a:kharn": "t:p2" }, "t:p2")).toEqual({ "a:kharn": "t:p2", "a:h1": "t:p2", "a:h2": "t:p2", "a:star": "t:p2" });
    expect(planAll(decision, {}, "t:p3")).toEqual({ "a:alexios": "t:p3", "a:kharn": "t:p3", "a:h1": "t:p3", "a:h2": "t:p3", "a:star": "t:p3" });
    expect(reachableTargets(decision).map((t) => t.id)).toEqual(["t:p2", "t:p3"]);
  });

  it("the A key cycles: all at Bob, all at Carol, then back to what must attack", () => {
    const one = cyclePlan(decision, { "a:kharn": "t:p2" });
    expect(one["a:h1"]).toBe("t:p2");
    const two = cyclePlan(decision, one);
    expect(Object.values(two).every((t) => t === "t:p3")).toBe(true);
    expect(cyclePlan(decision, two)).toEqual({ "a:kharn": "t:p2" });
  });

  it("sums power per defender (a */* creature makes it a lower bound)", () => {
    const plan = { "a:alexios": "t:p3", "a:kharn": "t:p2", "a:h1": "t:p2", "a:h2": "t:p2" };
    expect(summaryLine(fronts(decision, plan))).toBe("4 attacking · 3 (7 power) → Bob · 1 (4 power) → Carol");
    expect(summaryLine(fronts(decision, { "a:kharn": "t:p2", "a:star": "t:p2" }))).toBe("2 attacking · 5+ power → Bob");
    expect(summaryLine(fronts(decision, {}))).toBe("");
  });
});

describe("dragging a creature toward a defender", () => {
  it("assigns it, refuses one that can't attack there (by name), and a drop back home un-assigns", () => {
    expect(attackDrop(["h1", "alexios"], "p2")).toBe(true);
    expect(useAttackDraft.getState().plan).toEqual({ "a:kharn": "t:p2", "a:h1": "t:p2" });
    expect(toast).toHaveBeenCalledWith("Alexios, Deimos of Kosmos can't attack Bob", "info");
    expect(livePlan(state.view as GameView)).toEqual({ "a:kharn": "t:p2", "a:h1": "t:p2" });
    expect(attackDrop(["h1"], "home")).toBe(true);
    expect(useAttackDraft.getState().plan).toEqual({ "a:kharn": "t:p2" });
    expect(attackDrop(["h2"], "home")).toBe(false); // not attacking: a plain move in the row
  });

  it("leaves other drags alone: no decision, not my decision, or no attacker in the drag", () => {
    expect(attackDrop(["land"], "p2")).toBe(false);
    state.actingAs = "p2";
    (state.view as { viewer: string }).viewer = "p2";
    expect(attackDrop(["h1"], "p2")).toBe(false);
    expect(attackHint(["h1"], "p2")).toBeNull();
  });

  it("says what letting go does", () => {
    expect(attackHint(["h1"], "p3")).toEqual({ text: "Attack Carol", kind: "attack" });
    expect(attackHint(["alexios"], "p2")).toEqual({ text: "Can't attack Bob", kind: "refuse" });
    expect(attackHint(["h1", "h2", "alexios"], "p2")).toEqual({ text: "Attack Bob with 2", kind: "attack" });
  });
});
