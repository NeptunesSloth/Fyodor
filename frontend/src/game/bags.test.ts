import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import type { CardData } from "../types/cards";
import { commonBesidesDeck, COMMON_TOKENS, deckTokenIds, inGame, matchesToken, numberChits, parseChits, playerChits, teamChits, tokenKey, uniqueTokens } from "./bags";
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

/** A token printing, as the card database returns one. */
const tok = (id: string, over: Partial<CardData> = {}): CardData => ({
  id, oracle_id: `o-${id}`, name: "Goblin", layout: "token", set_code: "t", set_name: "T", collector_number: "1", rarity: null, mana_cost: "",
  cmc: 0, type_line: "Token Creature — Goblin", oracle_text: "", power: "1", toughness: "1", loyalty: null, defense: null, colors: ["R"],
  color_identity: ["R"], keywords: [], is_token: true, faces: [], double_faced: false, image_faces: 1, has_image: false, ...over,
});

describe("the Bag of Extras shows each token once (game/bags.ts uniqueTokens)", () => {
  it("drops another printing of the same token (one oracle id), keeping the first place and the printing with art", () => {
    const info: Record<string, CardData> = {
      g1: tok("g1", { oracle_id: "goblin" }),
      g2: tok("g2", { oracle_id: "goblin", has_image: true }),
      t1: tok("t1", { oracle_id: "treasure", name: "Treasure", type_line: "Token Artifact — Treasure", power: null, toughness: null, colors: [] }),
      g3: tok("g3", { oracle_id: "goblin" }),
    };
    expect(uniqueTokens(["g1", "t1", "g2", "g3"], (id) => info[id])).toEqual(["g2", "t1"]);
  });

  it("without an oracle id, the same name, P/T, types and colours are the same token; a different P/T or colour is not", () => {
    const info: Record<string, CardData> = {
      a: tok("a", { oracle_id: "" }),
      b: tok("b", { oracle_id: "" }),
      big: tok("big", { oracle_id: "", power: "2", toughness: "2" }),
      black: tok("black", { oracle_id: "", colors: ["B"] }),
    };
    expect(uniqueTokens(["a", "b", "big", "black"], (id) => info[id])).toEqual(["a", "big", "black"]);
    expect(tokenKey(info.a!)).toBe(tokenKey(info.b!));
  });

  it("keeps a token it knows nothing about yet (its data still loading) by its own id", () => {
    expect(uniqueTokens(["x", "x", "y"], () => undefined)).toEqual(["x", "y"]);
  });

  it("removes my deck's repeated tokens before the cap (the user's Copy ×3, Beast ×2, Treasure ×2)", () => {
    const info: Record<string, CardData> = {
      c1: tok("c1", { oracle_id: "copy", name: "Copy" }), c2: tok("c2", { oracle_id: "copy", name: "Copy" }), c3: tok("c3", { oracle_id: "copy", name: "Copy" }),
      b1: tok("b1", { oracle_id: "beast44", name: "Beast" }), b2: tok("b2", { oracle_id: "beast44", name: "Beast" }),
    };
    const v = view({ players: [{ id: "p1", name: "Alice", token_shortcuts: ["c1", "b1", "c2"] }] as GameView["players"] });
    const related = (id: string) => ({ krenko: ["b2", "c3"] } as Record<string, string[]>)[id];
    expect(deckTokenIds(v, "p1", related, (id) => info[id])).toEqual(["c1", "b1"]);
  });
});

describe("the common tokens find their printing in the card database (matchesToken)", () => {
  it("takes a printing with the same name, types, P/T, colours and rules text, and refuses a namesake that differs", () => {
    const spirit = COMMON_TOKENS.find((t) => t.id === "spirit")!;
    expect(matchesToken(tok("s", { name: "Spirit", type_line: "Token Creature — Spirit", colors: ["W"], oracle_text: "Flying", keywords: ["Flying"] }), spirit)).toBe(true);
    expect(matchesToken(tok("s", { name: "Spirit", type_line: "Token Creature — Spirit", colors: ["W", "B"], oracle_text: "Flying" }), spirit)).toBe(false);
    expect(matchesToken(tok("s", { name: "Spirit", type_line: "Token Creature — Spirit", colors: ["W"], oracle_text: "Flying", power: "2", toughness: "2" }), spirit)).toBe(false);
    expect(matchesToken(tok("s", { name: "Spirit", type_line: "Token Creature — Spirit", colors: ["W"], oracle_text: "" }), spirit)).toBe(false);
    const treasure = COMMON_TOKENS.find((t) => t.id === "treasure")!;
    const printed = tok("t", { name: "Treasure", type_line: "Token Artifact — Treasure", power: null, toughness: null, colors: [],
      oracle_text: "{T}, Sacrifice this token: Add one mana of any color." });
    expect(matchesToken(printed, treasure)).toBe(true);
    // reminder text in parentheses doesn't count
    expect(matchesToken({ ...printed, oracle_text: "{T}, Sacrifice this token: Add one mana of any color. (It's an artifact.)" }, treasure)).toBe(true);
  });
});

describe("the bag's common tokens leave out what my deck's list already shows (commonBesidesDeck)", () => {
  it("drops the Goblin my deck makes (the same token by oracle id, or by name, P/T, types and colours when not found yet)", () => {
    const goblin = tok("g1", { oracle_id: "goblin" });
    const found = { goblin: tok("g9", { oracle_id: "goblin" }) };
    expect(commonBesidesDeck(COMMON_TOKENS, found, [goblin]).map((t) => t.id)).not.toContain("goblin");
    // not found in the database: the predefined token is compared by what it is
    expect(commonBesidesDeck(COMMON_TOKENS, {}, [goblin]).map((t) => t.id)).not.toContain("goblin");
    // a 2/2 black Goblin in the deck is another token: the common 1/1 red one stays
    const other = tok("g2", { oracle_id: "goblin22", power: "2", toughness: "2", colors: ["B"] });
    expect(commonBesidesDeck(COMMON_TOKENS, {}, [other]).map((t) => t.id)).toContain("goblin");
    expect(commonBesidesDeck(COMMON_TOKENS, {}, [])).toHaveLength(COMMON_TOKENS.length);
  });
});

