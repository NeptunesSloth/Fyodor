import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../types/game";
import { attachmentLinks, boardCards, guests, guestsOf, guestSpot, MAX_ATTACH_LINKS, tetherAnchor } from "./attachments";

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

describe("attached elsewhere (guests)", () => {
  // Alice (p1): a sword on her own bear, Pacifism on Bob's Ogre, a Curse on Bob, a face-down card attached to the Ogre.
  // Cara (p3): Arrest on the same Ogre. Bob (p2): his Ogre, and a stolen Matron he owns, now on Alice's side with her Control Magic.
  const table = (): Pick<GameView, "cards" | "zones"> => {
    const cards = [
      card("bear", "p1:battlefield", { x: 100, y: 100 }),
      card("sword", "p1:battlefield", { attached_to: "bear" }),
      card("pacifism", "p1:battlefield", { attached_to: "ogre", x: 500, y: 300 }),
      card("curse", "p1:battlefield", { attached_player: "p2" }),
      card("morph", "p1:battlefield", { attached_to: "ogre", face_down: true }),
      card("ogre", "p2:battlefield", { owner: "p2", controller: "p2", x: 200, y: 50 }),
      card("arrest", "p3:battlefield", { owner: "p3", controller: "p3", attached_to: "ogre" }),
      card("matron", "p1:battlefield", { owner: "p2" }),
      card("magic", "p1:battlefield", { attached_to: "matron" }),
    ];
    const zones: Record<string, string[]> = { "p1:battlefield": [], "p2:battlefield": [], "p3:battlefield": [] };
    for (const c of cards) zones[c.zone]!.push(c.id);
    return { cards: Object.fromEntries(cards.map((c) => [c.id, c])), zones } as Pick<GameView, "cards" | "zones">;
  };
  it("draws an attachment on another player's permanent on that player's board, and a Curse on the enchanted player's", () => {
    const v = table();
    const g = guests(v);
    expect(g.get("pacifism")).toEqual({ board: "p2:battlefield", host: "ogre" });
    expect(g.get("arrest")).toEqual({ board: "p2:battlefield", host: "ogre" });
    expect(g.get("curse")).toEqual({ board: "p2:battlefield", host: null });
    // one's own, a stolen creature's Control Magic (same board now), and anything face down stay where they are
    for (const id of ["sword", "magic", "matron", "morph", "bear"]) expect(g.has(id)).toBe(false);
  });
  it("each board lists its guests just under their hosts (Curses first), and the controller's board leaves them out", () => {
    const v = table();
    expect(boardCards(v, "p2:battlefield")).toEqual(["curse", "pacifism", "arrest", "ogre"]);
    expect(boardCards(v, "p1:battlefield")).toEqual(["bear", "sword", "morph", "matron", "magic"]);
    expect(boardCards(v, "p3:battlefield")).toEqual([]);
  });
  it("keeps the same array while nothing changed (memoised layouts), and the zone's own when no guest touches it", () => {
    const v = table();
    const a = boardCards(v, "p2:battlefield");
    expect(boardCards(table(), "p2:battlefield")).toBe(a);
    const quiet = { cards: { x: card("x", "p4:battlefield") }, zones: { "p4:battlefield": ["x"] } } as Pick<GameView, "cards" | "zones">;
    expect(boardCards(quiet, "p4:battlefield")).toBe(quiet.zones["p4:battlefield"]);
  });
  it("follows the state: once the host has left, the Aura is drawn on its own board again", () => {
    const v = table();
    v.cards.ogre = { ...v.cards.ogre!, zone: "p2:graveyard" };
    v.zones["p2:battlefield"] = [];
    expect(guests(v).has("pacifism")).toBe(false);
    expect(boardCards(v, "p1:battlefield")).toContain("pacifism");
  });
  it("counts each player's cards attached elsewhere (their plaque's chip)", () => {
    const v = table();
    expect(guestsOf(v, "p1").sort()).toEqual(["curse", "pacifism"]);
    expect(guestsOf(v, "p3")).toEqual(["arrest"]);
    expect(guestsOf(v, "p2")).toEqual([]);
  });
  it("free placement: tucked a step under the host each (up and to the right, as the server tucks), a Curse along the front", () => {
    const v = table();
    const at = (h: string): [number, number] | null => [v.cards[h]!.x ?? 0, v.cards[h]!.y ?? 0];
    expect(guestSpot(v, "pacifism", at)).toEqual([210, 32]);
    expect(guestSpot(v, "arrest", at)).toEqual([220, 18]);
    expect(guestSpot(v, "curse", at)?.[1]).toBe(12);
    expect(guestSpot(v, "sword", at)).toBeNull();
  });
});
