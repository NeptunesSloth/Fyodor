import { describe, expect, it } from "vitest";
import type { LiveSummary, PredictionsView, SandboxBoard, SandboxResult } from "../services/spectate";
import {
  attackTargets,
  blockTargets,
  describeResult,
  fromBoard,
  patchCreature,
  pipHeadline,
  pipRows,
  pipStack,
  queueBody,
  queuedLabel,
  recapLine,
  setAttack,
  setBlock,
  stakeOptions,
  toScenario,
} from "./spectate";

const summary = (over: Partial<LiveSummary> = {}): LiveSummary => ({
  game: 1, turn: 7, phase: "main1", active: "p2", active_name: "Bob", priority: "p2", waiting: null,
  players: [
    { id: "p1", name: "Alice", color: "#a00", life: 31, poison: 0, out: null, hand: 5, library: 80,
      commander_damage: [{ key: "p2:0", name: "Krenko", damage: 8 }, { key: "p3:0", name: "Atraxa", damage: 14 }] },
    { id: "p2", name: "Bob", color: "#0a0", life: 40, poison: 3, out: null, hand: 2, library: 70, commander_damage: [] },
    { id: "p3", name: "Carol", color: "#00a", life: 0, poison: 0, out: "lost", hand: 0, library: 0, commander_damage: [] },
  ],
  stack: { count: 0, top: null }, log: ["Bob casts Lightning Bolt"], result: null, revision: 12,
  ...over,
});

describe("the live summary corner", () => {
  it("says whose turn it is and how many are still in", () => {
    expect(pipHeadline(summary())).toBe("Turn 7 · Bob's turn · 2 still in");
  });
  it("mentions the stack only when something is on it", () => {
    expect(pipStack(summary())).toBeNull();
    expect(pipStack(summary({ stack: { count: 2, top: "Lightning Bolt" } }))).toBe("Stack 2 · Lightning Bolt on top");
    expect(pipStack(summary({ stack: { count: 1, top: null } }))).toBe("Stack 1");
  });
  it("shows each player's heaviest commander damage and who is out", () => {
    const rows = pipRows(summary());
    expect(rows.map((r) => [r.name, r.life, r.out, r.active])).toEqual([["Alice", 31, false, false], ["Bob", 40, false, true], ["Carol", 0, true, false]]);
    expect(rows[0]!.commander).toEqual({ name: "Atraxa", damage: 14 });
    expect(rows[1]!.commander).toBeNull();
  });
});

const board: SandboxBoard = {
  players: [
    { id: "p1", name: "Alice", color: null, life: 20, poison: 0, commander_damage: {}, out: false },
    { id: "p2", name: "Bob", color: null, life: 7, poison: 0, commander_damage: { "p1:0": 15 }, out: false },
    { id: "p3", name: "Carol", color: null, life: 0, poison: 0, commander_damage: {}, out: true },
  ],
  creatures: [
    { id: "a", controller: "p1", name: "Krenko", power: 3, toughness: 3, keywords: [], commander: "p1:0", damage: 0, tapped: true, attacking: "p2", blocking: null },
    { id: "b", controller: "p2", name: "Wall", power: 0, toughness: 4, keywords: [], commander: null, damage: 0, tapped: false, attacking: null, blocking: "a" },
    { id: "c", controller: "p2", name: "Bear", power: 2, toughness: 2, keywords: [], commander: null, damage: 0, tapped: false, attacking: null, blocking: null },
    { id: "x", controller: "p3", name: "Gone", power: 9, toughness: 9, keywords: [], commander: null, damage: 0, tapped: false, attacking: "p2", blocking: null },
  ],
  commanders: { "p1:0": "Krenko, Mob Boss" },
};

describe("the damage sandbox", () => {
  it("copies the current public combat, leaving out players who are out", () => {
    const st = fromBoard(board);
    expect(st.players.map((p) => p.id)).toEqual(["p1", "p2"]);
    expect(st.creatures.map((c) => [c.id, c.attacking, c.blocking])).toEqual([["a", "p2", null], ["b", null, "a"], ["c", null, null]]);
    expect(toScenario(st).creatures.map((c) => c.id)).toEqual(["a", "b"]);  // only the creatures in combat
  });
  it("keeps blocks legal: a blocker blocks an attacker attacking its controller, never its own side", () => {
    let st = fromBoard(board);
    expect(blockTargets(st, st.creatures[2]!).map((c) => c.id)).toEqual(["a"]);
    expect(blockTargets(st, st.creatures[0]!)).toEqual([]);
    expect(attackTargets(st, st.creatures[0]!).map((p) => p.id)).toEqual(["p2"]);
    st = setBlock(st, "c", "a");
    expect(toScenario(st).creatures.map((c) => c.id)).toEqual(["a", "b", "c"]);
    st = setAttack(st, "a", null);  // the attacker stops attacking: its blockers stop blocking
    expect(toScenario(st).creatures).toEqual([]);
    st = setAttack(st, "b", "p1");  // a blocker that attacks stops blocking
    expect(st.creatures.find((c) => c.id === "b")!.blocking).toBeNull();
  });
  it("edits power, toughness and keywords without touching the board it came from", () => {
    const st = patchCreature(fromBoard(board), "a", { power: 7, keywords: ["trample"] });
    expect(toScenario(st).creatures[0]).toMatchObject({ power: 7, keywords: ["trample"] });
    expect(board.creatures[0]!.power).toBe(3);
  });
  it("describes the result in names", () => {
    const st = patchCreature(fromBoard(board), "a", { power: 7, keywords: ["trample"] });
    const res: SandboxResult = {
      rounds: [{ round: "only", dealt: [{ source: "a", target: "b", amount: 4 }, { source: "a", target: "p2", amount: 3 }] }],
      players: [
        { id: "p1", life_before: 20, life: 20, poison_before: 0, poison: 0, commander_damage: {}, loses: [] },
        { id: "p2", life_before: 7, life: 4, poison_before: 0, poison: 0, commander_damage: { "p1:0": 18 }, loses: [] },
      ],
      creatures: [{ id: "a", died: null, damage: 0, power: 7, toughness: 3 }, { id: "b", died: "lethal damage", damage: 4, power: 0, toughness: 4 }],
    };
    const text = describeResult(st, res);
    expect(text.rounds).toEqual([{ label: "Combat damage", lines: ["Krenko → Wall: 4", "Krenko → Bob: 3"] }]);
    expect(text.players[1]).toBe("Bob: 7 → 4 life · 18 commander damage from Krenko, Mob Boss");
    expect(text.creatures).toEqual(["Wall dies (lethal damage)"]);
    expect(text.losers).toEqual([]);
    const lethal = describeResult(st, { ...res, players: [{ ...res.players[1]!, commander_damage: { "p1:0": 21 }, loses: ["21 or more commander damage (p1:0)"] }] });
    expect(lethal.losers).toEqual(["Bob loses: 21 or more commander damage (Krenko, Mob Boss)"]);
  });
});

describe("predictions", () => {
  const v: PredictionsView = {
    game: 1, can_predict: true, stakes: [10, 25, 50, 100], markets: ["winner", "next_out"], candidates: [],
    balance: 120, available: 20, picks: { winner: { choice: "p1", choice_name: "Alice", stake: 100, outcome: null } },
    standings: [], recap: null,
  };
  it("offers only the stakes you can still cover (changing a pick frees its stake)", () => {
    expect(stakeOptions(v, "next_out")).toEqual([10]);
    expect(stakeOptions(v, "winner")).toEqual([10, 25, 50, 100]);
  });
  it("sums the night up in one casual line", () => {
    expect(recapLine({ game: 1, picks: [], standings: [{ name: "Carol", balance: 575, correct: 2, settled: 2 }, { name: "Dana", balance: 390, correct: 0, settled: 2 }] }))
      .toBe("Spectator predictions — Carol 575 · Dana 390");
  });
});

describe("the next-game queue", () => {
  it("sends a saved list, never an Archidekt link (that is fetched in the lobby)", () => {
    expect(queueBody({ name: "Goblins", body: { name: "Goblins", text: "1 Krenko" } })).toEqual({ name: "Goblins", text: "1 Krenko" });
    expect(queueBody({ name: "Old", body: { archidekt: "https://archidekt.com/decks/1" } })).toBeNull();
    expect(queueBody({ name: "File", body: { json: "{}" } })).toEqual({ name: "File", json: "{}" });
  });
  it("names the queued deck by its commanders", () => {
    expect(queuedLabel({ name: "Graveyard", commanders: ["Muldrotha, the Gravetide"] })).toBe("Muldrotha, the Gravetide");
    expect(queuedLabel({ name: "Graveyard", commanders: [] })).toBe("Graveyard");
  });
});
