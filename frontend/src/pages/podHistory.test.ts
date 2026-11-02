import { describe, expect, it } from "vitest";
import type { EliminationEntry, FinalBoardSeat } from "../services/pod";
import { boardLines, eliminationLines, howText, ordinal } from "./podHistory";

const out = (name: string, place: number, how: string, turn: number | null = 7, reason = ""): EliminationEntry =>
  ({ seat: name.toLowerCase(), name, place, turn, how, reason });

describe("ordinal", () => {
  it("reads 1st, 2nd, 3rd, 4th and the teens", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 101].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st"]);
  });
});

describe("eliminationLines", () => {
  it("lists who went out, in order, with the turn and how", () => {
    const lines = eliminationLines([
      out("Dan", 1, "conceded", 1),
      out("Bob", 2, "commander_damage", 7, "21 combat damage from one commander"),
      out("Cat", 3, "opponent_won", 9, "Ann won the game"),
    ]).map((l) => l.text);
    expect(lines).toEqual([
      "1st out: Dan (turn 1, conceded)",
      "2nd out: Bob (turn 7, commander damage)",
      "3rd out: Cat (turn 9, Ann won the game)",
    ]);
  });

  it("puts players who went out together on one line", () => {
    expect(eliminationLines([out("Ann", 3, "life", 9), out("Ben", 3, "life", 9)]).map((l) => l.text))
      .toEqual(["3rd out: Ann and Ben together (turn 9, 0 life)"]);
    expect(eliminationLines([out("Ann", 1, "life", 4), out("Ben", 1, "poison", 4), out("Cy", 1, "life", 4)]).map((l) => l.text))
      .toEqual(["1st out: Ann (0 life), Ben (poison) and Cy (0 life) together, turn 4"]);
  });

  it("comes in parts whose words make up the line", () => {
    const lines = eliminationLines([out("Dan", 1, "conceded", 1), out("Ann", 2, "life", 9), out("Ben", 2, "poison", 9)]);
    expect(lines[0]).toMatchObject({ head: "1st out:", who: "Dan", rest: " (turn 1, conceded)" });
    expect(lines[1]).toMatchObject({ head: "2nd out:", who: "Ann (0 life) and Ben (poison) together", rest: ", turn 9" });
    for (const l of lines) expect(`${l.head} ${l.who}${l.rest}`).toBe(l.text);
  });

  it("leaves out a turn nobody knows (an older save) and says 'out' when the reason is unknown", () => {
    expect(eliminationLines([out("Eve", 1, "left", null)])[0]!.text).toBe("1st out: Eve (left the table)");
    expect(howText({ how: "out", reason: "" })).toBe("out");
    expect(howText({ how: "out", reason: "a brand-new way to lose" })).toBe("a brand-new way to lose");
    expect(eliminationLines(undefined)).toEqual([]);
  });
});

describe("boardLines", () => {
  const seat = (over: Partial<FinalBoardSeat> = {}): FinalBoardSeat => ({
    seat: "p1", name: "Ann", life: 23, poison: 0, commanders: ["Krenko, Mob Boss"], more: 0, graveyard: 12, exile: 3,
    permanents: [{ name: "Goblin", count: 12 }, { name: "Sol Ring", count: 1 }, { name: "face-down card", count: 1 },
      { name: "Mountain", count: 8, land: true }, { name: "Command Tower", count: 1, land: true }],
    ...over,
  });

  it("reads life, poison, permanents, lands and the graveyard and exile", () => {
    expect(boardLines(seat())).toEqual({
      stats: "23 life",
      permanents: "Goblin ×12, Sol Ring, face-down card",
      lands: "Lands: Mountain ×8, Command Tower",
      zones: "Graveyard 12 · Exile 3",
    });
    expect(boardLines(seat({ poison: 4 })).stats).toBe("23 life · 4 poison");
  });

  it("counts what was left out, and says when the battlefield was empty", () => {
    expect(boardLines(seat({ more: 5 })).lands).toBe("Lands: Mountain ×8, Command Tower and 5 more");
    expect(boardLines(seat({ more: 2, permanents: [{ name: "Sol Ring", count: 1 }] })).permanents).toBe("Sol Ring and 2 more");
    const empty = boardLines(seat({ permanents: [] }));
    expect([empty.permanents, empty.lands]).toEqual(["No permanents", ""]);
  });
});
