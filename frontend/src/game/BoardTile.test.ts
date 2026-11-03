import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BoardTile, packStats } from "./BoardTile";
import { useCardCache } from "../state/cardCache";
import type { GameCard, VisibleCard } from "../types/game";
import type { CardData } from "../types/cards";

const base = { owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, face: 0, revealed: false, note: "" };
const tile = (card: GameCard, stats = "") => renderToStaticMarkup(createElement(BoardTile, { card, stats }));

describe("BoardTile: a permanent on the arranged board", () => {
  it("draws a token without art as the proxy's art window, with its name, a token mark and its P/T", () => {
    const goblin = { ...base, id: "g", name: "Goblin", card_id: null, is_token: true,
      token: { name: "Goblin", card_id: null, power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin", text: "" } } as VisibleCard;
    const html = tile(goblin);
    expect(html).toContain("tile-proxy");
    expect(html).toContain("tile-token");
    expect(html).toContain("tile-glyph");
    expect(html).toContain(">Goblin<");
    expect(html).toContain("tile-token-mark");
    expect(html).toMatch(/tile-pt[^>]*>1\/1</);
  });

  it("shows the card's art cropped to its art window, the name, and a commander's crown and brass rim", () => {
    const data = { id: "krenko-1", name: "Krenko, Mob Boss", type_line: "Legendary Creature — Goblin Warrior", power: "3", toughness: "3",
      colors: ["R"], color_identity: ["R"], faces: [], double_faced: false, image_faces: 1, has_image: true, mana_cost: "{2}{R}{R}", oracle_text: "" } as unknown as CardData;
    // (a static render reads the store's initial state)
    useCardCache.getInitialState().cards[data.id] = data;
    const krenko = { ...base, id: "k", name: "Krenko, Mob Boss", card_id: "krenko-1", is_token: false, commander_key: "p2:0" } as VisibleCard;
    const html = tile(krenko);
    expect(html).toContain('class="tile-art"');
    expect(html).toContain("/api/images/krenko-1?face=0&amp;size=normal");
    expect(html).toContain('alt="Krenko, Mob Boss"');
    expect(html).toContain("tile-commander");
    expect(html).toContain("tile-crown");
    expect(html).toMatch(/tile-pt[^>]*>3\/3</); // printed, when the rules don't say
    // the rules' P/T wins, with its direction and gained keywords
    const ruled = tile(krenko, packStats({ pt: [5, 5], base: ["3", "3"], gained: ["haste"] }));
    expect(ruled).toContain("tile-pt up");
    expect(ruled).toContain("5/5");
    expect(ruled).toContain('data-testid="stat-badge"');
    expect(ruled).toContain("Has: haste");
  });

  it("shows nothing of a face-down card but its back", () => {
    const hidden = { id: "h", hidden: true, owner: "p2", controller: "p2", zone: "p2:battlefield", face_down: true } as GameCard;
    const html = tile(hidden);
    expect(html).toContain("tile-back");
    expect(html).not.toContain("tile-name");
  });

  it("packs the rules' stats into a string (an unchanged P/T re-renders nothing)", () => {
    expect(packStats(undefined)).toBe("");
    expect(packStats({ pt: [2, 2], base: ["2", "2"] })).toBe(packStats({ pt: [2, 2], base: ["2", "2"] }));
    expect(packStats({ pt: [1, 1], base: ["2", "2"] })).toContain(" down");
  });
});
