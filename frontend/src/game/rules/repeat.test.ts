import { describe, expect, it } from "vitest";
import { defaultStart, repeatAction } from "./RepeatPanel";

describe("Repeat panel", () => {
  it("guesses the loop: a block done twice, else the newest action with its answers", () => {
    expect(defaultStart(["Pass priority", "Activate Fountain", "Activate Well", "Choose: Pay {1}", "Activate Fountain", "Activate Well", "Choose: Pay {1}"])).toBe(4);
    expect(defaultStart(["Pass priority", "Activate Fountain", "Activate Well", "Choose: Pay {1}"])).toBe(2);
    expect(defaultStart(["Pass priority"])).toBe(0);
  });
  it("never starts a loop on an answer", () => {
    expect(defaultStart(["Activate Scepter", "Choose: Yes", "Choose: Yes"])).toBe(0);
  });
  it("sends the actions from the start to the newest, the times clamped, and the target", () => {
    expect(repeatAction(4, 1, 10, { kind: "none", value: 0 })).toEqual({ type: "repeat_sequence", count: 3, times: 10 });
    expect(repeatAction(4, 3, 9999, { kind: "none", value: 0 })).toEqual({ type: "repeat_sequence", count: 1, times: 500 });
    expect(repeatAction(4, 2, 500, { kind: "life_at_most", value: 0, player: "p2" }))
      .toEqual({ type: "repeat_sequence", count: 2, times: 500, until: { kind: "life_at_most", value: 0, player: "p2" } });
  });
});
