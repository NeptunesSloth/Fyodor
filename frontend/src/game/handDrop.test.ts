import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToasts } from "../components/Toasts";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import type { CardData } from "../types/cards";
import type { GameView } from "../types/game";
import { useMenu } from "../components/ContextMenu";
import { dropCaption, dropFromHand, handDropKind, ontoTable, type HandDropFacts } from "./handDrop";
import { rulesMenu } from "./rules/rulesMenu";
import { playFromHand } from "./Hand";
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
  it("plays a land and casts a spell, like the card menu; both where they were dropped (drag to cast)", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropFromHand(["c1"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(dropFromHand(["c2"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(sent).toEqual([{ type: "play_land", card_id: "c1", x: 10, y: 20 }, { type: "cast_spell", card_id: "c2", ask_optional: true, x: 10, y: 20 }]);
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

describe("dropFromHand: a card with two halves or two faces asks which, as its menu does", () => {
  const two = (id: string, layout: string, faces: { name: string; mana_cost?: string; type_line: string }[]) =>
    ({ id, name: faces.map((f) => f.name).join(" // "), layout, type_line: faces.map((f) => f.type_line).join(" // "), oracle_text: "", faces }) as unknown as CardData;
  const cards = {
    giant: two("giant", "adventure", [{ name: "Bonecrusher Giant", mana_cost: "{2}{R}", type_line: "Creature — Giant" }, { name: "Stomp", mana_cost: "{1}{R}", type_line: "Instant — Adventure" }]),
    fire: two("fire", "split", [{ name: "Fire", mana_cost: "{1}{R}", type_line: "Instant" }, { name: "Ice", mana_cost: "{1}{U}", type_line: "Instant" }]),
    valakut: two("valakut", "modal_dfc", [{ name: "Valakut Awakening", mana_cost: "{2}{R}", type_line: "Instant" }, { name: "Valakut Stoneforge", type_line: "Land" }]),
  };
  const withHand = () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, castable: ["a1", "s1", "m1"] } });
    return { ...base, cards: { ...base.cards, a1: card("a1", "p1:hand", "giant"), s1: card("s1", "p1:hand", "fire"), m1: card("m1", "p1:hand", "valakut") } } as unknown as GameView;
  };
  const labels = () => useMenu.getState().menu!.items.map((i) => (i === "separator" ? "-" : i.label));
  const choose = (n: number) => (useMenu.getState().menu!.items[n] as { onClick: () => void }).onClick();
  beforeEach(() => {
    useMenu.setState({ menu: null });
    useCardCache.setState({ cards: { ...useCardCache.getState().cards, ...cards } });
    useGame.setState({ view: withHand() });
  });

  it("an adventure: the card menu's two Cast rows, at the drop point; the chosen half is cast", () => {
    const v = withHand();
    expect(dropFromHand(["a1"], { zone: "p1:battlefield", x: 10, y: 20, at: { clientX: 640, clientY: 380 } })).toBe(true);
    expect(sent).toEqual([]); // nothing cast until the player chooses
    const menu = useMenu.getState().menu!;
    expect([menu.x, menu.y]).toEqual([640, 380]);
    expect(labels()).toEqual(["Cast Bonecrusher Giant {2}{R}", "Cast Stomp {1}{R}"]);
    // the same rows the right-click menu offers
    const fromMenu = rulesMenu(v.cards.a1!, v, "p1").filter((i) => i !== "separator").map((i) => (i as { label: string }).label);
    expect(fromMenu.slice(0, 2)).toEqual(labels());
    choose(1);
    // (dropped on my battlefield: the spot goes with the cast; the server uses it only for a permanent entering my battlefield)
    expect(sent).toEqual([{ type: "cast_spell", card_id: "a1", face: 1, ask_optional: true, x: 10, y: 20 }]);
  });

  it("a split card asks which half", () => {
    expect(dropFromHand(["s1"], { zone: "stack" })).toBe(true);
    expect(labels()).toEqual(["Cast Fire {1}{R}", "Cast Ice {1}{U}"]);
    choose(0);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "s1", face: 0, ask_optional: true }]);
  });

  it("a modal double-faced card: cast its spell face, or play its land face where it was dropped", () => {
    expect(dropFromHand(["m1"], { zone: "p1:battlefield", x: 30, y: 40 })).toBe(true);
    expect(labels()).toEqual(["Cast Valakut Awakening {2}{R}", "Play Valakut Stoneforge (land)"]);
    choose(1);
    expect(dropFromHand(["m1"], { zone: "p2:battlefield", x: 30, y: 40 })).toBe(true);
    choose(0);
    expect(sent).toEqual([{ type: "play_land", card_id: "m1", face: 1, x: 30, y: 40 }, { type: "cast_spell", card_id: "m1", face: 0, ask_optional: true }]);
  });

  it("greys an MDFC's spell face the server doesn't list as castable, as the plain Cast row was; its land face is the server's to refuse", () => {
    const v = withHand();
    useGame.setState({ view: { ...v, rules: { ...v.rules!, hints: { ...v.rules!.hints, castable: [] } } } as GameView });
    expect(dropFromHand(["m1"], { zone: "p1:battlefield" })).toBe(true);
    const rows = useMenu.getState().menu!.items as { label: string; disabled?: boolean }[];
    expect(rows.map((r) => !!r.disabled)).toEqual([true, false]);
  });

  it("a double-click (or Enter) in the hand asks which half too, where it was clicked (playtest nov 16: Fire // Ice cast Fire)", () => {
    playFromHand("s1", "p1", { clientX: 300, clientY: 900 });
    expect(sent).toEqual([]);
    const menu = useMenu.getState().menu!;
    expect([menu.x, menu.y]).toEqual([300, 900]);
    expect(labels()).toEqual(["Cast Fire {1}{R}", "Cast Ice {1}{U}"]);
    choose(1);
    playFromHand("a1", "p1");
    expect(labels()).toEqual(["Cast Bonecrusher Giant {2}{R}", "Cast Stomp {1}{R}"]);
    playFromHand("m1", "p1");
    expect(labels()).toEqual(["Cast Valakut Awakening {2}{R}", "Play Valakut Stoneforge (land)"]);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "s1", face: 1, ask_optional: true }]);
  });

  it("Alt-drop still places it by hand, with no question", () => {
    expect(dropFromHand(["m1"], { zone: "p1:battlefield", x: 30, y: 40, manual: true })).toBe(false);
    expect(useMenu.getState().menu).toBeNull();
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
