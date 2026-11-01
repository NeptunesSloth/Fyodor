import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../types/game";
import { boardOf, focusStep } from "./focus2d";

const card = (id: string, zone: string): GameCard => ({ id, owner: "p1", controller: "p1", zone, face_down: false, hidden: true }) as GameCard;
const view: Pick<GameView, "cards"> = {
  cards: Object.fromEntries([card("bear", "p2:battlefield"), card("cmdr", "p3:command"), card("mine", "p1:battlefield"), card("held", "p1:hand"), card("bolt", "stack")].map((c) => [c.id, c])),
};

describe("2D focus (C)", () => {
  it("finds the board a card is drawn on: its battlefield or command zone, never a hand or the stack", () => {
    expect(boardOf(view, "bear")).toBe("p2");
    expect(boardOf(view, "cmdr")).toBe("p3");
    expect(boardOf(view, "held")).toBeNull();
    expect(boardOf(view, "bolt")).toBeNull();
    expect(boardOf(view, null)).toBeNull();
    expect(boardOf(view, "nope")).toBeNull();
  });
  it("looks at the hovered card's board, and C again returns to the board you were looking at", () => {
    const first = focusStep(view, "bear", null, null);
    expect(first).toEqual({ focus: "p2", open: { seat: "p2", back: null } });
    expect(focusStep(view, "mine", "p2", first!.open)).toEqual({ focus: null, open: null });
    expect(focusStep(view, "mine", "p3", null)).toEqual({ focus: "p1", open: { seat: "p1", back: "p3" } }); // your own board too
  });
  it("does nothing without a card on a board under the pointer", () => {
    expect(focusStep(view, "held", null, null)).toBeNull();
    expect(focusStep(view, null, "p2", null)).toBeNull();
  });
  it("a Look chosen since then starts a fresh focus instead of going back", () => {
    expect(focusStep(view, "cmdr", "p2", { seat: "p3", back: null })).toEqual({ focus: "p3", open: { seat: "p3", back: "p2" } });
  });
});
