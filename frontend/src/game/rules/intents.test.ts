import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCardCache } from "../../state/cardCache";
import { useGame } from "../../state/gameStore";
import type { CardData } from "../../types/cards";
import type { GameView } from "../../types/game";
import { abilityLines, automationOn, canConcede, choose, concede, divide, dropAsIntent, isLand, manaAbilityIndex, next, RESPONSE_CYCLE, tapForMana } from "./intents";
import { canSubmitChoice, doneLabel, legalClass, paidSymbol } from "./RulesHud";
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
  it("lets a seated player still in the game concede at any time (104.3a)", async () => {
    const base = { ...RULES, conceded: [], lost: {}, winner: null, priority: "p2" };
    expect(canConcede(view(base), "p1")).toBe(true); // without priority
    expect(canConcede(view({ ...base, decision: { id: "d", player: "p2" } }), "p1")).toBe(true); // during another's decision
    expect(canConcede(view({ ...base, paused: true }), "p1")).toBe(true); // even while paused
    expect(canConcede(view({ ...base, conceded: ["p1"] }), "p1")).toBe(false);
    expect(canConcede(view({ ...base, lost: { p1: "life" } }), "p1")).toBe(false);
    expect(canConcede(view({ ...base, winner: "p2" }), "p1")).toBe(false);
    expect(canConcede(view(undefined), "p1")).toBe(false); // no rules engine at this table
    expect(canConcede({ ...view(base), viewer: "__spectator__" } as GameView, "p1")).toBe(false);
    await concede();
    expect(sent).toEqual([{ type: "concede" }]);
  });

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

  it("offers casting and land plays from exile, the graveyard and the top of the library only when the server lists them", () => {
    const base = view({ ...RULES, hints: { castable: ["x1", "g2"], playable_lands: ["x2"] } });
    const v = { ...base, cards: { ...base.cards, x1: card("x1", "p1:exile", "bolt"), x2: card("x2", "p1:exile", "forest"),
      x3: card("x3", "p1:exile", "bolt"), g2: card("g2", "p1:graveyard", "bolt"), l1: card("l1", "p1:library", "bolt") } } as unknown as GameView;
    expect(labels(rulesMenu(v.cards.x1!, v, "p1"))[0]).toBe("Cast from exile");
    expect(labels(rulesMenu(v.cards.g2!, v, "p1"))[0]).toBe("Cast from graveyard");
    expect(labels(rulesMenu(v.cards.x2!, v, "p1"))[0]).toBe("Play land from exile");
    expect(labels(rulesMenu(v.cards.x3!, v, "p1"))).not.toContain("Cast from exile");
    expect(labels(rulesMenu(v.cards.l1!, v, "p1"))).not.toContain("Cast from library");
    const cast = rulesMenu(v.cards.x1!, v, "p1")[0];
    if (!cast || cast === "separator") throw new Error("expected Cast");
    cast.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "x1" }]);
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

  it("offers Equip for an Equipment on the battlefield", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true } });
    const v = { ...base, cards: { ...base.cards, eq: card("eq", "p1:battlefield", "splitter") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        splitter: { id: "splitter", name: "Bonesplitter", type_line: "Artifact — Equipment", oracle_text: "Equipped creature gets +2/+0.\nEquip {1}" } as CardData,
      },
    });
    const equip = rulesMenu(v.cards.eq!, v, "p1").find((i) => i !== "separator" && i.label === "Activate: Equip {1}");
    if (!equip || equip === "separator") throw new Error("expected Equip");
    expect(equip.disabled).toBe(false);
    equip.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "eq", ability: 1 }]);
  });

  const item = (items: ReturnType<typeof rulesMenu>, label: string) => {
    const found = items.find((i) => i !== "separator" && i.label === label);
    if (!found || found === "separator") throw new Error(`expected ${label}`);
    return found;
  };

  it("offers kicker (cast with kicker=1) and multikicker (a count submenu)", () => {
    const base = view({ ...RULES, hints: { castable: ["k1", "m1"] } });
    const v = { ...base, cards: { ...base.cards, k1: card("k1", "p1:hand", "burst"), m1: card("m1", "p1:hand", "kraken") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        burst: { id: "burst", name: "Burst Lightning", type_line: "Instant",
          oracle_text: "Kicker {4} (You may pay an additional {4} as you cast this spell.)\nBurst Lightning deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead." } as CardData,
        kraken: { id: "kraken", name: "Gnarlid Colony", type_line: "Creature",
          oracle_text: "Multikicker {1}{G} (You may pay an additional {1}{G} any number of times as you cast this spell.)\nThis enters with a +1/+1 counter on it for each time it was kicked." } as CardData,
      },
    });
    const kick = item(rulesMenu(v.cards.k1!, v, "p1"), "Cast with Kicker {4}");
    expect(kick.disabled).toBe(false);
    kick.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "k1", kicker: 1 }]);
    const multi = item(rulesMenu(v.cards.m1!, v, "p1"), "Cast with Multikicker {1}{G}");
    expect(multi.submenu?.map((i) => (i === "separator" ? "—" : i.label))).toEqual(
      ["Kicked ×1", "Kicked ×2", "Kicked ×3", "Kicked ×4", "Kicked ×5", "Kicked ×6"]);
    const three = multi.submenu?.[2];
    if (!three || three === "separator") throw new Error("expected ×3");
    three.onClick?.();
    expect(sent[1]).toEqual({ type: "cast_spell", card_id: "m1", kicker: 3 });
    expect(labels(rulesMenu(v.cards.c2!, v, "p1")).some((l) => /kicker/i.test(l))).toBe(false);  // no kicker line
  });

  it("offers graveyard-activated abilities (113.6m) only for graveyard costs or server-listed ones", () => {
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "g1", ability: 1 }] } });
    const v = { ...base, cards: { ...base.cards, g1: card("g1", "p1:graveyard", "scrounger"), g2: card("g2", "p1:graveyard", "looter"),
      g3: card("g3", "p1:graveyard", "bloodghast") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        scrounger: { id: "scrounger", name: "Scrapheap Scrounger", type_line: "Creature",
          oracle_text: "{T}: Mill a card.\n{1}{B}, Exile another creature card from your graveyard, Exile Scrapheap Scrounger from your graveyard: Return Scrapheap Scrounger to the battlefield tapped." } as CardData,
        bloodghast: { id: "bloodghast", name: "Ghoul", type_line: "Creature",
          oracle_text: "{2}{B}, Exile this card from your graveyard: Create a 2/2 black Zombie creature token." } as CardData,
      },
    });
    const menu = rulesMenu(v.cards.g1!, v, "p1");
    const acts = menu.filter((i) => i !== "separator" && i.label.startsWith("Activate:"));
    expect(acts).toHaveLength(1);  // not the {T} ability
    const act = acts[0];
    if (!act || act === "separator") throw new Error("expected Activate");
    expect(act.disabled).toBe(false);
    act.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "g1", ability: 1 }]);
    expect(labels(rulesMenu(v.cards.g2!, v, "p1")).some((l) => l.startsWith("Activate"))).toBe(false);  // looter: no graveyard cost
    const ghoul = rulesMenu(v.cards.g3!, v, "p1").filter((i) => i !== "separator" && i.label.startsWith("Activate:"));
    expect(ghoul).toHaveLength(1);  // a graveyard cost, not listed right now: shown disabled
    expect(ghoul[0] !== "separator" && ghoul[0]?.disabled).toBe(true);
  });

  it("shows nothing about hidden cards", () => {
    const v = view(RULES);
    expect(rulesMenu(v.cards.h!, v, "p1")).toEqual([]);
  });
});

describe("decision answers", () => {
  it("lets an empty answer through when min_choices is 0 (cancel a cost choice)", () => {
    expect(canSubmitChoice(0, 0, 2)).toBe(true);
    expect(doneLabel(0, 0, 2)).toBe("Done (none)");
    expect(canSubmitChoice(0, 1, 1)).toBe(false);
    expect(canSubmitChoice(3, 0, 2)).toBe(false);
    expect(doneLabel(2, 0, 2)).toBe("Done (2)");
    void choose("d1", []);
    expect(sent).toEqual([{ type: "choose", decision_id: "d1", option_ids: [] }]);
  });

  it("answers a divide decision with amounts in the options' order and no option ids", () => {
    void divide("d2", [2, 1]);
    expect(sent).toEqual([{ type: "choose", decision_id: "d2", option_ids: [], amounts: [2, 1] }]);
  });
});
