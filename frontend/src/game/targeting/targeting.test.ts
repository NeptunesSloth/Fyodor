import { beforeEach, describe, expect, it } from "vitest";
import { useCardCache } from "../../state/cardCache";
import type { CardData } from "../../types/cards";
import type { DecisionView, GameView } from "../../types/game";
import { bow, edgePoint } from "./arrowPath";
import { useTargeting } from "./store";
import { progress, promptSource, sourceOf, step, targetingOf, traySeats } from "./targeting";

const card = (id: string, name: string, zone: string, extra: Record<string, unknown> = {}) => {
  const seat = zone.split(":")[0]!;
  return { id, name, zone, card_id: `pr-${name}`, owner: seat, controller: seat, face: 0, revealed: false, note: "", is_token: false, face_down: false, ...extra };
};

/** Alice (p1) casting at a 3-seat table: two of her creatures, Bob's six Goblins (one tapped, one bigger), a card in Carol's graveyard. */
function table(decision: Partial<DecisionView> | null, extra: Record<string, ReturnType<typeof card>> = {}): GameView {
  const cards: Record<string, ReturnType<typeof card>> = {
    swords: card("swords", "Swords to Plowshares", "p1:hand"),
    grind: card("grind", "Grind // Dust", "p1:hand"),
    bear: card("bear", "Grizzly Bears", "p1:battlefield"),
    elf: card("elf", "Llanowar Elves", "p1:battlefield"),
    ...Object.fromEntries([1, 2, 3, 4, 5, 6].map((n) => [`g${n}`, card(`g${n}`, "Goblin", "p2:battlefield", {
      card_id: null, is_token: true, token: { name: "Goblin", power: "1", toughness: "1", type_line: "Token Creature — Goblin", colors: ["R"] },
      ...(n === 2 ? { tapped: true } : {}), ...(n === 3 ? { counters: { "+1/+1": 1 } } : {}),
    })])),
    zombie: card("zombie", "Gravecrawler", "p3:graveyard"),
    ...extra,
  };
  return {
    viewer: "p1", seat_order: ["p1", "p2", "p3"],
    players: [{ id: "p1", name: "Alice", color: "#c33", life: 40 }, { id: "p2", name: "Bob", color: "#36c", life: 37 }, { id: "p3", name: "Carol", color: "#3a3", life: 22 }],
    cards,
    zones: { "p1:hand": ["swords", "grind"], "p1:battlefield": ["bear", "elf"], "p2:battlefield": ["g1", "g2", "g3", "g4", "g5", "g6"], "p3:graveyard": ["zombie"] },
    stack: [], arrows: [],
    rules: decision ? { decision: { id: "d1", player: "p1", source_id: null, min_choices: 1, max_choices: 1, rememberable: false, cancelable: true, ...decision }, hints: {}, options: {}, stats: {} } : { hints: {}, options: {} },
  } as unknown as GameView;
}

const opts = (...ids: string[]) => ids.map((id) => ({ id, label: id.startsWith("g") ? "Goblin" : id === "p2" ? "Bob" : id === "p3" ? "Carol" : id, card_id: /^p\d$/.test(id) ? null : id, group: null }));

describe("targeting: which decisions the table answers", () => {
  beforeEach(() => {
    useCardCache.setState({ cards: {
      "pr-Grizzly Bears": { id: "pr-Grizzly Bears", name: "Grizzly Bears", type_line: "Creature — Bear", power: "2", toughness: "2" },
      "pr-Llanowar Elves": { id: "pr-Llanowar Elves", name: "Llanowar Elves", type_line: "Creature — Elf Druid", power: "1", toughness: "1" },
    } as unknown as Record<string, CardData> });
  });

  it("a spell's target: the card cast is the source, the words come from what is legal, every option is a candidate", () => {
    const t = targetingOf(table({ kind: "choose_one", prompt: "Choose a target for Swords to Plowshares", options: opts("bear", "elf", "g1", "g2", "g3", "g4", "g5", "g6") }), "p1")!;
    expect(t.source).toBe("swords");
    expect(t.sourceName).toBe("Swords to Plowshares");
    expect(t.instruction).toBe("Choose target creature");
    expect(t.multi).toBe(false);
    expect(t.candidates.map((c) => c.ref)).toEqual(["bear", "elf", "g1", "g2", "g3", "g4", "g5", "g6"]);
    expect(t.candidates[0]!.seat).toBe("p1");
    expect(t.candidates[2]!.seat).toBe("p2");
  });

  it("tells namesakes apart by what differs (tapped, a counter's P/T), and numbers the alike ones, which share a fan", () => {
    const t = targetingOf(table({ kind: "choose_one", prompt: "Choose a target for Swords to Plowshares", options: opts("g1", "g2", "g3", "g4") }), "p1")!;
    expect(t.candidates.map((c) => c.note)).toEqual(["1/1 · 1", "1/1 · tapped", "2/2", "1/1 · 2"]);
    const seats = traySeats(t, table(null), "p1");
    expect(seats.map((s) => s.seat)).toEqual(["p2"]);
    expect(seats[0]!.runs.map((r) => r.map((c) => c.ref))).toEqual([["g1", "g4"], ["g2"], ["g3"]]); // the two untapped 1/1s fan
    // all alike: one fan, numbered
    const alike = targetingOf(table({ kind: "choose_one", prompt: "Choose a target for Swords to Plowshares", options: opts("g1", "g4", "g5", "g6") }), "p1")!;
    expect(alike.candidates.map((c) => c.note)).toEqual(["1", "2", "3", "4"]);
    expect(traySeats(alike, table(null), "p1")[0]!.runs.map((r) => r.length)).toEqual([4]);
  });

  it("several targets: a choose-cards decision with its limits, the split card's half named as the source", () => {
    const t = targetingOf(table({ kind: "choose_cards", prompt: "Choose up to 2 targets for Grind", min_choices: 0, max_choices: 2, options: opts("bear", "g3") }), "p1")!;
    expect(t.multi).toBe(true);
    expect([t.min, t.max]).toEqual([0, 2]);
    expect(t.source).toBe("grind");
    expect(t.instruction).toBe("Choose up to two target creatures");
    expect(progress(1, t)).toBe("1 of 2 chosen");
  });

  it("players: their plaques are the candidates, in the words of the rules; with creatures it is either", () => {
    const players = targetingOf(table({ kind: "choose_one", prompt: "Contagion Engine: choose a target", options: opts("p2", "p3") }), "p1")!;
    expect(players.candidates.map((c) => [c.kind, c.ref, c.seat])).toEqual([["player", "p2", "p2"], ["player", "p3", "p3"]]);
    expect(players.instruction).toBe("Choose target player");
    expect(players.sourceName).toBe("Contagion Engine");
    const any = targetingOf(table({ kind: "choose_one", prompt: "Choose a target for Lightning Bolt", options: opts("bear", "p2") }), "p1")!;
    expect(any.instruction).toBe("Choose target creature or player");
  });

  it("the same target for every identical trigger: the board picks one, the bar offers \"Bob — same for all 68\" (playtest B3)", () => {
    const same = [{ id: "all:p2", label: "Bob — same for all 68", card_id: null, group: null }, { id: "all:p3", label: "Carol — same for all 68", card_id: null, group: null }];
    const t = targetingOf(table({ kind: "choose_one", prompt: "Blood Artist: choose a target", options: [...opts("p2", "p3"), ...same] }), "p1")!;
    expect(t.candidates.map((c) => c.ref)).toEqual(["p2", "p3"]);
    expect(t.others.map((o) => o.label)).toEqual(["Bob — same for all 68", "Carol — same for all 68"]);
  });

  it("a card in a graveyard, and a sacrifice (a choice that isn't a target)", () => {
    const gy = targetingOf(table({ kind: "choose_one", prompt: "Choose a target for Reanimate", options: opts("zombie") }), "p1")!;
    expect(gy.instruction).toBe("Choose target card in a graveyard");
    expect(gy.candidates[0]).toMatchObject({ where: "graveyard", seat: "p3" });
    const sac = targetingOf(table({ kind: "choose_cards", prompt: "Fleshbag Marauder: sacrifice 1 (creature)", cancelable: false, options: opts("bear", "elf") }), "p1")!;
    expect(sac.instruction).toBe("Sacrifice a creature");
    expect(sac.multi).toBe(true);
  });

  it("leaves the panel to everything else: someone else's choice, words, names, numbers, payments, remembered answers, hidden highlights", () => {
    const words = [{ id: "White", label: "White", card_id: null }, { id: "Blue", label: "Blue", card_id: null }];
    expect(targetingOf(table({ kind: "choose_one", prompt: "Choose a color", options: words }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "choose_one", prompt: "x", options: opts("bear"), player: "p2" }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "choose_one", prompt: "x", options: [{ id: "__name__", label: "", card_id: null }] }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "choose_cards", prompt: "x", options: opts("bear"), display: { kind: "payment" } }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "choose_one", prompt: "x", options: opts("bear"), rememberable: true }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "confirm", prompt: "x", options: opts("bear") }), "p1")).toBeNull();
    expect(targetingOf(table({ kind: "choose_one", prompt: "x", options: [...opts("bear"), { id: "seen", label: "x", card_id: "elf", group: "seen" }] }), "p1")).toBeNull();
  });
});

describe("targeting: the source, keys and arrows", () => {
  it("reads the source's name from the prompt", () => {
    expect(promptSource("Choose a target for Swords to Plowshares")).toBe("Swords to Plowshares");
    expect(promptSource("Choose a target for Cankerbloom (mode 1)")).toBe("Cankerbloom");
    expect(promptSource("Choose 2 targets for Role Reversal (group 1 of 2)")).toBe("Role Reversal");
    expect(promptSource("Fleshbag Marauder: sacrifice 1 (creature)")).toBe("Fleshbag Marauder");
    expect(promptSource("Sacrifice a creature")).toBeNull();
  });

  it("prefers the card I just selected when I hold two of it; the server's own source wins", () => {
    const v = table(null, { swords2: card("swords2", "Swords to Plowshares", "p1:hand") });
    (v.zones as Record<string, string[]>)["p1:hand"] = ["swords", "swords2"];
    const d = { id: "d", player: "p1", kind: "choose_one", prompt: "Choose a target for Swords to Plowshares", source_id: null } as DecisionView;
    expect(sourceOf(v, d, "p1")).toBe("swords");
    expect(sourceOf(v, d, "p1", ["swords2"])).toBe("swords2");
    expect(sourceOf(v, { ...d, source_id: "bear" }, "p1")).toBe("bear");
  });

  it("steps through candidates with wrap-around (Tab, arrows)", () => {
    expect(step(["a", "b", "c"], null, 1)).toBe("a");
    expect(step(["a", "b", "c"], null, -1)).toBe("c");
    expect(step(["a", "b", "c"], "c", 1)).toBe("a");
    expect(step(["a", "b", "c"], "a", -1)).toBe("c");
    expect(step([], null, 1)).toBeNull();
  });

  it("ends the arrow on the target's edge facing the source, bowing upward", () => {
    const box = { left: 100, top: 100, width: 60, height: 84 };
    const end = edgePoint(box, { x: 130, y: 400 }, 0);
    expect(end).toEqual({ x: 130, y: 184 });
    const side = edgePoint(box, { x: 400, y: 142 }, 0);
    expect(side).toEqual({ x: 160, y: 142 });
    const { d, mid } = bow({ x: 0, y: 500 }, { x: 400, y: 500 });
    expect(d.startsWith("M0,500 Q200,")).toBe(true);
    expect(mid.y).toBeLessThan(500); // up the screen
  });
});

describe("targeting: choosing several", () => {
  beforeEach(() => useTargeting.getState().reset("d1"));

  it("toggles picks in order, stops at the most allowed, and with one allowed a new pick replaces the old", () => {
    const s = useTargeting.getState;
    s().toggle("d1", { opt: "a", ref: "a" }, 2);
    s().toggle("d1", { opt: "b", ref: "b" }, 2);
    s().toggle("d1", { opt: "c", ref: "c" }, 2);
    expect(s().picked.map((p) => p.ref)).toEqual(["a", "b"]);
    s().toggle("d1", { opt: "a", ref: "a" }, 2);
    expect(s().picked.map((p) => p.ref)).toEqual(["b"]);
    s().toggle("d1", { opt: "c", ref: "c" }, 1);
    expect(s().picked.map((p) => p.ref)).toEqual(["c"]);
    s().toggle("d2", { opt: "x", ref: "x" }, 3); // a new decision starts empty
    expect(s().picked.map((p) => p.ref)).toEqual(["x"]);
  });
});
