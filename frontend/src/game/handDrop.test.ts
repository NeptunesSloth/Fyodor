import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "../components/Toasts";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import type { CardData } from "../types/cards";
import type { GameView } from "../types/game";
import { dropCaption, dropFromHand, handDropKind, ontoTable, type HandDropFacts } from "./handDrop";
import { contrast, CHIP_INK, SEAT_CHIPS } from "./seatChips";
import { SEAT_ACTIONS } from "./seatActions";

const card = (id: string, zone: string, card_id: string) => ({ id, zone, card_id, name: card_id, owner: "p1", controller: "p1" });
const RULES = { automation: "full", paused: false, prefs: {}, card_modes: {}, hints: { playable_lands: ["c1", "x1"], castable: ["c2"] } };
const view = (rules: object | undefined): GameView =>
  ({
    viewer: "p1",
    seat_order: ["p1", "p2"],
    players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }],
    game: { seats: { p1: {}, p2: {} } },
    turn: { active_player: "p1" },
    cards: {
      c1: card("c1", "p1:hand", "forest"),
      c2: card("c2", "p1:hand", "bolt"),
      c3: card("c3", "p1:battlefield", "bolt"),
      x1: card("x1", "p1:hand", "unknown-land"), // a land whose card data hasn't loaded here yet
      k: card("k", "p1:command", "bolt"),
    },
    rules,
  }) as unknown as GameView;

const sent: unknown[] = [];
beforeEach(() => {
  sent.length = 0;
  useToasts.setState({ toasts: [] } as never);
  useGame.setState({ view: null, actingAs: null, send: vi.fn(async (a) => { sent.push(a); return true; }) });
  useCardCache.setState({
    cards: {
      forest: { id: "forest", name: "Forest", type_line: "Basic Land — Forest", oracle_text: "({T}: Add {G}.)" } as CardData,
      bolt: { id: "bolt", name: "Lightning Bolt", type_line: "Instant", oracle_text: "Lightning Bolt deals 3 damage to any target." } as CardData,
    },
  });
});

const facts = (f: Partial<HandDropFacts>): HandDropFacts => ({ automation: true, manual: false, from: "p1:hand", to: "p1:battlefield", me: "p1", count: 1, ...f });

describe("a drop from the hand (pure mapping)", () => {
  it("plays one card dropped on the table with automation on", () => {
    expect(handDropKind(facts({}))).toBe("play");
    expect(handDropKind(facts({ to: "stack" }))).toBe("play");
    expect(handDropKind(facts({ to: "p2:battlefield" }))).toBe("play"); // still mine to cast, onto my side
    expect(handDropKind(facts({ from: "p1:command" }))).toBe("play"); // a commander
  });

  it("is a plain move with automation off, Alt held, off the table, or not from my hand", () => {
    expect(handDropKind(facts({ automation: false }))).toBe("move");
    expect(handDropKind(facts({ manual: true }))).toBe("move");
    expect(handDropKind(facts({ to: "p1:graveyard" }))).toBe("move");
    expect(handDropKind(facts({ to: "p1:hand" }))).toBe("move");
    expect(handDropKind(facts({ to: null }))).toBe("move");
    expect(handDropKind(facts({ from: "p1:battlefield" }))).toBe("move");
    expect(handDropKind(facts({ from: "p2:hand" }))).toBe("move");
  });

  it("refuses several cards at once onto the table (one cast at a time), not a silent move", () => {
    expect(handDropKind(facts({ count: 2 }))).toBe("many");
    expect(handDropKind(facts({ count: 2, manual: true }))).toBe("move");
  });

  it("knows the table's zones and captions the drag", () => {
    expect(ontoTable("stack")).toBe(true);
    expect(ontoTable("p3:battlefield")).toBe(true);
    expect(ontoTable("p1:exile")).toBe(false);
    expect(dropCaption("play", true, false)).toMatch(/^Play land/);
    expect(dropCaption("play", false, false)).toMatch(/^Cast · Alt: place by hand$/);
    expect(dropCaption("move", false, true)).toBe("Place by hand");
    expect(dropCaption("move", false, false)).toBeNull();
  });
});

describe("dropFromHand (the intent sent)", () => {
  it("plays a land and casts a spell, like the card menu", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropFromHand(["c1"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(dropFromHand(["c2"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(sent).toEqual([{ type: "play_land", card_id: "c1", x: 10, y: 20 }, { type: "cast_spell", card_id: "c2", ask_optional: true }]);
  });

  it("casts onto my side when dropped on another player's mat; a land dropped on the stack is played", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropFromHand(["c2"], { zone: "p2:battlefield", x: 5, y: 5 })).toBe(true);
    expect(dropFromHand(["c1"], { zone: "stack" })).toBe(true);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "c2", ask_optional: true }, { type: "play_land", card_id: "c1" }]);
  });

  it("plays a land the engine lists as playable even before its card data is here", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropFromHand(["x1"], { zone: "p1:battlefield", x: 1, y: 2 })).toBe(true);
    expect(sent).toEqual([{ type: "play_land", card_id: "x1", x: 1, y: 2 }]);
  });

  it("leaves Alt-drops and automation off to a plain move; a multi-card drop only explains", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropFromHand(["c2"], { zone: "p1:battlefield", manual: true })).toBe(false);
    expect(dropFromHand(["c1", "c2"], { zone: "p1:battlefield" })).toBe(true);
    expect(useToasts.getState().toasts.at(-1)?.text).toMatch(/one card at a time/);
    useGame.setState({ view: view({ ...RULES, paused: true }) });
    expect(dropFromHand(["c2"], { zone: "p1:battlefield" })).toBe(false);
    useGame.setState({ view: view(undefined) });
    expect(dropFromHand(["c2"], { zone: "p1:battlefield" })).toBe(false);
    expect(sent).toEqual([]);
  });
});

describe("seat chips", () => {
  it("gives every seat button its own colour, with an ivory glyph that reads on it (WCAG 1.4.11: 3:1)", () => {
    const bases = SEAT_ACTIONS.map((a) => SEAT_CHIPS[a.id].base);
    expect(new Set(bases).size).toBe(bases.length);
    for (const c of Object.values(SEAT_CHIPS)) {
      expect(contrast(CHIP_INK, c.base)).toBeGreaterThanOrEqual(3);
      expect(contrast(CHIP_INK, c.light)).toBeGreaterThanOrEqual(3); // the face's lit corner too
    }
  });
});
