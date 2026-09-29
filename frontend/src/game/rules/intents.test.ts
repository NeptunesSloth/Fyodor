import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCardCache } from "../../state/cardCache";
import { useGame } from "../../state/gameStore";
import type { CardData } from "../../types/cards";
import type { GameView } from "../../types/game";
import { abilityLines, automationOn, dropAsIntent, isLand, manaAbilityIndex, next, RESPONSE_CYCLE, tapForMana } from "./intents";
import { legalClass, paidSymbol } from "./RulesHud";
import { rulesMenu } from "./rulesMenu";

const card = (id: string, zone: string, card_id: string) => ({ id, zone, card_id, name: card_id, owner: "p1", controller: "p1" });

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
      c3: card("c3", "p1:battlefield", "looter"),
      c4: card("c4", "p2:hand", "forest"),
      h: { id: "h", zone: "p2:hand", hidden: true },
    },
    rules,
  }) as unknown as GameView;

const RULES = {
  automation: "full", paused: false, prefs: { response: "auto", payment: "ask", mana_sources: {} }, card_modes: {},
  hints: { playable_lands: ["c1"], castable: ["c2"], activatable: [{ card_id: "c3", ability: 0 }] },
};

const sent: unknown[] = [];

beforeEach(() => {
  sent.length = 0;
  useGame.setState({ view: null, actingAs: null, send: vi.fn(async (a) => { sent.push(a); return true; }) });
  useCardCache.setState({
    cards: {
      forest: { id: "forest", name: "Forest", type_line: "Basic Land — Forest", oracle_text: "({T}: Add {G}.)" } as CardData,
      bolt: { id: "bolt", name: "Lightning Bolt", type_line: "Instant", oracle_text: "Lightning Bolt deals 3 damage to any target." } as CardData,
      looter: { id: "looter", name: "Merfolk Looter", type_line: "Creature — Merfolk Rogue",
        oracle_text: "{T}: Draw a card, then discard a card." } as CardData,
    },
  });
});

describe("automation intents", () => {
  it("is on only with an unpaused rules view", () => {
    expect(automationOn(view(undefined))).toBe(false);
    expect(automationOn(view({ ...RULES, paused: true }))).toBe(false);
    expect(automationOn(view(RULES))).toBe(true);
  });

  it("knows lands from the card cache, never from hidden cards", () => {
    const v = view(RULES);
    expect(isLand("c1", v)).toBe(true);
    expect(isLand("c2", v)).toBe(false);
    expect(isLand("h", v)).toBe(false);
  });

  it("turns a drop from hand into play_land or cast_spell", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropAsIntent(["c1"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(dropAsIntent(["c2"], { zone: "stack" })).toBe(true);
    expect(sent).toEqual([{ type: "play_land", card_id: "c1", x: 10, y: 20 }, { type: "cast_spell", card_id: "c2" }]);
  });

  it("leaves Alt-drops, other players' cards, multi-drops and OFF to the sandbox", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropAsIntent(["c1"], { zone: "p1:battlefield", manual: true })).toBe(false);
    expect(dropAsIntent(["c4"], { zone: "p2:battlefield" })).toBe(false);
    expect(dropAsIntent(["c1", "c2"], { zone: "p1:battlefield" })).toBe(false);
    expect(dropAsIntent(["c2"], { zone: "p1:graveyard" })).toBe(false);
    useGame.setState({ view: view(undefined) });
    expect(dropAsIntent(["c1"], { zone: "p1:battlefield" })).toBe(false);
    expect(sent).toEqual([]);
  });

  it("cycles RESPONSE and MANA", () => {
    expect(next(RESPONSE_CYCLE, "off")).toBe("auto");
    expect(next(RESPONSE_CYCLE, "on")).toBe("off");
  });

  it("taps your own land for mana (never a plain tap) with automation on", () => {
    const base = view(RULES);
    const v = { ...base, cards: { ...base.cards, f1: card("f1", "p1:battlefield", "forest"), l1: card("l1", "p1:battlefield", "looter") } } as unknown as GameView;
    useGame.setState({ view: v });
    expect(manaAbilityIndex("f1", v)).toBe(0);  // a basic land's intrinsic ability
    expect(tapForMana("f1", "p1")).toBe(true);
    expect(sent).toEqual([{ type: "activate_ability", card_id: "f1", ability: 0 }]);
    expect(tapForMana("l1", "p1")).toBe(false);  // no mana ability: a plain tap
    expect(tapForMana("c4", "p1")).toBe(false);  // not yours
  });

  it("during a convoke / improvise payment, clicking a highlighted creature or artifact taps it for that", () => {
    const base = view({ ...RULES, decision: { id: "d1", player: "p1", kind: "choose_one", prompt: "Tap mana",
      display: { kind: "tap_mana", sources: ["f1"], convoke: ["cr"], improvise: ["ar"] }, options: [] } });
    const v = { ...base, cards: { ...base.cards, f1: card("f1", "p1:battlefield", "forest"), cr: card("cr", "p1:battlefield", "looter"),
      ar: card("ar", "p1:battlefield", "looter") } } as unknown as GameView;
    useGame.setState({ view: v });
    expect(tapForMana("cr", "p1")).toBe(true);
    expect(tapForMana("ar", "p1")).toBe(true);
    expect(tapForMana("f1", "p1")).toBe(true);
    expect(sent).toEqual([
      { type: "activate_ability", card_id: "cr", ability: 0, convoke: true },
      { type: "activate_ability", card_id: "ar", ability: 0, improvise: true },
      { type: "activate_ability", card_id: "f1", ability: 0 },
    ]);
  });

  it("a committed convoke / improvise / delve card is marked as paying, not tapped, and clicking it again takes it back", () => {
    const base = view({ ...RULES, options: { highlights: "on" }, decision: { id: "d1", player: "p1", kind: "choose_one", prompt: "Tap mana",
      display: { kind: "tap_mana", sources: [], convoke: ["cr"], improvise: [], delve: ["g1"], committed: ["cr"] }, options: [] } });
    const v = { ...base, cards: { ...base.cards, cr: card("cr", "p1:battlefield", "looter"), g1: card("g1", "p1:graveyard", "bolt") } } as unknown as GameView;
    useGame.setState({ view: v });
    expect(legalClass(v, "cr", "p1")).toBe("rules-committed");
    expect(legalClass(v, "g1", "p1")).toBe("rules-mana-source");
    expect(tapForMana("cr", "p1")).toBe(true);
    expect(sent).toEqual([{ type: "activate_ability", card_id: "cr", ability: 0, convoke: true }]);
    expect(paidSymbol("1")).toBe("{1}");
    expect(paidSymbol("G")).toBe("{G}");
  });

  it("splits ability lines without reminder text", () => {
    expect(abilityLines("Flying\n{T}: Add {C}{C}. (Mana ability.)\n")).toEqual(["Flying", "{T}: Add {C}{C}."]);
  });
});

describe("rules card menu", () => {
  const labels = (items: ReturnType<typeof rulesMenu>) => items.map((i) => (i === "separator" ? "—" : i.label));

  it("is empty with automation off", () => {
    const v = view(undefined);
    expect(rulesMenu(v.cards.c1!, v, "p1")).toEqual([]);
  });

  it("offers play, cast, activate and the per-card automation", () => {
    const v = view(RULES);
    expect(labels(rulesMenu(v.cards.c1!, v, "p1"))).toEqual(["Play land", "Automation: AUTO", "—"]);
    expect(labels(rulesMenu(v.cards.c2!, v, "p1"))[0]).toBe("Cast");
    const looter = rulesMenu(v.cards.c3!, v, "p1");
    expect(labels(looter)[0]).toBe("Activate: {T}: Draw a card, then discard a card.");
    const first = looter[0];
    if (first === "separator" || !first) throw new Error("expected an item");
    expect(first.disabled).toBe(false);
    first.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "c3", ability: 0 }]);
  });

  it("disables what the server doesn't list as legal", () => {
    const v = view({ ...RULES, hints: {} });
    const [play] = rulesMenu(v.cards.c1!, v, "p1");
    expect(play !== "separator" && play?.disabled).toBe(true);
  });

  it("offers flashback from the graveyard and cycling from the hand", () => {
    const base = view({ ...RULES, hints: { castable: ["g1"] } });
    const v = { ...base, cards: { ...base.cards, g1: card("g1", "p1:graveyard", "firebolt"), m1: card("m1", "p1:hand", "moor") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        firebolt: { id: "firebolt", name: "Firebolt", type_line: "Sorcery", oracle_text: "Firebolt deals 2 damage to any target.\nFlashback {4}{R}" } as CardData,
        moor: { id: "moor", name: "Barren Moor", type_line: "Land", oracle_text: "Barren Moor enters tapped.\n{T}: Add {B}.\nCycling {B} ({B}, Discard this card: Draw a card.)" } as CardData,
      },
    });
    expect(labels(rulesMenu(v.cards.g1!, v, "p1"))[0]).toBe("Cast with flashback");
    const cyc = rulesMenu(v.cards.m1!, v, "p1").find((i) => i !== "separator" && i.label === "Cycling {B}");
    if (!cyc || cyc === "separator") throw new Error("expected a cycling item");
    cyc.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "m1", ability: 2 }]);
  });

  it("offers morph: cast face down from hand, turn face up on the battlefield", () => {
    const base = view(RULES);
    const v = { ...base, cards: { ...base.cards, mh: card("mh", "p1:hand", "slinger"), mb: { ...card("mb", "p1:battlefield", "slinger"), face_down: true } } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        slinger: { id: "slinger", name: "Gravel Slinger", type_line: "Creature — Human Soldier", oracle_text: "Morph {1}{W} (You may cast this card face down.)" } as CardData,
      },
    });
    expect(labels(rulesMenu(v.cards.mh!, v, "p1"))).toContain("Cast face down (morph, {3})");
    const up = rulesMenu(v.cards.mb!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Turn face up"));
    if (!up || up === "separator") throw new Error("expected Turn face up");
    up.onClick?.();
    expect(sent).toEqual([{ type: "turn_face_up", card_id: "mb" }]);
  });

  it("shows nothing about hidden cards", () => {
    const v = view(RULES);
    expect(rulesMenu(v.cards.h!, v, "p1")).toEqual([]);
  });
});
