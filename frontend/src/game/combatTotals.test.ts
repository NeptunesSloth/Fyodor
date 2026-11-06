import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../types/game";
import { attackerDamage, frontTotal, totalText } from "./combatTotals";

const goblin = (id: string, quantity = 1, power = "1"): GameCard => ({
  id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, card_id: null, name: "Goblin", face: 0, revealed: false, note: "",
  is_token: true, quantity, token: { name: "Goblin", power, toughness: "1", type_line: "Token Creature — Goblin" },
} as unknown as GameCard);

const bare = { cards: {} } as unknown as GameView;

describe("combat totals for attacking token stacks", () => {
  it("an unblocked stack deals its members × its power, the rules engine's power first", () => {
    const stack = goblin("s", 512);
    expect(attackerDamage(bare, stack)).toBe(512);
    const v = { rules: { stats: { s: { pt: [3, 1] } } } } as unknown as GameView;
    expect(attackerDamage(v, stack)).toBe(1536);
  });
  it("sums the unblocked attackers of a front; blocked ones deal nothing to it", () => {
    const t = frontTotal(bare, [
      { attacker: goblin("s", 400), blockers: [] },
      { attacker: goblin("one"), blockers: [goblin("b")] },
      { attacker: goblin("big", 1, "5"), blockers: [] },
    ]);
    expect(t).toEqual({ unblocked: 405, attackers: 402, partial: false, stacked: true });
    expect(totalText(t)).toBe("405 damage unblocked");
  });
  it("says 'at least' when a power is unknown, and marks a front without a stack", () => {
    const hidden = { id: "h", hidden: true, zone: "p1:battlefield", owner: "p1", controller: "p1" } as unknown as GameCard;
    const t = frontTotal(bare, [{ attacker: hidden, blockers: [] }, { attacker: goblin("g"), blockers: [] }]);
    expect(t.partial).toBe(true);
    expect(t.stacked).toBe(false);
    expect(totalText(t)).toBe("at least 1 damage unblocked");
  });
});
