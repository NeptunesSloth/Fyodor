import { describe, expect, it } from "vitest";
import type { CardData } from "../types/cards";
import type { GameCard, GameView, VisibleCard } from "../types/game";
import {
  biovisionaryNeed, boardLoad, createCount, createTokens, creatureCensus, doppelgang, emptyBoard, fmt, graveyardLands, landTriggerDoubler, landfallApply,
  landfallMaker, landsUntil, project, readBoard, selfCopier, selfCopyApply, selfCopyGrowth, tokenCensus, tokenFactor, tokenSpecFor, totals, underPressure,
  type Board,
} from "./tokenMath";

// Real Oracle text (Scryfall, 2026-11-05)
const O = {
  scute: "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of this creature instead.",
  doublingSeason: "If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.",
  primalVigor: "If one or more tokens would be created, twice that many of those tokens are created instead.\nIf one or more +1/+1 counters would be put on a creature, twice that many +1/+1 counters are put on that creature instead.",
  adrix: "Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.",
  ojerTaq: "Vigilance\nIf one or more creature tokens would be created under your control, three times that many of those tokens are created instead.\nWhen Ojer Taq dies, return it to the battlefield tapped and transformed under its owner's control.",
  chatterfang: "Forestwalk (This creature can't be blocked as long as defending player controls a Forest.)\nIf one or more tokens would be created under your control, those tokens plus that many 1/1 green Squirrel creature tokens are created instead.\n{B}, Sacrifice X Squirrels: Target creature gets +X/-X until end of turn.",
  greenwarden: "Reach (This creature can block creatures with flying.)\nYou may play lands from your graveyard.\nIf a land entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
  chocobo: "You may look at the top card of your library any time.\nYou may play lands and cast Bird spells from the top of your library.\nIf a land or Bird you control entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
  yarok: "Deathtouch, lifelink\nIf a permanent entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
  panharmonicon: "If an artifact or creature entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
  baloths: "Trample\nLandfall — Whenever a land you control enters, create a 4/4 green Beast creature token.",
  provisioner: "Landfall — Whenever a land you control enters, create a Food token or a Treasure token. (Food is an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\" Treasure is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
  springheart: "Bestow {1}{G}\nEnchanted creature gets +1/+1.\nLandfall — Whenever a land you control enters, you may pay {1}{G} if this permanent is attached to a creature you control. If you do, create a token that's a copy of that creature. If you didn't create a token this way, create a 1/1 green Insect creature token.",
  fieldOfTheDead: "This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.",
  cobra: "Landfall — Whenever a land you control enters, add one mana of any color.",
  avenger: "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.",
  tifa: "Trample\nLandfall — Whenever a land you control enters, double Tifa Lockhart's power until end of turn.",
  biowaste: "Oozes you control get +1/+1.\nAt the beginning of your upkeep, if you control a commander, create a token that's a copy of this creature.",
  council: "The \"legend rule\" doesn't apply to creatures you control.\nAt the beginning of combat on your turn, if you've cast a noncreature spell this turn, create a token that's a copy of Council of Reeds.",
  adephage: "Trample\nWhenever this creature deals combat damage to a player, create a token that's a copy of this creature.",
  helm: "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste.\nEquip {5}",
  extravagant: "At the beginning of your upkeep, create a token that's a copy of another target nonland permanent you control.",
  lumra: "Vigilance, reach\nLumra's power and toughness are each equal to the number of lands you control.\nWhen Lumra enters, mill four cards. Then return all land cards from your graveyard to the battlefield tapped.",
  scapeshift: "Sacrifice any number of lands. Search your library for up to that many land cards, put them onto the battlefield tapped, then shuffle.",
  doppelgang: "For each of X target permanents, create X tokens that are copies of that permanent.",
  rite: "Kicker {5}\nCreate a token that's a copy of target creature. If this spell was kicked, create five of those tokens instead.",
  biovisionary: "At the beginning of the end step, if you control four or more creatures named Biovisionary, you win the game.",
};

const board = (b: Partial<Board>): Board => ({ ...emptyBoard(), ...b });

describe("token doublers (616.1)", () => {
  it("reads both doubler wordings, and Ojer Taq's creature-only tripling", () => {
    expect(tokenFactor("Doubling Season", O.doublingSeason, true)).toEqual({ name: "Doubling Season", factor: 2, creatureOnly: false });
    expect(tokenFactor("Adrix and Nev, Twincasters", O.adrix, true)).toMatchObject({ factor: 2, creatureOnly: false });
    expect(tokenFactor("Ojer Taq, Deepest Foundry", O.ojerTaq, true)).toMatchObject({ factor: 3, creatureOnly: true });
  });
  it("an 'under your control' doubler counts only for its controller; Primal Vigor counts for everyone", () => {
    expect(tokenFactor("Adrix and Nev, Twincasters", O.adrix, false)).toBeNull();
    expect(tokenFactor("Primal Vigor", O.primalVigor, false)).toMatchObject({ factor: 2 });
  });
  it("doublers multiply; Chatterfang's Squirrels come first so the doublers double them too", () => {
    const f = [tokenFactor("A", O.adrix, true)!, tokenFactor("P", O.primalVigor, true)!, tokenFactor("O", O.ojerTaq, true)!];
    expect(createTokens(1, true, f)).toEqual({ tokens: 12, extra: 0 });
    expect(createTokens(1, false, f)).toEqual({ tokens: 4, extra: 0 }); // a Treasure: Ojer Taq doesn't apply
    expect(createTokens(1, false, f, 1)).toEqual({ tokens: 4, extra: 12 }); // the Squirrels are creatures
    expect(createCount(5, f)).toBe(60);
  });
  it("doesn't take Chatterfang for a doubler", () => {
    expect(tokenFactor("Chatterfang", O.chatterfang, true)).toBeNull();
  });
});

describe("landfall trigger doublers (603.2d)", () => {
  it("Ancient Greenwarden, Traveling Chocobo and Yarok count; Panharmonicon doesn't (a land isn't an artifact or creature)", () => {
    expect(landTriggerDoubler(O.greenwarden)).toBe(true);
    expect(landTriggerDoubler(O.chocobo)).toBe(true);
    expect(landTriggerDoubler(O.yarok)).toBe(true);
    expect(landTriggerDoubler(O.panharmonicon)).toBe(false);
    expect(landTriggerDoubler(O.doublingSeason)).toBe(false);
  });
});

describe("landfall makers", () => {
  it("reads what each landfall card makes", () => {
    expect(landfallMaker("Rampaging Baloths", O.baloths)).toMatchObject({ kind: "tokens", amount: 1, creature: true, label: "4/4 Beast" });
    expect(landfallMaker("Tireless Provisioner", O.provisioner)).toMatchObject({ kind: "tokens", amount: 1, creature: false, label: "Food or Treasure" });
    expect(landfallMaker("Springheart Nantuko", O.springheart)).toMatchObject({ kind: "tokens", amount: 1, creature: true, label: "1/1 Insect" });
    expect(landfallMaker("Field of the Dead", O.fieldOfTheDead)).toMatchObject({ kind: "tokens", label: "2/2 Zombie", needsSevenNames: true });
    expect(landfallMaker("Lotus Cobra", O.cobra)).toMatchObject({ kind: "mana" });
    expect(landfallMaker("Avenger of Zendikar", O.avenger)).toMatchObject({ kind: "plant_counters", optional: true });
    expect(landfallMaker("Tifa Lockhart", O.tifa)).toMatchObject({ kind: "double_power" });
  });
  it("leaves Scute Swarm to the swarm calculator, and ignores cards without landfall", () => {
    expect(landfallMaker("Scute Swarm", O.scute)).toBeNull();
    expect(landfallMaker("Doubling Season", O.doublingSeason)).toBeNull();
  });
});

describe("Scute Swarm projection", () => {
  it("doubles once you control six lands, one land at a time", () => {
    const steps = project(board({ lands: 5, swarms: 1 }), { lands: 3, together: false });
    expect(steps.map((s) => s.swarms)).toEqual([2, 4, 8]);
    expect(steps.map((s) => s.lands)).toEqual([6, 7, 8]);
  });
  it("makes Insects below six lands (the land that entered counts, 603.4)", () => {
    const [s] = project(board({ lands: 3, swarms: 2 }), { lands: 1, together: false });
    expect(s).toMatchObject({ lands: 4, insects: 2, newSwarms: 0, swarms: 2 });
  });
  it("lands entering at once trigger each swarm once per land, but the new copies don't trigger (603.2c, 603.10)", () => {
    // Lumra returns 10 lands with 3 swarms and Traveling Chocobo out: 3 × 10 × 2 = 60 triggers, 60 new swarms
    const [s] = project(board({ lands: 6, swarms: 3, triggers: 2 }), { lands: 10, together: true });
    expect(s).toMatchObject({ entered: 10, triggers: 60, newSwarms: 60, swarms: 63 });
    // the same 10 lands one at a time grow exponentially: 3 × 3^10
    expect(project(board({ lands: 6, swarms: 3, triggers: 2 }), { lands: 10, together: false }).at(-1)!.swarms).toBe(3 * 3 ** 10);
  });
  it("token doublers multiply every copy (Adrix and Nev with Primal Vigor: 1 → 5)", () => {
    const f = [tokenFactor("A", O.adrix, true)!, tokenFactor("P", O.primalVigor, true)!];
    expect(project(board({ lands: 7, swarms: 1, factors: f }), { lands: 1, together: false })[0]!.swarms).toBe(5);
  });
  it("counts the other landfall makers and their triggers", () => {
    const b = board({
      lands: 7, landNames: 7, triggers: 2,
      makers: [landfallMaker("Rampaging Baloths", O.baloths)!, landfallMaker("Lotus Cobra", O.cobra)!, landfallMaker("Field of the Dead", O.fieldOfTheDead)!,
        landfallMaker("Tifa Lockhart", O.tifa)!, landfallMaker("Avenger of Zendikar", O.avenger)!],
    });
    const t = totals(project(b, { lands: 2, together: false }));
    expect(t.tokens).toEqual({ "4/4 Beast": 4, "2/2 Zombie": 4 });
    expect(t.mana).toBe(4);
    expect(t.triggers).toBe(20);
    const steps = project(b, { lands: 2, together: true });
    expect(steps[0]).toMatchObject({ doublings: 4, plantCounters: 4 });
    // Field of the Dead needs seven names; a maker the player leaves out isn't counted
    expect(totals(project({ ...b, landNames: 6 }, { lands: 1, together: false, skip: ["Rampaging Baloths"] })).tokens).toEqual({});
  });
  it("finds how many lands it takes to reach a count", () => {
    expect(landsUntil(board({ lands: 6, swarms: 1 }), 100)).toBe(7);
    expect(landsUntil(board({ lands: 0, swarms: 1 }), 2)).toBe(6); // five Insects first
    expect(landsUntil(board({ lands: 6, swarms: 0 }), 2)).toBeNull();
  });
});

describe("self-copiers", () => {
  it("finds cards that copy themselves, not the ones that copy something else", () => {
    expect(selfCopier("Biowaste Blob", O.biowaste)).toMatchObject({ when: "at the beginning of your upkeep" });
    expect(selfCopier("Council of Reeds", O.council)).toMatchObject({ when: "at the beginning of combat on your turn" });
    expect(selfCopier("Giant Adephage", O.adephage)).toMatchObject({ when: "whenever this creature deals combat damage to a player" });
    expect(selfCopier("Helm of the Host", O.helm)).toBeNull();
    expect(selfCopier("Extravagant Replication", O.extravagant)).toBeNull();
    expect(selfCopier("Scute Swarm", O.scute)).toBeNull();
  });
  it("grows by 1 + the doubling factor each round", () => {
    expect(selfCopyGrowth(1, 4, 3)).toEqual([5, 25, 125]);
    expect(selfCopyGrowth(2, 1, 2)).toEqual([4, 8]);
  });
});

// --- the board ---

const DATA: Record<string, Partial<CardData>> = {
  scute: { name: "Scute Swarm", type_line: "Creature — Insect", oracle_text: O.scute, power: "1" },
  chocobo: { name: "Traveling Chocobo", type_line: "Creature — Bird", oracle_text: O.chocobo, power: "3" },
  adrix: { name: "Adrix and Nev, Twincasters", type_line: "Legendary Creature — Merfolk Wizard", oracle_text: O.adrix, power: "2" },
  vigor: { name: "Primal Vigor", type_line: "Enchantment", oracle_text: O.primalVigor },
  lumra: { name: "Lumra, Bellow of the Woods", type_line: "Legendary Creature — Elemental Bear", oracle_text: O.lumra, power: "*" },
  baloths: { name: "Rampaging Baloths", type_line: "Creature — Beast", oracle_text: O.baloths, power: "6", related_tokens: [{ id: "beast-tok", name: "Beast", type_line: "Token Creature — Beast" }] },
  provisioner: { name: "Tireless Provisioner", type_line: "Creature — Elf Scout", oracle_text: O.provisioner, power: "3" },
  forest: { name: "Forest", type_line: "Basic Land — Forest", oracle_text: "({T}: Add {G}.)" },
  tomb: { name: "Ancient Tomb", type_line: "Land", oracle_text: "{T}: Add {C}{C}. Ancient Tomb deals 2 damage to you." },
  ashaya: { name: "Ashaya, Soul of the Wild", type_line: "Legendary Creature — Elemental", oracle_text: "Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control are Forest lands in addition to their other types.", power: "*" },
};
const lookup = (id: string) => DATA[id] as CardData | undefined;

function card(id: string, cardId: string, extra: Partial<VisibleCard> = {}): VisibleCard {
  const ctl = extra.controller ?? "p1";
  return { id, owner: ctl, controller: ctl, zone: `${ctl}:battlefield`, face_down: false, card_id: cardId, name: DATA[cardId]?.name ?? cardId, face: 0,
    revealed: false, note: "", is_token: false, x: 0, y: 0, ...extra };
}
function view(cards: GameCard[], hidden: GameCard[] = []): GameView {
  const zones: Record<string, string[]> = {};
  for (const c of [...cards, ...hidden]) (zones[c.zone] ??= []).push(c.id);
  return { cards: Object.fromEntries([...cards, ...hidden].map((c) => [c.id, c])), zones } as unknown as GameView;
}

describe("reading the board", () => {
  it("counts lands, names, swarms (stacks and copies), trigger and token doublers by controller", () => {
    const v = view([
      ...Array.from({ length: 5 }, (_, i) => card(`f${i}`, "forest")),
      card("t", "tomb"),
      card("s1", "scute"),
      card("s2", "scute", { is_token: true, quantity: 3, copy_of: { source_id: "s1", source_name: "Scute Swarm", modifications: "" } }),
      card("c", "chocobo"),
      card("a", "adrix", { controller: "p2" }), // an opponent's Adrix doesn't double your tokens
      card("v", "vigor", { controller: "p2" }), // an opponent's Primal Vigor does
    ], [{ id: "h", owner: "p1", controller: "p1", zone: "p1:hand", face_down: false, hidden: true } as unknown as GameCard]);
    const b = readBoard(v, "p1", lookup);
    expect(b).toMatchObject({ lands: 6, landNames: 2, swarms: 4, triggers: 2, triggerSources: ["Traveling Chocobo"] });
    expect(b.factors.map((f) => f.name)).toEqual(["Primal Vigor"]);
    expect(readBoard(v, "p2", lookup).factors.map((f) => f.name).sort()).toEqual(["Adrix and Nev, Twincasters", "Primal Vigor"]);
  });
  it("Ashaya makes your nontoken creatures lands too", () => {
    const v = view([card("f", "forest"), card("ash", "ashaya"), card("c", "chocobo"), card("s", "scute", { is_token: true })]);
    expect(readBoard(v, "p1", lookup).lands).toBe(3); // the Forest, Ashaya and the Chocobo; not the token
  });
  it("tallies your tokens and creatures, stacks counted per token", () => {
    const goblin = { name: "Goblin", card_id: null, power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin", text: "" };
    const v = view([
      card("g", "", { is_token: true, name: "Goblin", card_id: null, token: goblin, quantity: 10 }),
      card("g2", "", { is_token: true, name: "Goblin", card_id: null, token: goblin, tapped: true }),
      card("c", "chocobo"),
      card("f", "forest"),
    ]);
    expect(tokenCensus(v, "p1")).toEqual([{ name: "Goblin", count: 11, power: 11, untapped: 10 }]);
    expect(creatureCensus(v, "p1", lookup)).toEqual({ count: 12, power: 14, untapped: 11, untappedPower: 13 });
  });
});

it("formats big numbers", () => {
  expect(fmt(1234)).toBe("1,234");
  expect(fmt(3e21)).toBe("3.00e+21");
  expect(fmt(Infinity)).toBe("∞");
});

describe("copies by hand", async () => {
  const { copiesAction } = await import("./cardMenu");
  it("makes one card ×N past 50 copies (or past the collapse setting) when the table may stack", () => {
    expect(copiesAction("c", "p1", 4096, true, 0)).toEqual({ type: "copy_card", card_id: "c", player: "p1", count: 4096, stacked: true });
    expect(copiesAction("c", "p1", 8, true, 5)).toMatchObject({ stacked: true });
    expect(copiesAction("c", "p1", 8, true, 0)).not.toHaveProperty("stacked");
    expect(copiesAction("c", "p1", 40, false, 5)).not.toHaveProperty("stacked"); // automation on: separate copies
  });
});

describe("Lumra and Scapeshift", () => {
  it("counts the land cards in a graveyard (public), nothing else", () => {
    const gy = (id: string, cardId: string) => card(id, cardId, { zone: "p1:graveyard" });
    const v = view([gy("g1", "forest"), gy("g2", "tomb"), gy("g3", "chocobo"), gy("g4", "lumra"), card("f", "forest")],
      [{ id: "h", owner: "p1", controller: "p1", zone: "p1:hand", face_down: false, hidden: true } as unknown as GameCard]);
    expect(graveyardLands(v, "p1", lookup)).toBe(2);
    expect(graveyardLands(v, "p2", lookup)).toBe(0);
  });
  it("Scapeshift sacrifices first: S lands leave, S enter at once, so six lands is checked against L − S + S", () => {
    // 6 lands, 1 swarm, Scapeshift for 5: 1 land left, 5 enter → 6 lands as the triggers resolve: 5 copies
    const [s] = project(board({ lands: 6, swarms: 1 }), { lands: 5, together: true, sacrificed: 5 });
    expect(s).toMatchObject({ lands: 6, newSwarms: 5, insects: 0, swarms: 6 });
    // with 5 lands, Scapeshift for 5 leaves 5: Insects, not copies
    expect(project(board({ lands: 5, swarms: 2 }), { lands: 5, together: true, sacrificed: 5 })[0]).toMatchObject({ lands: 5, insects: 10, newSwarms: 0 });
    // can't sacrifice lands you don't have
    expect(project(board({ lands: 2, swarms: 1 }), { lands: 9, together: true, sacrificed: 9 })[0]).toMatchObject({ lands: 9 });
  });
});

describe("copy spells", () => {
  it("Doppelgang X = 3 makes 3 × 3 copies; a doubler doubles each creation", () => {
    expect(doppelgang(3, [])).toEqual({ perTarget: 3, total: 9, extra: 0 });
    const f = [tokenFactor("Adrix and Nev, Twincasters", O.adrix, true)!, tokenFactor("Ojer Taq", O.ojerTaq, true)!];
    expect(doppelgang(3, f)).toMatchObject({ perTarget: 18, total: 54 });
    expect(doppelgang(3, f, false)).toMatchObject({ total: 18 }); // noncreature permanents: Ojer Taq doesn't apply
  });
  it("Biovisionary: copies still needed, and one-copy spells with doublers", () => {
    expect(biovisionaryNeed(1, 1)).toEqual({ copies: 3, spells: 3 });
    expect(biovisionaryNeed(1, 2)).toEqual({ copies: 3, spells: 2 });
    expect(biovisionaryNeed(5, 4)).toEqual({ copies: 0, spells: 0 });
  });
});

describe("the whole table", () => {
  it("counts objects and what they stand for, the biggest stack and triggers waiting; face-down cards count once, unread", () => {
    const fd = { id: "fd", owner: "p2", controller: "p2", zone: "p2:battlefield", face_down: true, hidden: true } as unknown as GameCard;
    const trig = card("t1", "", { zone: "stack", ability: { text: "Landfall", source_id: "s", source_card_id: null, source_name: "Scute Swarm", kind: "triggered" }, quantity: 3 });
    const spell = card("sp", "forest", { zone: "stack" });
    const v = { ...view([card("a", "forest"), card("s", "scute", { is_token: true, quantity: 4096 }), trig, spell], [fd]), stack: ["t1", "sp"] } as GameView;
    const load = boardLoad(v);
    expect(load).toEqual({ objects: 3, permanents: 4098, biggestStack: 4096, triggers: 3 });
    expect(underPressure(load)).toBe(true); // a ×4,096 stack
    expect(underPressure({ objects: 40, permanents: 40, biggestStack: 6, triggers: 0 })).toBe(false);
    expect(underPressure({ objects: 150, permanents: 150, biggestStack: 1, triggers: 0 })).toBe(true);
  });
});

describe("putting it on the table", () => {
  it("names the token from the card's related tokens, else a plain token; a choice stays the player's", () => {
    expect(tokenSpecFor("4/4 Beast", ["G"], true, [{ id: "beast-tok", name: "Beast" }])).toEqual({ card_id: "beast-tok" });
    expect(tokenSpecFor("2/2 Zombie", ["B"], true)).toEqual({ name: "Zombie", type_line: "Token Creature — Zombie", power: "2", toughness: "2", colors: ["B"] });
    expect(tokenSpecFor("Treasure", [], false)).toMatchObject({ type_line: "Token Artifact — Treasure" });
    expect(tokenSpecFor("Food or Treasure", [], false)).toBeNull();
  });
  it("Scute copies are one stacked copy of a swarm you control; other tokens are create_token, stacked past 100 or the collapse setting", () => {
    const v = view([
      ...Array.from({ length: 6 }, (_, i) => card(`f${i}`, "forest")),
      card("s1", "scute"),
      card("b", "baloths"),
      card("p", "provisioner"),
    ]);
    const b = readBoard(v, "p1", lookup);
    expect(b.makers.find((m) => m.name === "Rampaging Baloths")).toMatchObject({ colors: ["G"], cardId: "baloths" });
    const sum = totals(project(b, { lands: 3, together: false }));
    const plan = landfallApply(b, sum, { player: "p1", collapse: 5, related: (id) => (id ? DATA[id]?.related_tokens ?? [] : []) });
    expect(plan.steps.map((s) => s.action)).toEqual([
      { type: "copy_card", card_id: "s1", player: "p1", count: 7, stacked: true }, // 1 → 2 → 4 → 8
      { type: "create_token", player: "p1", token: { card_id: "beast-tok" }, count: 3, stacked: false },
    ]);
    expect(plan.skipped).toEqual(["3 Food or Treasure: your choice each time, so make them from Create tokens"]);
    // no swarm to copy (the swarms were typed in): said, not sent
    const typed = landfallApply({ ...b, swarmId: null, makers: [] }, sum, { player: "p1", collapse: 0, related: () => [] });
    expect(typed.steps).toEqual([]);
    expect(typed.skipped[0]).toMatch(/no Scute Swarm on your battlefield/);
    // Insects below six lands, 150 of them: one card ×150
    const low = landfallApply(board({ swarms: 150, swarmId: "s1" }), totals(project(board({ lands: 1, swarms: 150 }), { lands: 1, together: false })),
      { player: "p1", collapse: 0, related: () => [] });
    expect(low.steps[0]!.action).toMatchObject({ type: "create_token", count: 150, stacked: true, token: { name: "Insect", power: "1", colors: ["G"] } });
  });
  it("self-copiers: N rounds as one stacked copy", () => {
    expect(selfCopyApply({ name: "Biowaste Blob", count: 1, when: "", id: "bb" }, 2, 3, "p1")).toMatchObject({
      action: { type: "copy_card", card_id: "bb", count: 26, stacked: true }, // 1 → 3 → 9 → 27
    });
    expect(selfCopyApply({ name: "Biowaste Blob", count: 1, when: "" }, 2, 3, "p1")).toBeNull();
  });
});
