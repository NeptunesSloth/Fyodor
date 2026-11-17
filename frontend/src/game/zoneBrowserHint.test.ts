import { describe, expect, it } from "vitest";
import type { GameCard } from "../types/game";
import { browserHint, commanderHere } from "./ZoneBrowser";

describe("the zone browser's hint says what a double-click does (playtest nov 17: \"put into hand\" over a commander at Full)", () => {
  it("my command zone: casting the commander, worded for the automation level", () => {
    const full = browserHint({ myHand: false, castHere: false, command: true, automation: true });
    const off = browserHint({ myHand: false, castHere: false, command: true, automation: false });
    expect(full).toContain("cast it");
    expect(off).toContain("on the stack");
    for (const h of [full, off]) expect(h).not.toContain("into hand");
  });

  it("other piles keep their hints", () => {
    expect(browserHint({ myHand: false, castHere: false, command: false, automation: true })).toContain("double-click to put into hand");
    expect(browserHint({ myHand: true, castHere: false, command: false, automation: true })).toContain("double-click or Enter plays it");
  });

  it("only my own commander in my own command zone counts", () => {
    const card = { id: "c", zone: "p1:command", commander_key: "k", name: "Ghalta" } as unknown as GameCard;
    expect(commanderHere(card, "p1")).toBe(true);
    expect(commanderHere(card, "p2")).toBe(false);
    expect(commanderHere({ ...card, commander_key: undefined } as GameCard, "p1")).toBe(false);
  });
});
