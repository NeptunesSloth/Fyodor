import { describe, expect, it } from "vitest";
import { litCards, nextCombatFilter } from "./combatFilter";
import type { DecisionView, GameCard, GameView, HiddenCard, PhaseName, VisibleCard } from "../types/game";

const perm = (id: string, controller: string, type: string, extra: Partial<VisibleCard> = {}): VisibleCard => ({
  id, owner: controller, controller, zone: `${controller}:battlefield`, face_down: false, card_id: null, name: id, face: 0, revealed: false, note: "",
  is_token: true, token: { name: id, type_line: type, power: "1", toughness: "1" }, x: 0, y: 0, ...extra,
} as VisibleCard);

function viewOf(cards: GameCard[], phase: PhaseName = "main1", extra: { active?: string; decision?: DecisionView; sick?: string[]; stats?: Record<string, { creature?: boolean }> } = {}): GameView {
  const zones: Record<string, string[]> = { "p1:battlefield": [], "p2:battlefield": [], "p3:battlefield": [], "p1:graveyard": ["gy"] };
  for (const c of cards) zones[c.zone]!.push(c.id);
  return {
    cards: Object.fromEntries([...cards, perm("gy", "p1", "Creature — Bear", { zone: "p1:graveyard" })].map((c) => [c.id, c])),
    zones,
    seat_order: ["p1", "p2", "p3"],
    turn: { number: 3, active_player: extra.active ?? "p1", phase },
    rules: { decision: extra.decision ?? null, hints: { summoning_sick: extra.sick ?? [] }, stats: extra.stats ?? {} },
  } as unknown as GameView;
}

const sorted = (s: Set<string> | null) => (s ? [...s].sort() : s);

const board = [
  perm("bear", "p1", "Creature — Bear"),
  perm("tappedBear", "p1", "Creature — Bear", { tapped: true }),
  perm("newBear", "p1", "Creature — Bear"),
  perm("forest", "p1", "Basic Land — Forest"),
  perm("vehicle", "p1", "Artifact — Vehicle"),
  { id: "morph", owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: true, hidden: true } as HiddenCard,
  perm("wolf", "p2", "Creature — Wolf"),
  perm("tappedWolf", "p2", "Creature — Wolf", { tapped: true }),
  perm("ring", "p2", "Artifact"),
  perm("walker", "p2", "Legendary Planeswalker — Jace"),
  perm("cat", "p3", "Creature — Cat"),
];

describe("combat filter: which cards stay lit", () => {
  it("off lights everything", () => {
    expect(litCards(viewOf(board), "p1", "off")).toBeNull();
  });

  it("creatures only: creatures, crewed vehicles and face-down permanents; never other zones", () => {
    const lit = litCards(viewOf(board, "main1", { stats: { vehicle: { creature: true } } }), "p1", "creatures");
    expect(sorted(lit)).toEqual(["bear", "cat", "morph", "newBear", "tappedBear", "tappedWolf", "vehicle", "wolf"]);
  });

  it("can attack / block outside combat reads as creatures only", () => {
    expect(sorted(litCards(viewOf(board, "main2"), "p1", "combat"))).toEqual(sorted(litCards(viewOf(board, "main2"), "p1", "creatures")));
  });

  it("my declare attackers with automation: exactly the creatures the server offers", () => {
    const decision = { id: "d", player: "p1", kind: "declare_attackers", prompt: "", source_id: null,
      options: [{ id: "a:bear", label: "Bear", card_id: "bear" }, { id: "t:p2", label: "P2", card_id: null }] } as DecisionView;
    expect(sorted(litCards(viewOf(board, "declare_attackers", { decision }), "p1", "combat"))).toEqual(["bear"]);
  });

  it("declare attackers without a decision: the attacker's untapped creatures, less my summoning-sick ones", () => {
    expect(sorted(litCards(viewOf(board, "declare_attackers", { sick: ["newBear"] }), "p1", "combat"))).toEqual(["bear", "morph"]);
    // another player's attack: their sickness isn't in my view, so every untapped creature of theirs counts
    expect(sorted(litCards(viewOf(board, "declare_attackers", { active: "p2", sick: ["newBear"] }), "p1", "combat"))).toEqual(["wolf"]);
  });

  it("declare blockers: the defending players' untapped creatures, and what is already in the combat", () => {
    const attacked = board.map((c) => (c.id === "bear" ? { ...c, tapped: true, attacking: { kind: "player" as const, id: "p2" } } : c));
    expect(sorted(litCards(viewOf(attacked, "declare_blockers"), "p1", "combat"))).toEqual(["bear", "wolf"]);
    // attacking a planeswalker defends its controller
    const atWalker = board.map((c) => (c.id === "bear" ? { ...c, attacking: { kind: "card" as const, id: "walker" } } : c));
    expect(sorted(litCards(viewOf(atWalker, "declare_blockers"), "p1", "combat"))).toEqual(["bear", "wolf"]);
    // no attacker on record (manual play): every other player defends
    expect(sorted(litCards(viewOf(board, "declare_blockers"), "p1", "combat"))).toEqual(["cat", "wolf"]);
  });

  it("my declare blockers with automation: the blockers the server offers", () => {
    const decision = { id: "d", player: "p2", kind: "declare_blockers", prompt: "", source_id: null,
      options: [{ id: "b:wolf", label: "Wolf", card_id: "wolf" }, { id: "a:bear", label: "Bear", card_id: "bear" }] } as DecisionView;
    expect(sorted(litCards(viewOf(board, "declare_blockers", { decision }), "p2", "combat"))).toEqual(["wolf"]);
  });

  it("cycles off → creatures → can attack / block → off", () => {
    expect(nextCombatFilter("off")).toBe("creatures");
    expect(nextCombatFilter("creatures")).toBe("combat");
    expect(nextCombatFilter("combat")).toBe("off");
  });
});
