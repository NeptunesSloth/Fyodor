import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../../types/game";
import { abilityRow } from "./rulesMenu";

const view = (priority: boolean, phase = "main1", active = "p1") =>
  ({ rules: { hints: { has_priority: priority } }, zones: { stack: [] }, turn: { number: 1, active_player: active, phase } }) as unknown as GameView;
const card = (tapped = false) => ({ id: "c1", controller: "p1", tapped }) as unknown as GameCard;

describe("abilityRow", () => {
  it("splits cost and effect and keeps the whole effect", () => {
    const line = "{2}{R}{R}{G}{G}: Transform Bruce Banner. Activate only as a sorcery.";
    expect(abilityRow(line, card(), view(true), true)).toEqual({ cost: "{2}{R}{R}{G}{G}", effect: "Transform Bruce Banner. Activate only as a sorcery." });
  });
  it("says why it is greyed out", () => {
    const draw = "{X}{X}, {T}: Draw X cards. Activate only as a sorcery.";
    expect(abilityRow(draw, card(), view(false), false).why).toBe("Wait for priority");
    expect(abilityRow(draw, card(true), view(true), false).why).toBe("Already tapped");
    expect(abilityRow(draw, card(), view(true, "upkeep"), false).why).toMatch(/^Sorcery speed/);
    expect(abilityRow("{1}: Scry 1.", card(), view(true), false).why).toMatch(/pay the cost/);
  });
});
