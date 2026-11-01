import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../types/game";
import { attachmentLinks, MAX_ATTACH_LINKS, tetherAnchor } from "./attachments";

const card = (id: string, zone: string, extra: Partial<GameCard> = {}): GameCard =>
  ({ id, owner: "p1", controller: "p1", zone, face_down: false, card_id: null, name: id, face: 0, revealed: false, note: "", is_token: false, ...extra }) as GameCard;

const view = (cards: GameCard[]): Pick<GameView, "cards"> => ({ cards: Object.fromEntries(cards.map((c) => [c.id, c])) });

// a creature wearing a sword and an aura, a curse on a player, and an aura on an opponent's creature
const board = view([
  card("bear", "p1:battlefield"),
  card("sword", "p1:battlefield", { attached_to: "bear" }),
  card("aura", "p1:battlefield", { attached_to: "bear" }),
  card("curse", "p1:battlefield", { attached_player: "p2" }),
  card("theirs", "p2:battlefield", { controller: "p2", owner: "p2" }),
  card("pacifism", "p1:battlefield", { attached_to: "theirs" }),
  card("lone", "p1:battlefield"),
]);

describe("attachmentLinks", () => {
  it("draws nothing while nothing is hovered or selected", () => {
    expect(attachmentLinks(board, [])).toEqual([]);
    expect(attachmentLinks(board, [null, undefined])).toEqual([]);
  });
  it("hovering a host shows everything attached to it; hovering an attachment shows its host", () => {
    expect(attachmentLinks(board, ["bear"])).toEqual([{ from: "sword", to: "bear" }, { from: "aura", to: "bear" }]);
    expect(attachmentLinks(board, ["sword"])).toEqual([{ from: "sword", to: "bear" }]);
    expect(attachmentLinks(board, ["theirs"])).toEqual([{ from: "pacifism", to: "theirs" }]); // across the table
    expect(attachmentLinks(board, ["lone"])).toEqual([]);
  });
  it("links an Aura enchanting a player to that player", () => {
    expect(attachmentLinks(board, ["curse"])).toEqual([{ from: "curse", to: "p2", player: true }]);
  });
  it("hover and selection add up, without duplicates", () => {
    expect(attachmentLinks(board, ["bear", "sword", "pacifism"])).toHaveLength(3);
  });
  it("follows the attachment state: a stale host off the battlefield, or a card that left, draws no line", () => {
    const moved = view([card("bear", "p1:graveyard"), card("sword", "p1:battlefield", { attached_to: "bear" }), card("gone", "p1:exile", { attached_to: "x" })]);
    expect(attachmentLinks(moved, ["bear", "sword", "gone"])).toEqual([]);
    const detached = view([card("bear", "p1:battlefield"), card("sword", "p1:battlefield", { attached_to: null })]);
    expect(attachmentLinks(detached, ["bear"])).toEqual([]);
  });
  it("caps the number of lines", () => {
    const many = view([card("host", "p1:battlefield"), ...Array.from({ length: 40 }, (_, i) => card(`eq${i}`, "p1:battlefield", { attached_to: "host" }))]);
    expect(attachmentLinks(many, ["host"])).toHaveLength(MAX_ATTACH_LINKS);
  });
});

describe("tetherAnchor", () => {
  const f = (x: number, y: number, rot = 0) => ({ x, y, hw: 0.42, hh: 0.585, rot });
  it("starts on the sliver of a tucked attachment that peeks out from under its host", () => {
    // the server tucks an attachment up and to the right of its host (10, -18 virtual units)
    const a = tetherAnchor(f(0.1, -0.18), f(0, 0));
    expect(a.y).toBeLessThan(-0.585); // past the host's far edge …
    expect(a.y).toBeGreaterThan(-0.18 - 0.585); // … but still on the attachment
  });
  it("uses the attachment's centre when the two are apart", () => {
    expect(tetherAnchor(f(3, 0), f(0, 0))).toEqual({ x: 3, y: 0 });
  });
  it("accounts for a turned (tapped) host", () => {
    // a host turned a quarter is wide: an attachment 0.5 to its right is still under it
    expect(tetherAnchor(f(0.5, 0), f(0, 0, Math.PI / 2)).x).toBeGreaterThan(0.585);
    expect(tetherAnchor(f(0.5, 0), f(0, 0)).x).toBeGreaterThan(0.42);
  });
  it("falls back to the centre when it's exactly underneath", () => {
    expect(tetherAnchor(f(0, 0), f(0, 0))).toEqual({ x: 0, y: 0 });
  });
});
