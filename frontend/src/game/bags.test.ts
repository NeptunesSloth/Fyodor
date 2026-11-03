import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { COMMON_TOKENS, deckTokenIds, inGame, numberChits, parseChits, playerChits, teamChits } from "./bags";
import { outRefusal } from "./outOfGame";

const view = (over: Partial<GameView> = {}) => ({
  seat_order: ["p1", "p2", "p3"],
  players: [
    { id: "p1", name: "Alice", token_shortcuts: ["tok-a"] },
    { id: "p2", name: "Bob" },
    { id: "p3", name: "Cleo", left: false },
  ],
  cards: {
    c1: { id: "c1", owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, name: "Krenko", card_id: "krenko" },
    c2: { id: "c2", owner: "p2", controller: "p2", zone: "p2:battlefield", face_down: false, name: "Other", card_id: "other" },
    c3: { id: "c3", hidden: true, owner: "p1", controller: "p1", zone: "p1:hand", face_down: false },
  },
  rules: undefined,
  ...over,
}) as unknown as GameView;

describe("the draw bag's chits (game/bags.ts)", () => {
  it("reads typed chits one a line or between commas, trimmed, blanks dropped, as the server takes them", () => {
    expect(parseChits("Team A\nTeam B,  chaos ;\n\n,x")).toEqual(["Team A", "Team B", "chaos", "x"]);
    expect(parseChits("a".repeat(60))).toEqual(["a".repeat(40)]);
    expect(parseChits(Array.from({ length: 150 }, (_, i) => i).join(","))).toHaveLength(100);
  });

  it("fills with numbers, the players still in the game, or even teams", () => {
    expect(numberChits(4)).toEqual(["1", "2", "3", "4"]);
    expect(teamChits(5)).toEqual(["Team A", "Team B", "Team A", "Team B", "Team A"]);
    expect(teamChits(1)).toEqual(["Team A", "Team B"]);
    expect(playerChits(view())).toEqual(["Alice", "Bob", "Cleo"]);
    const out = view({ rules: { conceded: ["p2"], lost: { p3: "0 life" } } as unknown as GameView["rules"] });
    expect(inGame(out).map((p) => p.id)).toEqual(["p1"]);
    expect(playerChits(view({ players: [...view().players.slice(0, 2), { id: "p3", name: "Cleo", left: true }] as GameView["players"] }))).toEqual(["Alice", "Bob"]);
  });
});

describe("the Bag of Extras (game/bags.ts)", () => {
  it("offers my deck's tokens: its Tokens section, then those my visible cards list (never another player's, never a hidden card)", () => {
    const related = (id: string) => ({ krenko: ["goblin-tok"], other: ["their-tok"] } as Record<string, string[]>)[id];
    expect(deckTokenIds(view(), "p1", related)).toEqual(["tok-a", "goblin-tok"]);
    expect(deckTokenIds(view(), "p2", related)).toEqual(["their-tok"]);
  });

  it("makes the predefined tokens with the rules text the server's rules use", () => {
    const treasure = COMMON_TOKENS.find((t) => t.id === "treasure")!.token;
    expect(treasure).toEqual({ name: "Treasure", type_line: "Token Artifact — Treasure", text: "{T}, Sacrifice this token: Add one mana of any color." });
    expect(COMMON_TOKENS.filter((t) => t.pt === "1/1").every((t) => t.token.power === "1" && t.token.toughness === "1")).toBe(true);
  });

  it("is not for a player who is out (it makes objects), while the cannon and the draw bag stay theirs", () => {
    const out = view({ viewer: "p2", rules: { conceded: ["p2"], lost: {} } as unknown as GameView["rules"] });
    expect(outRefusal(out, "p2", "create_token")).toMatch(/out of this game/);
    for (const t of ["cannon", "bag_fill", "bag_draw", "bag_show", "bag_return", "bag_empty", "roll"]) expect(outRefusal(out, "p2", t)).toBeNull();
  });
});
