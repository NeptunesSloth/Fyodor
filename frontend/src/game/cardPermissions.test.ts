import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { actionRefusal, cardEditRefusal, cardKeepers, limitedSeat } from "./cardPermissions";

const card = (id: string, zone: string, owner: string, controller = owner, extra: Record<string, unknown> = {}) =>
  ({ id, zone, owner, controller, face_down: false, name: id, card_id: null, face: 0, revealed: false, note: "", is_token: false, ...extra });

const CARDS = {
  ring: card("ring", "p1:battlefield", "p1"),
  stolen: card("stolen", "p2:battlefield", "p1", "p2"),
  exiled: card("exiled", "p2:exile", "p1"),
  bolt: card("bolt", "stack", "p1"),
  "hidden:p1:hand:0": { id: "hidden:p1:hand:0", zone: "p1:hand", owner: "p1", controller: "p1", face_down: false, hidden: true },
  goblin: card("goblin", "p1:battlefield", "p1", "p1", { is_token: true }),
  bird: card("bird", "p2:battlefield", "p2", "p2", { is_token: true }),
};

const view = (settings: Record<string, unknown> = { card_permissions: "owner" }, over: Record<string, unknown> = {}, game: Record<string, unknown> = {}): GameView =>
  ({
    viewer: "p2",
    seat_order: ["p1", "p2", "p3"],
    players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }, { id: "p3", name: "Cleo" }],
    cards: CARDS,
    game: { mode: "lan", host_seat: "p1", seats: { p1: {}, p2: {}, p3: {} }, settings, ...game },
    ...over,
  }) as unknown as GameView;

const ALICE = "Alice's cards: only Alice or the host can change them at this table.";

describe("cardKeepers", () => {
  it("is the controller on the battlefield and the stack, the owner and the zone's player elsewhere", () => {
    expect(cardKeepers(CARDS.ring)).toEqual(["p1"]);
    expect(cardKeepers(CARDS.stolen)).toEqual(["p2"]); // a stolen permanent is its controller's
    expect(cardKeepers(CARDS.bolt)).toEqual(["p1"]);
    expect(cardKeepers(CARDS.exiled)).toEqual(["p1", "p2"]); // my card in your exile: both of us
    expect(cardKeepers(card("x", "p1:graveyard", "p1"))).toEqual(["p1"]);
    expect(cardKeepers(card("y", "p2:hand", "p1"))).toEqual(["p2"]); // a hidden zone is its player's (a hidden owner isn't public)
  });
});

describe("limitedSeat", () => {
  it("limits nobody under the default (old servers send no setting) or at a hot-seat table", () => {
    expect(limitedSeat(view({}))).toBeNull();
    expect(limitedSeat(view({ card_permissions: "everyone" }))).toBeNull();
    expect(limitedSeat(view(undefined, {}, { mode: "local" }))).toBeNull();
  });
  it("never limits the host's seat or a spectator; limits a guest's seat", () => {
    expect(limitedSeat(view(undefined, { viewer: "p1" }))).toBeNull();
    expect(limitedSeat(view(undefined, { viewer: "__spectator__" }))).toBeNull();
    expect(limitedSeat(view())).toBe("p2");
  });
});

describe("cardEditRefusal", () => {
  it("refuses another player's cards with the server's words", () => {
    expect(cardEditRefusal(view(), ["ring"])).toBe(ALICE);
    expect(cardEditRefusal(view(undefined, { viewer: "p3" }), ["exiled"])).toBe("Alice's cards: only Alice, Bob or the host can change them at this table.");
    expect(cardEditRefusal(view(), ["hidden:p1:hand:0"])).toBe(ALICE);
  });
  it("allows a player's own cards, the cards they control and the cards in their zones", () => {
    expect(cardEditRefusal(view(), ["stolen", "exiled", "bird"])).toBeNull();
    expect(cardEditRefusal(view(), ["bird", "ring"])).toBe(ALICE); // one of someone else's is enough
    expect(cardEditRefusal(view(undefined, { viewer: "p1" }), ["bird"])).toBeNull(); // the host helps
    expect(cardEditRefusal(view({}), ["ring"])).toBeNull();
    expect(cardEditRefusal(view(), ["gone"])).toBeNull(); // unknown ids: the server answers
  });
});

describe("actionRefusal", () => {
  it("refuses manual edits of another player's cards, by whatever field names them", () => {
    expect(actionRefusal(view(), { type: "tap", card_ids: ["ring"] })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "note", card_id: "ring", text: "x" })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "set_position", moves: [["ring", 1, 2]] })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "move", card_ids: ["bolt"], to: { zone: "graveyard", player: "p1" } })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "draw", player: "p1" })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "create_token", player: "p1", token: { name: "Goblin" } })).toBe(ALICE);
    expect(actionRefusal(view(), { type: "cleanup", what: ["tokens"] })).toBe(ALICE); // would delete Alice's Goblin too
  });
  it("lets through rules intents, looking, player counters, procedures and a player's own edits", () => {
    for (const action of [
      { type: "cast_spell", card_id: "ring" },
      { type: "activate_ability", card_id: "ring", ability: 0 },
      { type: "resolve_top" },
      { type: "life", player: "p1", delta: -3 },
      { type: "look_top", player: "p1" },
      { type: "create_arrow", source: "ring", targets: ["bird"] },
      { type: "copy_card", card_id: "ring" },
      { type: "create_token", token: { name: "Bird" } },
      { type: "draw" },
      { type: "tap", card_ids: ["stolen", "bird"] },
      { type: "attach", card_ids: ["bird"], to: "ring" },
      { type: "cleanup", what: ["damage", "effects"] },
      { type: "next_turn" },
    ]) {
      expect(actionRefusal(view(), action)).toBeNull();
    }
  });
});
