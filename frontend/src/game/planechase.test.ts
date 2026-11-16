import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import type { CardData } from "../types/cards";
import { PlanechasePlaque } from "./PlanechasePlaque";
import type { GameView, PlanechaseView } from "../types/game";
import { canRollPlanar, costText, planarRotation, planechaseCue, splitPlaneText } from "./planechase";

const pc = (over: Partial<PlanechaseView> = {}): PlanechaseView => ({
  current: { printing_id: "a", name: "Llanowar", phenomenon: false },
  count: 10, visited: [], visited_count: 0, walks: 0, cost: 0, rolls: 0, last_roll: null, ...over,
});

describe("planechase", () => {
  it("splits a plane's text into its statics and its chaos ability", () => {
    expect(splitPlaneText('All creatures have "{T}: Add {G}{G}."\nWhenever chaos ensues, untap all creatures you control.')).toEqual({
      statics: ['All creatures have "{T}: Add {G}{G}."'], chaos: "Whenever chaos ensues, untap all creatures you control.",
    });
    expect(splitPlaneText("Whenever you roll {CHAOS}, draw a card.").chaos).toBe("Whenever you roll {CHAOS}, draw a card.");
    expect(splitPlaneText("When you encounter Planewide Disaster, destroy all creatures.")).toEqual({
      statics: ["When you encounter Planewide Disaster, destroy all creatures."], chaos: null,
    });
    expect(splitPlaneText(null)).toEqual({ statics: [], chaos: null });
  });

  it("shows the cost as mana and turns an upright scan to landscape", () => {
    expect(costText(0)).toBe("{0}");
    expect(costText(3)).toBe("{3}");
    expect(planarRotation(488, 680)).toBe(90);
    expect(planarRotation(680, 488)).toBe(0);
    expect(planarRotation(0, 0)).toBe(0);
  });

  it("cues a planeswalk, a chaos roll and a plain roll, and nothing on first sight", () => {
    const roll = (seq: number, face: "planeswalker" | "chaos" | "blank") => ({ player: "p1", face, cost: 0, seq });
    expect(planechaseCue(null, pc())).toBeNull();
    expect(planechaseCue(pc(), pc())).toBeNull();
    expect(planechaseCue(pc(), pc({ walks: 1, last_roll: roll(4, "planeswalker") }))).toEqual({ walk: true, chaos: false, rolled: "planeswalker" });
    expect(planechaseCue(pc({ last_roll: roll(4, "blank") }), pc({ last_roll: roll(6, "chaos") }))).toEqual({ walk: false, chaos: true, rolled: "chaos" });
    expect(planechaseCue(pc({ last_roll: roll(4, "blank") }), pc({ last_roll: roll(4, "blank") }))).toBeNull();
    expect(planechaseCue(pc({ walks: 2 }), pc({ walks: 3 }))).toEqual({ walk: true, chaos: false, rolled: null }); // "Done — planeswalk"
  });

  it("offers the die to the active player only, never on a phenomenon", () => {
    const view = (p: PlanechaseView | null) => ({ planechase: p, turn: { active_player: "p1" }, players: [{ id: "p1" }, { id: "p2" }] }) as unknown as GameView;
    expect(canRollPlanar(view(pc()), "p1")).toBe(true);
    expect(canRollPlanar(view(pc()), "p2")).toBe(false);
    expect(canRollPlanar(view(pc({ current: { printing_id: "x", name: "Chaotic Aether", phenomenon: true } })), "p1")).toBe(false);
    expect(canRollPlanar(view(null), "p1")).toBe(false);
  });
});

describe("the planechase plaque", () => {
  const render = (planechase: PlanechaseView | null, me = "p1", viewer = "p1") => {
    const view = { viewer, planechase, turn: { active_player: "p1" }, players: [{ id: "p1", name: "Alice", color: "#d4a852" }, { id: "p2", name: "Bob", color: "#5fa8d3" }] };
    // (a static render reads the stores' initial state)
    (useGame.getInitialState() as { view: unknown }).view = view;
    useCardCache.getInitialState().cards.a = { id: "a", name: "Llanowar", type_line: "Plane — Dominaria", oracle_text: "x", faces: [] } as unknown as CardData;
    useCardCache.getInitialState().cards.x = { id: "x", name: "Chaotic Aether", type_line: "Phenomenon", oracle_text: "y", faces: [] } as unknown as CardData;
    return renderToStaticMarkup(createElement(PlanechasePlaque, { me }));
  };

  it("shows the face-up plane, landscape, and the die with its cost to the active player only", () => {
    const html = render(pc({ cost: 2, last_roll: { player: "p1", face: "chaos", cost: 1, seq: 3 } }));
    expect(html).toContain("Llanowar");
    expect(html).toContain('data-testid="planar-roll"');
    expect(html).toContain("/api/images/a?face=0&amp;size=normal");
    expect(html).toContain("face-chaos");
    const theirs = render(pc({ cost: 1 }), "p2", "p2");
    expect(theirs).not.toContain('data-testid="planar-roll"');
    expect(theirs).toContain("Alice may roll");
    expect(render(pc(), "p1", "__spectator__")).not.toContain('data-testid="planar-roll"');
  });

  it("offers Done — planeswalk on a phenomenon, and is absent without a planar deck", () => {
    const html = render(pc({ current: { printing_id: "x", name: "Chaotic Aether", phenomenon: true } }), "p2", "p2");
    expect(html).toContain("Phenomenon");
    expect(html).toContain('data-testid="planar-done"');
    expect(html).not.toContain('data-testid="planar-roll"');
    expect(render(null)).toBe("");
  });
});
