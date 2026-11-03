import { describe, expect, it } from "vitest";
import type { GameCard, PlayerView } from "../types/game";
import { commanderDealt, commanderKeyOf, commanderMatrix, dealtText } from "./commanderDamage";

const player = (id: string, name: string, cmdrs: string[], dmg: Record<string, number> = {}, extra: Partial<PlayerView> = {}) => ({
  id, name, color: `#${id}`, left: false, commander_damage: dmg,
  commanders: cmdrs.map((k) => ({ key: k, name: k[0]!.toUpperCase() + k.slice(1), card_id: null, instance_id: null, zone: null, tax: 0 })),
  ...extra,
});

// Ann owns Atraxa; Bob owns Tymna and Thrasios (partners); Cara has taken 21 from Atraxa
const players = [
  player("p1", "Ann", ["atraxa"], { tymna: 3 }),
  player("p2", "Bob", ["tymna", "thrasios"], { atraxa: 8 }),
  player("p3", "Cara", ["edgar"], { atraxa: 21, thrasios: 2 }),
];

describe("commanderDealt", () => {
  it("lists what one commander dealt to each of its owner's opponents, zeros included", () => {
    expect(commanderDealt(players, "atraxa")).toEqual([
      { player: "p2", name: "Bob", color: "#p2", damage: 8 },
      { player: "p3", name: "Cara", color: "#p3", damage: 21 },
    ]);
    expect(commanderDealt(players, "edgar").map((r) => [r.name, r.damage])).toEqual([["Ann", 0], ["Bob", 0]]);
    expect(dealtText(commanderDealt(players, "atraxa"))).toBe("Bob 8 · Cara 21");
  });
  it("counts damage a stolen commander dealt its own owner (903.10a), and skips players who left with none", () => {
    const stolen = [player("p1", "Ann", ["atraxa"], { atraxa: 4 }), player("p2", "Bob", []), player("p3", "Cara", [], {}, { left: true })];
    expect(commanderDealt(stolen, "atraxa").map((r) => [r.name, r.damage])).toEqual([["Ann", 4], ["Bob", 0]]);
  });
  it("is empty for an unknown commander", () => {
    expect(commanderDealt(players, "nobody")).toEqual([]);
  });
});

describe("commanderKeyOf", () => {
  it("only trusts what the server sent this viewer: a hidden card is never a commander", () => {
    const base = { id: "c1", owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false };
    expect(commanderKeyOf({ ...base, card_id: "x", name: "Atraxa", face: 0, revealed: false, note: "", is_token: false, commander_key: "atraxa" } as GameCard)).toBe("atraxa");
    expect(commanderKeyOf({ ...base, card_id: "x", name: "Sol Ring", face: 0, revealed: false, note: "", is_token: false } as GameCard)).toBeNull();
    expect(commanderKeyOf({ ...base, face_down: true, hidden: true } as GameCard)).toBeNull();
    expect(commanderKeyOf(undefined)).toBeNull();
  });
});

describe("commanderMatrix", () => {
  it("has a row per commander and a column per player, marking each commander's own column", () => {
    const { cols, rows } = commanderMatrix(players);
    expect(cols.map((c) => c.name)).toEqual(["Ann", "Bob", "Cara"]);
    expect(rows.map((r) => r.key)).toEqual(["atraxa", "tymna", "thrasios", "edgar"]);
    expect(rows[0]!.cells.map((c) => (c.own ? "·" : c.damage))).toEqual(["·", 8, 21]);
    expect(rows[1]!.cells.map((c) => (c.own ? "·" : c.damage))).toEqual([3, "·", 0]);
    expect(rows[2]!.cells.map((c) => (c.own ? "·" : c.damage))).toEqual([0, "·", 2]);
    expect(rows[1]!.owner).toEqual({ id: "p2", name: "Bob", color: "#p2" });
  });
  it("drops a player who left from the columns unless commander damage is recorded against them", () => {
    const gone = [player("p1", "Ann", ["atraxa"]), player("p2", "Bob", [], {}, { left: true }), player("p3", "Cara", [], { atraxa: 5 }, { left: true })];
    expect(commanderMatrix(gone).cols.map((c) => c.name)).toEqual(["Ann", "Cara"]);
  });
});
