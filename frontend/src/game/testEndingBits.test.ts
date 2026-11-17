import { describe, expect, it } from "vitest";
import type { GameView, LogEntryView } from "../types/game";
import { ENDING_WORD, causeLine, endingVariant, lifeTick, lossSource, otherLine, tickAt } from "./testEndingBits";

const line = (turn: number, ...parts: LogEntryView["parts"]): LogEntryView =>
  ({ seq: 0, ts: 0, turn, phase: "end", actor: null, kind: "rules", parts }) as LogEntryView;
const t = (s: string) => ({ t: s });
const c = (name: string, card_id: string | null = `id-${name}`) => ({ card: { name, card_id } });

describe("the test-table ending screen", () => {
  it("picks the variant and its word", () => {
    expect(endingVariant("lost")).toBe("defeat");
    expect(endingVariant("won")).toBe("victory");
    expect(endingVariant("draw")).toBe("draw");
    expect(ENDING_WORD.defeat).toBe("Defeat");
  });

  it("puts the rules' loss reason in words", () => {
    expect(causeLine("0 or less life")).toBe("Your life fell to 0.");
    expect(causeLine("10 poison counters")).toBe("You were poisoned: 10 poison counters.");
    expect(causeLine("21 combat damage from one commander")).toBe("You took 21 combat damage from one commander.");
    expect(causeLine("drew from an empty library")).toBe("You drew from an empty library.");
    expect(causeLine("an effect")).toBe("An effect made you lose the game.");
    expect(causeLine("Bob won the game")).toBe("Bob won the game.");
    expect(causeLine(undefined)).toBe("You lost the game.");
    expect(causeLine("0 or less life", true)).toBe("You conceded the game.");
  });

  it("names the card the log shows just before the loss, in that turn only", () => {
    const log = [
      line(4, c("Grizzly Bears"), t(" attacks Alice")),
      line(5, c("Final Fortune"), t("'s ability resolves")),
      line(5, t("Alice loses the game (an effect)")),
    ];
    expect(lossSource(log, "Alice")).toEqual({ name: "Final Fortune", card_id: "id-Final Fortune" });
    expect(lossSource([line(4, c("Grizzly Bears")), line(5, t("Alice loses the game (0 or less life)"))], "Alice")).toBeNull();
    expect(lossSource([line(5, c("Lightning Bolt"))], "Alice")).toBeNull(); // (no loss in the log)
    const far = [line(5, c("Sol Ring")), ...Array.from({ length: 8 }, () => line(5, t("…"))), line(5, t("Alice loses the game"))];
    expect(lossSource(far, "Alice")).toBeNull();
  });

  it("ticks the life from where the last turn's changes began to where it ended", () => {
    expect(lifeTick({ life: 0, life_history: [{ turn: 3, before: 40, after: 35 }, { turn: 5, before: 35, after: 12 }, { turn: 5, before: 12, after: 0 }] }))
      .toEqual({ from: 35, to: 0 });
    expect(lifeTick({ life: 40, life_history: [] })).toEqual({ from: 40, to: 40 });
    expect(lifeTick(undefined)).toEqual({ from: 0, to: 0 });
    expect([0, 0.5, 1, 2].map((k) => tickAt(35, 0, k))).toEqual([35, 4, 0, 0]);
  });

  it("says what the victory and the draw were", () => {
    const view = (dummies: string[], rules: Record<string, unknown> = {}) =>
      ({ players: dummies.map((name, i) => ({ id: `p${i + 2}`, name, dummy: true })), rules }) as unknown as GameView;
    expect(otherLine(view(["Wall"]), "victory")).toBe("Wall is out.");
    expect(otherLine(view(["A", "B"]), "victory")).toBe("Every target dummy is out (2).");
    expect(otherLine(view(["A"], { draw_reason: "Everyone lost at once" }), "draw")).toBe("Everyone lost at once.");
  });
});
