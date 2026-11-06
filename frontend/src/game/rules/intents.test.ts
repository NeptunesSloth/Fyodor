import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCardCache } from "../../state/cardCache";
import { useGame } from "../../state/gameStore";
import type { CardData } from "../../types/cards";
import type { GameView } from "../../types/game";
import { abilityLines, automationOn, canConcede, choose, concede, divide, dropAsIntent, isLand, manaAbilityIndex, next, RESPONSE_CYCLE, send, tapForMana, useXPrompt, submitNumericPrompt } from "./intents";
import { canSubmitChoice, dialState, doneLabel, legalClass, paidSymbol } from "./RulesHud";
import { rulesMenu } from "./rulesMenu";
import { libraryTopActions } from "../ZonePile";
import type { MenuItem } from "../../components/ContextMenu";

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
      rite: { id: "rite", name: "Rite of Replication", type_line: "Sorcery",
        oracle_text: "Kicker {5} (You may pay an additional {5} as you cast this spell.)\nCreate a token that's a copy of target creature. If this spell was kicked, create five of those tokens instead." } as CardData,
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
    expect(canConcede(view({ ...base, draw_reason: "Mandatory loop" }), "p1")).toBe(false);
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

  it("asks about kicker when a kicker card is dragged to cast (Rite of Replication): plain, or kicked (playtest nov 6)", async () => {
    const { useMenu } = await import("../../components/ContextMenu");
    const base = view(RULES);
    const v = { ...base, cards: { ...base.cards, r1: card("r1", "p1:hand", "rite") } } as unknown as GameView;
    useGame.setState({ view: v });
    expect(dropAsIntent(["r1"], { zone: "stack" })).toBe(true);
    expect(sent).toEqual([]); // nothing cast yet: the player chooses
    const items = useMenu.getState().menu!.items.map((i) => (i === "separator" ? "-" : i.label));
    expect(items).toEqual(["Cast without kicker", "Cast with Kicker {5}"]);
    const kicked = useMenu.getState().menu!.items[1] as { onClick: () => void };
    kicked.onClick();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "r1", kicker: 1 }]);
  });

  it("turns a drop from hand into play_land or cast_spell", () => {
    useGame.setState({ view: view(RULES) });
    expect(dropAsIntent(["c1"], { zone: "p1:battlefield", x: 10, y: 20 })).toBe(true);
    expect(dropAsIntent(["c2"], { zone: "stack" })).toBe(true);
    expect(sent).toEqual([{ type: "play_land", card_id: "c1", x: 10, y: 20 }, { type: "cast_spell", card_id: "c2", ask_optional: true }]);
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
    expect(sent).toEqual([{ type: "activate_ability", card_id: "f1", ability: 0, tap_for_mana: true }]);  // the server reads which mana ability (Chromatic Lantern: playtest nov 5)
    expect(tapForMana("l1", "p1")).toBe(false);  // no mana ability: a plain tap
    expect(tapForMana("c4", "p1")).toBe(false);  // not yours
  });

  it("taps a token given a mana ability (Cryptolith Rite) for mana, though it has no card data (playtest nov 6)", () => {
    const base = view({ ...RULES, stats: { t1: { abilities: [{ index: 100, text: "{T}: Add one mana of any color.", kind: "mana" }] } } });
    const insect = { ...card("t1", "p1:battlefield", "looter"), card_id: null, is_token: true, name: "Insect" };
    const v = { ...base, cards: { ...base.cards, t1: insect } } as unknown as GameView;
    useGame.setState({ view: v });
    expect(manaAbilityIndex("t1", v)).toBe(100);
    expect(tapForMana("t1", "p1")).toBe(true);
    expect(sent).toEqual([{ type: "activate_ability", card_id: "t1", ability: 100, tap_for_mana: true }]);
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
      { type: "activate_ability", card_id: "f1", ability: 0, tap_for_mana: true },
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

  it("offers beam me up from the graveyard as flashback is, with the server's cost (Star Trek, wave 112T)", () => {
    const base = view({ ...RULES, hints: { alt_castable: { g1: [{ id: "g1:1", label: "Energize: beam me up {3}{U}" },
      { id: "s1:0", label: "Scotty, Miracle Worker: beam me up {1}{U}" }] } } });
    const g1 = { ...card("g1", "p1:graveyard", "energize"), name: "Energize" };
    const v = { ...base, cards: { ...base.cards, g1 } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      energize: { id: "energize", name: "Energize", type_line: "Sorcery", oracle_text: "Return target creature an opponent controls to its owner's hand.\nBeam me up {3}{U}" } as CardData } });
    const items = rulesMenu(v.cards.g1!, v, "p1");
    expect(labels(items).filter((l) => l.startsWith("Cast"))).toEqual(["Cast with beam me up {3}{U}", "Cast with beam me up {1}{U} (Scotty, Miracle Worker)"]);
    sent.length = 0;
    const first = items.find((i) => i !== "separator" && i.label === "Cast with beam me up {3}{U}");
    if (!first || first === "separator") throw new Error("expected the beam me up item");
    first.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "g1", alt_cost: "g1:1" }]);
  });

  it.each([
    ["Street Wraith", "Creature — Wraith", "Swampwalk\nCycling—Pay 2 life. (Pay 2 life, Discard this card: Draw a card.)", "Cycling—Pay 2 life.", 1],
    ["Edge of Autumn", "Sorcery", "If you control four or fewer lands, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nCycling—Sacrifice a land. (Sacrifice a land, Discard this card: Draw a card.)", "Cycling—Sacrifice a land.", 1],
    ["Sojourner's Companion", "Artifact Creature — Frog", "Affinity for artifacts\nArtifact landcycling {2} ({2}, Discard this card: Search your library for an artifact land card, reveal it, put it into your hand, then shuffle.)", "Artifact landcycling {2}", 1],
  ])("offers %s's cycling cost from the hand", (name, typeLine, oracle, label, index) => {
    const base = view(RULES);
    const source = card("cycling", "p1:hand", "cycling-data");
    const v = { ...base, cards: { ...base.cards, cycling: source } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      "cycling-data": { id: "cycling-data", name, type_line: typeLine, oracle_text: oracle } as CardData } });
    const item = rulesMenu(v.cards.cycling!, v, "p1").find((item) => item !== "separator" && item.label === label);
    if (!item || item === "separator") throw new Error("expected the cycling action");
    item.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "cycling", ability: index }]);
  });

  it.each(["Slivercycling {3}", "Cycling {1}{U}"])("offers a private hand grant using the server index: %s", (text) => {
    const base = view({ ...RULES, stats: { c1: { abilities: [{ index: 100, kind: "keywords", text }] } } });
    const item = rulesMenu(base.cards.c1!, base, "p1").find((item) => item !== "separator" && item.label === text);
    if (!item || item === "separator") throw new Error("expected granted cycling action");
    item.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "c1", ability: 100 }]);
  });

  it("does not offer cycling for another player's visible hand grant", () => {
    const base = view({ ...RULES, stats: { other: { abilities: [{ index: 100, kind: "keywords", text: "Slivercycling {3}" }] } } });
    const other = { ...card("other", "p2:hand", "forest"), owner: "p2", controller: "p2" };
    const v = { ...base, cards: { ...base.cards, other } } as unknown as GameView;
    expect(labels(rulesMenu(v.cards.other!, v, "p1"))).not.toContain("Slivercycling {3}");
  });

  it("offers a card in an opponent's exile only when the server lists it for you (Hostage Taker, Valgavoth)", () => {
    const listed = view({ ...RULES, hints: { castable: ["x1"] } });
    const v = { ...listed, cards: { ...listed.cards, x1: card("x1", "p2:exile", "firebolt") } } as unknown as GameView;
    expect(labels(rulesMenu(v.cards.x1!, v, "p1"))[0]).toBe("Cast from exile");
    const unlisted = { ...v, rules: { ...v.rules, hints: {} } } as unknown as GameView;
    expect(labels(rulesMenu(unlisted.cards.x1!, unlisted, "p1"))).not.toContain("Cast from exile");
  });

  it("offers a hand ability the server lists (Tetzimoc's reveal from the hand, 113.6m)", () => {
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "t1", ability: 1 }] } });
    const v = { ...base, cards: { ...base.cards, t1: card("t1", "p1:hand", "tetz") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        tetz: { id: "tetz", name: "Tetzimoc, Primal Death", type_line: "Legendary Creature — Elder Dinosaur",
          oracle_text: "Deathtouch\n{B}, Reveal this card from your hand: Put a prey counter on target creature. Activate only during your turn.\nWhen Tetzimoc enters, destroy each creature your opponents control with a prey counter on it." } as CardData,
      },
    });
    expect(labels(rulesMenu(v.cards.t1!, v, "p1"))).toContain("{B}, Reveal this card from your hand: Put a prey counter on target creature. Activate only during your turn.");
    const unlisted = view({ ...RULES, hints: {} });
    const u = { ...unlisted, cards: { ...unlisted.cards, t1: card("t1", "p1:hand", "tetz") } } as unknown as GameView;
    expect(labels(rulesMenu(u.cards.t1!, u, "p1")).some((l) => l.startsWith("{B}, Reveal"))).toBe(false);
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

  it("offers an ability that works in exile (Q, Stacking the Deck's grant), enabled only when the server lists it (113.6b)", () => {
    const granted = { index: 2, kind: "activated",
      text: "Exile a card from your hand: Create a copy of this card. You may cast the copy. Activate only during your turn and only if this card is exiled." };
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "x1", ability: 2 }] },
      stats: { x1: { abilities: [granted] }, x2: { abilities: [granted] }, x3: { abilities: [{ index: 0, kind: "activated", text: "{T}: Draw a card." }] } } });
    const v = { ...base, cards: { ...base.cards, x1: card("x1", "p1:exile", "bolt"), x2: card("x2", "p1:exile", "bolt"),
      x3: card("x3", "p1:exile", "bolt"), x4: card("x4", "p2:exile", "bolt") } } as unknown as GameView;
    const [now] = rulesMenu(v.cards.x1!, v, "p1").filter((i) => i !== "separator" && i.label.startsWith("Activate:"));
    if (!now || now === "separator") throw new Error("expected Activate");
    expect(now.disabled).toBe(false);
    now.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "x1", ability: 2 }]);
    // the same ability not usable right now (not your turn): shown, disabled
    const later = rulesMenu(v.cards.x2!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Activate:"));
    expect(later && later !== "separator" && later.disabled).toBe(true);
    // an ordinary ability of an exiled card isn't offered, nor anything on another player's exiled card
    expect(labels(rulesMenu(v.cards.x3!, v, "p1")).some((l) => l.startsWith("Activate:"))).toBe(false);
    expect(labels(rulesMenu(v.cards.x4!, v, "p1")).some((l) => l.startsWith("Activate:"))).toBe(false);
  });

  it("offers no activation for a triggered ability an exiled card was given (Uvilda's refine counters)", () => {
    const upkeep = { index: 10000, kind: "triggered", text: "At the beginning of your upkeep, if this card is exiled, remove a refine counter from it." };
    const base = view({ ...RULES, stats: { x1: { abilities: [upkeep] } } });
    const v = { ...base, cards: { ...base.cards, x1: card("x1", "p1:exile", "bolt") } } as unknown as GameView;
    expect(labels(rulesMenu(v.cards.x1!, v, "p1")).some((l) => l.startsWith("Activate:"))).toBe(false);
  });

  it("offers each granted replicate (Hugh) as its own count, in the server's order (702.56b)", () => {
    const base = view({ ...RULES, hints: { castable: ["c2"], replicate111r3: { c2: ["Replicate {2}{U} (Hugh, First of Many)", "Replicate {2}{U} (Hugh, First of Many)"] } } });
    const v = base as unknown as GameView;
    const casts = rulesMenu(v.cards.c2!, v, "p1").filter((i) => i !== "separator" && i.label.startsWith("Cast with Replicate"));
    expect(casts).toHaveLength(2);
    const second = casts[1];
    if (!second || second === "separator" || !second.submenu) throw new Error("expected a submenu");
    const twice = second.submenu.find((i) => i !== "separator" && i.label === "Replicate ×2");
    if (!twice || twice === "separator") throw new Error("expected ×2");
    twice.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "c2", replicate: [0, 2] }]);
    // "Other count…" asks for a number and fills only that grant's count
    const other = second.submenu.find((i) => i !== "separator" && i.label === "Other count…");
    if (!other || other === "separator") throw new Error("expected Other count");
    other.onClick?.();
    expect(useXPrompt.getState().field).toBe("replicate");
    expect(submitNumericPrompt("5")).toBe(true);
    expect(sent[1]).toEqual({ type: "cast_spell", card_id: "c2", replicate: [0, 5] });
    // a card the server doesn't list gets no replicate entry
    expect(labels(rulesMenu(v.cards.c1!, v, "p1")).some((l) => l.startsWith("Cast with Replicate"))).toBe(false);
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

  it("offers disguise and uses the server's current private face-up cost", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true },
      stats: { cb: { turn_up: [{ method: "disguise", cost: "{R}" }] } } });
    const v = { ...base, cards: { ...base.cards, ch: card("ch", "p1:hand", "codebreaker"),
      cb: { ...card("cb", "p1:battlefield", "codebreaker"), face_down: true } } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      codebreaker: { id: "codebreaker", name: "Fugitive Codebreaker", type_line: "Creature — Human Rogue",
        oracle_text: "Disguise {5}{R}. This cost is reduced by {1} for each instant and sorcery card in your graveyard." } as CardData } });
    const down = rulesMenu(v.cards.ch!, v, "p1").find((i) => i !== "separator" && i.label === "Cast face down (disguise, {3})");
    if (!down || down === "separator") throw new Error("expected disguise cast");
    down.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "ch", face_down: true }]);
    const up = rulesMenu(v.cards.cb!, v, "p1").find((i) => i !== "separator" && i.label === "Turn face up (disguise, {R})");
    if (!up || up === "separator") throw new Error("expected reduced disguise cost");
    up.onClick?.();
    expect(sent[1]).toEqual({ type: "turn_face_up", card_id: "cb", method: "disguise" });
    const changed = { ...v, rules: { ...v.rules!, stats: { cb: { turn_up: [{ method: "disguise" as const, cost: "{3}{R}" }] } } } };
    expect(labels(rulesMenu(changed.cards.cb!, changed, "p1"))).toContain("Turn face up (disguise, {3}{R})");
  });

  it("offers crew and equip lines with trailing restrictions or target cost rules", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true,
      activatable: [{ card_id: "train", ability: 1 }] } });
    const v = { ...base, cards: { ...base.cards, train: card("train", "p1:battlefield", "locomotive"),
      blade: card("blade", "p1:battlefield", "blades") } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      locomotive: { id: "locomotive", name: "Luxurious Locomotive", type_line: "Artifact — Vehicle",
        oracle_text: "Whenever this Vehicle attacks, create a Treasure token for each creature that crewed it this turn.\nCrew 1. Activate only once each turn." } as CardData,
      blades: { id: "blades", name: "Warrior's Blades", type_line: "Artifact — Equipment",
        oracle_text: "When this Equipment enters, it deals 3 damage to any target and you gain 3 life.\nEquipped creature gets +2/+1.\nEquip {3}. This ability costs {1} less to activate for each +1/+1 counter on the creature it targets." } as CardData } });
    const crew = rulesMenu(v.cards.train!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Activate: Crew 1"));
    if (!crew || crew === "separator") throw new Error("expected restricted crew");
    expect(crew.disabled).toBe(false);
    crew.onClick?.();
    expect(sent[0]).toEqual({ type: "activate_ability", card_id: "train", ability: 1 });
    const used = { ...v, rules: { ...v.rules!, hints: { ...v.rules!.hints, activatable: [] } } };
    const disabled = rulesMenu(used.cards.train!, used, "p1").find((i) => i !== "separator" && i.label.startsWith("Activate: Crew 1"));
    expect(disabled && disabled !== "separator" && disabled.disabled).toBe(true);
    const equip = rulesMenu(v.cards.blade!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Activate: Equip {3}"));
    if (!equip || equip === "separator") throw new Error("expected equip with cost rule");
    equip.onClick?.();
    expect(sent[1]).toEqual({ type: "activate_ability", card_id: "blade", ability: 2 });
  });

  it("offers equip planeswalker using its printed ability number", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true } });
    const v = { ...base, cards: { ...base.cards, lx: card("lx", "p1:battlefield", "luxior") } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      luxior: { id: "luxior", name: "Luxior, Giada's Gift", type_line: "Legendary Artifact — Equipment",
        oracle_text: "Equipped creature gets +1/+1 for each counter on it.\nEquipped permanent isn't a planeswalker and is a creature in addition to its other types.\nEquip planeswalker {1}\nEquip {3}" } as CardData } });
    const ability = item(rulesMenu(v.cards.lx!, v, "p1"), "Activate: Equip planeswalker {1}");
    expect(ability.disabled).toBe(false);
    ability.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "lx", ability: 2 }]);
  });

  it("offers a Room's halves to cast, and its locked doors to unlock (709.5)", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true }, stats: { rb: { doors: [1], halves: [{ name: "Grand Entryway", mana_cost: "{1}{W}" }, { name: "Elegant Rotunda", mana_cost: "{2}{W}" }] } } });
    const v = { ...base, cards: { ...base.cards, rh: card("rh", "p1:hand", "room"), rb: card("rb", "p1:battlefield", "room") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        room: { id: "room", name: "Grand Entryway // Elegant Rotunda", layout: "split", type_line: "Enchantment — Room // Enchantment — Room", oracle_text: "",
          faces: [{ name: "Grand Entryway", mana_cost: "{1}{W}", type_line: "Enchantment — Room" }, { name: "Elegant Rotunda", mana_cost: "{2}{W}", type_line: "Enchantment — Room" }] } as unknown as CardData,
      },
    });
    const cast = rulesMenu(v.cards.rh!, v, "p1").filter((i) => i !== "separator" && i.label.startsWith("Cast "));
    expect(cast.map((i) => (i === "separator" ? "" : i.label))).toEqual(["Cast Grand Entryway {1}{W}", "Cast Elegant Rotunda {2}{W}"]);
    const unlock = rulesMenu(v.cards.rb!, v, "p1").filter((i) => i !== "separator" && i.label.startsWith("Unlock "));
    expect(unlock.map((i) => (i === "separator" ? "" : i.label))).toEqual(["Unlock Elegant Rotunda {2}{W}"]); // door 1 is open
    const [door] = unlock;
    if (!door || door === "separator") throw new Error("expected Unlock");
    door.onClick?.();
    expect(sent).toEqual([{ type: "unlock_door", card_id: "rb", door: 2 }]);
  });

  it("offers each half of a split card to cast, and a half's optional cost with that half (709.3, pod audit)", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true, castable: ["sp"],
      optional_costs: { sp: [{ id: "sp:casualty", label: "Casualty 1: sacrifice a creature with power 1 or greater", face: 1 }] } } });
    const v = { ...base, cards: { ...base.cards, sp: card("sp", "p1:hand", "split") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        split: { id: "split", name: "Revival // Revenge", layout: "split", type_line: "Sorcery // Sorcery", oracle_text: "",
          faces: [{ name: "Revival", mana_cost: "{W/B}{W/B}", type_line: "Sorcery" }, { name: "Revenge", mana_cost: "{4}{W}{B}", type_line: "Sorcery" }] } as unknown as CardData,
      },
    });
    const cast = rulesMenu(v.cards.sp!, v, "p1").filter((i): i is Exclude<MenuItem, "separator"> => i !== "separator" && i.label.startsWith("Cast"));
    expect(cast.map((i) => i.label)).toEqual(["Cast Revival {W/B}{W/B}", "Cast Revenge {4}{W}{B}",
      "Cast Revenge and sacrifice a creature with power 1 or greater (Casualty 1)"]);
    cast[1]!.onClick?.();
    cast[2]!.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "sp", face: 1 }, { type: "cast_spell", card_id: "sp", optional_costs: ["sp:casualty"], face: 1 }]);
  });

  it("offers a free cast together with an optional cost when the server lists both (118.9d, pod audit: Deadly Rollick with casualty)", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true, castable: [], free_castable: ["dr"],
      free_optional_costs: { dr: [{ id: "dr:casualty", label: "Casualty 1: sacrifice a creature with power 1 or greater" }] } } });
    const v = { ...base, cards: { ...base.cards, dr: card("dr", "p1:hand", "rollick") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        rollick: { id: "rollick", name: "Deadly Rollick", type_line: "Instant",
          oracle_text: "If you control a commander, you may cast this spell without paying its mana cost.\nExile target creature." } as CardData,
      },
    });
    const cast = rulesMenu(v.cards.dr!, v, "p1").filter((i): i is Exclude<MenuItem, "separator"> => i !== "separator" && i.label.startsWith("Cast"));
    expect(cast.map((i) => i.label)).toEqual(["Cast", "Cast without paying its mana cost",
      "Cast without paying its mana cost and sacrifice a creature with power 1 or greater (Casualty 1)"]);
    expect(cast[0]!.disabled).toBe(true);
    cast[2]!.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "dr", free: true, optional_costs: ["dr:casualty"] }]);
  });

  it("offers the special action that ends a Licid's effect (116.2c) when the server lists its cost", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true }, stats: { lb: { end_cost: "{W}" } } });
    const v = { ...base, cards: { ...base.cards, lb: card("lb", "p1:battlefield", "licid"), lc: card("lc", "p1:battlefield", "licid") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        licid: { id: "licid", name: "Calming Licid", type_line: "Creature — Licid", oracle_text: "{W}, {T}: This creature loses this ability and becomes an Aura enchantment with enchant creature." } as CardData,
      },
    });
    const end = rulesMenu(v.cards.lb!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("End the effect"));
    if (!end || end === "separator") throw new Error("expected the special action");
    expect(end.label).toBe("End the effect ({W}, special action)");
    expect(end.disabled).toBe(false);
    end.onClick?.();
    expect(sent).toEqual([{ type: "end_effect", card_id: "lb" }]);
    expect(rulesMenu(v.cards.lc!, v, "p1").some((i) => i !== "separator" && i.label.startsWith("End the effect"))).toBe(false); // no effect of yours on it
  });

  it("offers your companion's special action (116.2g) with priority, as its Companion line", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, has_priority: true } });
    const v = { ...base, cards: { ...base.cards, lu: card("lu", "p1:companion", "lurrus"), ob: card("ob", "p2:companion", "lurrus") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        lurrus: { id: "lurrus", name: "Lurrus of the Dream-Den", type_line: "Legendary Creature — Cat Nightmare",
          oracle_text: "Companion — Each permanent card in your starting deck has mana value 2 or less. (If this card is your chosen companion, you may put it into your hand from outside the game for {3} as a sorcery.)\nLifelink" } as CardData,
      },
    });
    const take = rulesMenu(v.cards.lu!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Put into your hand"));
    if (!take || take === "separator") throw new Error("expected the companion action");
    expect(take.disabled).toBe(false);
    take.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "lu", ability: 0 }]);
    expect(rulesMenu(v.cards.ob!, v, "p1").some((i) => i !== "separator" && i.label.startsWith("Put into your hand"))).toBe(false); // not yours
    const idle = view({ ...RULES, hints: { ...RULES.hints, has_priority: false } });
    const w = { ...idle, cards: { ...idle.cards, lu: card("lu", "p1:companion", "lurrus") } } as unknown as GameView;
    expect(rulesMenu(w.cards.lu!, w, "p1").find((i) => i !== "separator" && i.label.startsWith("Put into your hand"))).toMatchObject({ disabled: true });
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
      ["Kicked ×1", "Kicked ×2", "Kicked ×3", "Kicked ×4", "Kicked ×5", "Kicked ×6", "Other count…"]);
    const three = multi.submenu?.[2];
    if (!three || three === "separator") throw new Error("expected ×3");
    three.onClick?.();
    expect(sent[1]).toEqual({ type: "cast_spell", card_id: "m1", kicker: 3 });
    const other = multi.submenu?.[6];
    if (!other || other === "separator") throw new Error("expected Other count");
    other.onClick?.();
    expect(useXPrompt.getState()).toMatchObject({ action: { type: "cast_spell", card_id: "m1" }, field: "kicker" });
    expect(sent).toHaveLength(2);
    useXPrompt.setState({ action: null, field: "x_value" });
    expect(labels(rulesMenu(v.cards.c2!, v, "p1")).some((l) => /kicker/i.test(l))).toBe(false);  // no kicker line
  });

  it("offers each kicker cost of \"Kicker {A} and/or {B}\" (wave 50H, 702.33b): the cast's kicker is a mask", () => {
    const base = view({ ...RULES, hints: { castable: ["k1"] } });
    const v = { ...base, cards: { ...base.cards, k1: card("k1", "p1:hand", "battlemage") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        battlemage: { id: "battlemage", name: "Thornscape Battlemage", type_line: "Creature — Elf Wizard",
          oracle_text: "Kicker {R} and/or {W} (You may pay an additional {R} and/or {W} as you cast this spell.)\nWhen this creature enters, if it was kicked with its {R} kicker, it deals 2 damage to any target." } as CardData,
      },
    });
    const both = item(rulesMenu(v.cards.k1!, v, "p1"), "Cast with Kicker {R} and/or {W}");
    expect(both.disabled).toBe(false);
    expect(both.submenu?.map((i) => (i === "separator" ? "—" : i.label))).toEqual(["Kicked with {R}", "Kicked with {W}", "Kicked with both"]);
    both.submenu?.forEach((i) => (i === "separator" ? undefined : i.onClick?.()));
    expect(sent.map((m) => (m as { kicker?: number }).kicker)).toEqual([1, 2, 3]);
  });

  it("offers entwine, prototype, splice and miracle (wave 18E)", () => {
    const base = view({ ...RULES, hints: { castable: ["e1", "p1x", "s1"], miracle: ["w1"] } });
    const v = { ...base, zones: { "p1:hand": ["e1", "p1x", "s1", "s2", "w1"] },
      cards: { ...base.cards, e1: card("e1", "p1:hand", "rust"), p1x: card("p1x", "p1:hand", "goliath"),
        s1: card("s1", "p1:hand", "might"), s2: card("s2", "p1:hand", "ray"), w1: card("w1", "p1:hand", "wrath") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        rust: { id: "rust", name: "Rain of Rust", type_line: "Instant",
          oracle_text: "Choose one —\n• Destroy target artifact.\n• Destroy target land.\nEntwine {3}{R} (Choose both if you pay the entwine cost.)" } as CardData,
        goliath: { id: "goliath", name: "Rust Goliath", type_line: "Artifact Creature — Construct",
          oracle_text: "Prototype {3}{G}{G} — 3/5 (You may cast this spell with different mana cost, color, and size.)\nReach, trample" } as CardData,
        might: { id: "might", name: "Kodama's Might", type_line: "Instant — Arcane",
          oracle_text: "Target creature gets +2/+2 until end of turn.\nSplice onto Arcane {G} (As you cast an Arcane spell, you may reveal this card.)" } as CardData,
        ray: { id: "ray", name: "Glacial Ray", type_line: "Instant — Arcane",
          oracle_text: "Glacial Ray deals 2 damage to any target.\nSplice onto Arcane {1}{R} (As you cast an Arcane spell, you may reveal this card.)" } as CardData,
        wrath: { id: "wrath", name: "Thunderous Wrath", type_line: "Instant", oracle_text: "Thunderous Wrath deals 5 damage to any target.\nMiracle {R}" } as CardData,
      },
    });
    item(rulesMenu(v.cards.e1!, v, "p1"), "Cast with Entwine {3}{R}").onClick?.();
    expect(sent[0]).toEqual({ type: "cast_spell", card_id: "e1", kicker: 1 });
    item(rulesMenu(v.cards.p1x!, v, "p1"), "Cast prototyped: {3}{G}{G} — 3/5").onClick?.();
    expect(sent[1]).toEqual({ type: "cast_spell", card_id: "p1x", prototype: true });
    const splice = item(rulesMenu(v.cards.s1!, v, "p1"), "Cast with splice");
    const ray = splice.submenu?.find((i) => i !== "separator" && i.label === "Splice Glacial Ray");
    if (!ray || ray === "separator") throw new Error("expected a Glacial Ray entry");
    ray.onClick?.();
    expect(sent[2]).toEqual({ type: "cast_spell", card_id: "s1", splice: ["s2"] });
    item(rulesMenu(v.cards.w1!, v, "p1"), "Reveal for miracle").onClick?.();
    expect(sent[3]).toEqual({ type: "miracle_reveal", card_id: "w1" });
  });

  it("lists Suspend X in the hand and waits for X before sending it (wave 50H, 107.3d)", () => {
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "x1", ability: 1, x: true }] } });
    const v = { ...base, cards: { ...base.cards, x1: card("x1", "p1:hand", "chron") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        chron: { id: "chron", name: "Aeon Chronicler", type_line: "Creature — Avatar",
          oracle_text: "Aeon Chronicler's power and toughness are each equal to the number of cards in your hand.\nSuspend X—{X}{3}{U}. X can't be 0." } as CardData,
      },
    });
    useGame.setState({ view: v });
    item(rulesMenu(v.cards.x1!, v, "p1"), "Suspend X—{X}{3}{U}. X can't be 0.").onClick?.();
    expect(useXPrompt.getState().action).toEqual({ type: "activate_ability", card_id: "x1", ability: 1 });
  });

  it("numbers reconfigure's abilities after every printed line (702.151a)", () => {
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "r1", ability: 2 }] } });
    const v = { ...base, cards: { ...base.cards, r1: card("r1", "p1:battlefield", "gear") } } as unknown as GameView;
    useCardCache.setState({
      cards: {
        ...useCardCache.getState().cards,
        gear: { id: "gear", name: "Test Gear", type_line: "Artifact Creature — Equipment", oracle_text: "Reconfigure {2} (Attach or unattach.)\n{1}: Scry 1." } as CardData,
      },
    });
    const attach = item(rulesMenu(v.cards.r1!, v, "p1"), "Reconfigure: attach ({2})");
    expect(attach.disabled).toBe(false);
    attach.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "r1", ability: 2 }]);
    expect(item(rulesMenu(v.cards.r1!, v, "p1"), "Reconfigure: unattach ({2})").disabled).toBe(true);
  });

  it("offers alternative-cost reconfigure attach and unattach with server availability", () => {
    const base = view({ ...RULES, hints: { activatable: [{ card_id: "r1", ability: 2 }] } });
    const v = { ...base, cards: { ...base.cards, r1: card("r1", "p1:battlefield", "ripper") } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      ripper: { id: "ripper", name: "Razorfield Ripper", type_line: "Artifact Creature — Equipment Rhino",
        oracle_text: "Whenever this creature or equipped creature attacks, you get {E}, then it gets +X/+X until end of turn, where X is the amount of {E} you have.\nReconfigure—Pay {2} or {E}{E}{E}. (Attach or unattach.)" } as CardData } });
    const attach = item(rulesMenu(v.cards.r1!, v, "p1"), "Reconfigure: attach (Pay {2} or {E}{E}{E})");
    expect(attach.disabled).toBe(false);
    attach.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "r1", ability: 2 }]);
    expect(item(rulesMenu(v.cards.r1!, v, "p1"), "Reconfigure: unattach (Pay {2} or {E}{E}{E})").disabled).toBe(true);
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

  it("offers energy unearth from the graveyard when the server lists it", () => {
    const base = view({ ...RULES, hints: { ...RULES.hints, activatable: [{ card_id: "col", ability: 2 }] } });
    const v = { ...base, cards: { ...base.cards, col: card("col", "p1:graveyard", "colossus") } } as unknown as GameView;
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      colossus: { id: "colossus", name: "Salvation Colossus", type_line: "Artifact Creature — Construct",
        oracle_text: "Flying, vigilance, trample\nWhenever you attack, other creatures you control get +2/+2 and gain indestructible until end of turn.\nUnearth—Pay eight {E}." } as CardData } });
    const ability = rulesMenu(v.cards.col!, v, "p1").find((i) => i !== "separator" && i.label.startsWith("Activate: Unearth"));
    if (!ability || ability === "separator") throw new Error("expected energy unearth");
    expect(ability.disabled).toBe(false);
    ability.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "col", ability: 2 }]);
    const unpaid = { ...v, rules: { ...v.rules!, hints: { ...v.rules!.hints, activatable: [] } } };
    expect(labels(rulesMenu(unpaid.cards.col!, unpaid, "p1")).some((label) => label.startsWith("Activate"))).toBe(false);
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
    // a cost of exactly two objects ("Sacrifice two other artifacts and/or creatures", 601.2h): none (cancel) or both, never one
    expect([0, 1, 2].map((n) => canSubmitChoice(n, 0, 2, 2))).toEqual([true, false, true]);
    expect(doneLabel(2, 0, 2)).toBe("Done (2)");
    void choose("d1", []);
    expect(sent).toEqual([{ type: "choose", decision_id: "d1", option_ids: [] }]);
  });

  it("answers a divide decision with amounts in the options' order and no option ids", () => {
    void divide("d2", [2, 1]);
    expect(sent).toEqual([{ type: "choose", decision_id: "d2", option_ids: [], amounts: [2, 1] }]);
  });

  it("holds a cast or activation that needs X for the prompt, then sends it with x_value (107.3a)", () => {
    useGame.setState({ view: view({ ...RULES, hints: { castable: ["c2"], x_cast: ["c2"], activatable: [{ card_id: "c3", ability: 0, x: true }, { card_id: "c3", ability: 1 }] } }) });
    void send({ type: "cast_spell", card_id: "c2" });
    void send({ type: "activate_ability", card_id: "c3", ability: 1 }); // no X: goes straight through
    void send({ type: "cast_spell", card_id: "c2", free: true }); // X is 0 when cast for free (107.3b)
    void send({ type: "cast_spell", card_id: "c2", x_value: 4 });
    expect(sent).toHaveLength(3);
    expect(useXPrompt.getState().action).toEqual({ type: "cast_spell", card_id: "c2" });
    void send({ type: "activate_ability", card_id: "c3", ability: 0 });
    expect(useXPrompt.getState().action).toMatchObject({ ability: 0 });
    useXPrompt.setState({ action: null });
    void dropAsIntent(["c2"], { zone: "stack" }); // the drag-to-cast path asks too
    expect(useXPrompt.getState().action).toEqual({ type: "cast_spell", card_id: "c2", ask_optional: true });
  });

  it("validates Other multikicker range and retains its count through a subsequent X prompt", () => {
    useGame.setState({ view: view({ ...RULES, hints: { castable: ["c4"], x_kicker: ["c4"] } }) });
    useXPrompt.setState({ action: { type: "cast_spell", card_id: "c4" }, field: "kicker" });
    const before = useXPrompt.getState();
    expect(submitNumericPrompt("1001")).toBe(false);
    expect(useXPrompt.getState()).toBe(before);
    expect(submitNumericPrompt("21")).toBe(true);
    expect(sent).toHaveLength(0);
    expect(useXPrompt.getState()).toMatchObject({ action: { type: "cast_spell", card_id: "c4", kicker: 21 }, field: "x_value" });
    expect(submitNumericPrompt("3")).toBe(true);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "c4", kicker: 21, x_value: 3 }]);
    expect(useXPrompt.getState().action).toBeNull();
  });

  it("asks for X for an alternative cost or a kicker cost that has {X}, and only then (107.3a, wave 43D)", () => {
    useGame.setState({ view: view({ ...RULES, hints: { castable: ["c2", "c4"], x_cast: ["c2"], x_kicker: ["c4"],
      alt_castable: { c2: [{ id: "c2:1", label: "overload {X}{X}{R}{R}", x: true }, { id: "c2:2", label: "pitch" }] } } }) });
    sent.length = 0;
    useXPrompt.setState({ action: null });
    void send({ type: "cast_spell", card_id: "c2", alt_cost: "c2:2" }); // an alternative cost without X: X is 0 (107.3b)
    void send({ type: "cast_spell", card_id: "c4" }); // not kicked: no X
    expect(sent).toHaveLength(2);
    void send({ type: "cast_spell", card_id: "c4", kicker: 1 });
    expect(useXPrompt.getState().action).toEqual({ type: "cast_spell", card_id: "c4", kicker: 1 });
    useXPrompt.setState({ action: null });
    void send({ type: "cast_spell", card_id: "c2", alt_cost: "c2:1" });
    expect(useXPrompt.getState().action).toEqual({ type: "cast_spell", card_id: "c2", alt_cost: "c2:1" });
    useXPrompt.setState({ action: null });
  });
});

describe("wave 110 follow-ups: library top, Chorus, Leonin Arbiter", () => {
  const labels = (items: MenuItem[]) => items.map((i) => (i === "separator" ? "—" : i.label));
  const withTop = (hints: object, top: string | null) => {
    const base = view({ ...RULES, hints });
    return { ...base, zones: { "p2:library": { count: 30, known: top ? [[0, top]] : [] } },
      cards: { ...base.cards, ...(top ? { [top]: { ...card(top, "p2:library", "bolt"), owner: "p2", controller: "p2" } } : {}) } } as unknown as GameView;
  };

  it("offers another player's top card only when the viewer sees it and the server lists it (Xanathar)", () => {
    useGame.setState({ view: withTop({ castable: ["t1"] }, "t1") });
    const items = libraryTopActions("p2", "p1");
    expect(labels(items)).toEqual(["Cast their top card", "—"]);
    const [cast] = items;
    if (!cast || cast === "separator") throw new Error("expected Cast");
    cast.onClick?.();
    expect(sent).toEqual([{ type: "cast_spell", card_id: "t1" }]);
    useGame.setState({ view: withTop({ castable: [] }, "t1") });
    expect(libraryTopActions("p2", "p1")).toEqual([]); // seen, not castable
    useGame.setState({ view: withTop({ castable: ["t1"] }, null) });
    expect(libraryTopActions("p2", "p1")).toEqual([]); // not seen: no entry
  });

  it("offers plot and a free cast from the top of your library (Fblthp, Temporal Aperture)", () => {
    const base = withTop({ activatable: [{ card_id: "t1", ability: 102 }], free_castable: ["t1"] }, "t1");
    const v = { ...base, zones: { "p1:library": { count: 30, known: [[0, "t1"]] } } } as unknown as GameView;
    useGame.setState({ view: v });
    const items = libraryTopActions("p1", "p1");
    expect(labels(items)).toEqual(["Cast the top card without paying its mana cost", "Plot the top card (special action)", "—"]);
    const plot = items[1];
    if (!plot || plot === "separator") throw new Error("expected Plot");
    plot.onClick?.();
    expect(sent).toEqual([{ type: "activate_ability", card_id: "t1", ability: 102 }]);
  });

  it("asks for the Chorus of the Conclave amount and sends it as chorus", () => {
    const v = view({ ...RULES, hints: { castable: ["c2"], chorus: ["c2"] } });
    useGame.setState({ view: v });
    const chorus = rulesMenu(v.cards.c2!, v, "p1").find((i) => i !== "separator" && i.label === "Cast with Chorus of the Conclave…");
    if (!chorus || chorus === "separator") throw new Error("expected the Chorus entry");
    chorus.onClick?.();
    expect(useXPrompt.getState()).toMatchObject({ action: { type: "cast_spell", card_id: "c2" }, field: "chorus" });
    expect(submitNumericPrompt("3")).toBe(true);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "c2", chorus: 3 }]);
    expect(rulesMenu(v.cards.c1!, v, "p1").some((i) => i !== "separator" && i.label.includes("Chorus"))).toBe(false); // not listed
  });

  it("labels Leonin Arbiter's special action with the server's wording", () => {
    const base = view({ ...RULES, hints: { has_priority: true }, stats: { la: { end_cost: "{2}", end_label: "Ignore Leonin Arbiter until end of turn" } } });
    const v = { ...base, cards: { ...base.cards, la: { ...card("la", "p2:battlefield", "looter"), owner: "p2", controller: "p2" } } } as unknown as GameView;
    expect(labels(rulesMenu(v.cards.la!, v, "p1"))).toContain("Ignore Leonin Arbiter until end of turn ({2}, special action)");
  });
});

describe("turn dial state", () => {
  const OUT = { ...RULES, conceded: [], lost: {}, priority: "p2", decision: null, controlled_by: null };

  it("shows the priority holder while automation runs", () => {
    expect(dialState(view({ ...OUT, priority: "p1" }), "p1")).toEqual({ auto: true, watching: false, mine: true, status: "Your priority" });
    expect(dialState(view(OUT), "p1")).toMatchObject({ auto: true, watching: false, mine: false, status: "Waiting for Bob" });
  });

  it("offers the manual step controls with automation off or paused", () => {
    expect(dialState(view(undefined), "p1")).toMatchObject({ auto: false, watching: false, status: "Manual play: you move the steps" });
    expect(dialState(view({ ...OUT, paused: true }), "p1")).toMatchObject({ auto: false, watching: false, status: "Automation paused: move the steps yourself" });
  });

  it("treats a seated player who conceded or lost as a watcher (800.4a), even while automation is paused", () => {
    const out = { auto: false, watching: true, mine: false, status: "You're out: watching" };
    expect(dialState(view({ ...OUT, conceded: ["p1"] }), "p1")).toEqual(out);
    expect(dialState(view({ ...OUT, lost: { p1: "0 life" } }), "p1")).toEqual(out);
    expect(dialState(view({ ...OUT, conceded: ["p1"], paused: true }), "p1")).toEqual(out);
    expect(dialState(view({ ...OUT, conceded: ["p1"], priority: "p1" }), "p1")).toEqual(out); // never offered PASS
    expect(dialState(view({ ...OUT, conceded: ["p2"] }), "p1")).toMatchObject({ auto: true, watching: false }); // someone else is out
  });

  it("shows spectators the turn without controls", () => {
    expect(dialState({ ...view(OUT), viewer: "__spectator__" } as GameView, "p1")).toEqual({ auto: false, watching: true, mine: false, status: "Watching" });
  });
});
