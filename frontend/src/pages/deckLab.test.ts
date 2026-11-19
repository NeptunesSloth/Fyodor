import { describe, expect, it } from "vitest";
import type { CardData } from "../types/cards";
import type { DeckEntry } from "../types/decks";
import { atLeast, deckStats, hypergeometric, keepRate, landColors, landDrops, libraryPool, pips, sampleHand } from "./deckLab";

const card = (id: string, type_line: string, extra: Partial<CardData> = {}): CardData => ({
  id, oracle_id: id, name: id, layout: "normal", set_code: "x", set_name: "X", collector_number: "1", rarity: null, mana_cost: null, cmc: 0,
  type_line, oracle_text: null, power: null, toughness: null, loyalty: null, defense: null, colors: [], color_identity: [], keywords: [],
  is_token: false, faces: [], double_faced: false, image_faces: 1, has_image: false, ...extra,
});
const entry = (printing_id: string, quantity: number, section: DeckEntry["section"] = "main") => ({ section, quantity, name: printing_id, printing_id }) as DeckEntry;
const face = (type_line: string, mana_cost: string | null, oracle_text: string | null = null) => ({
  name: type_line, mana_cost, type_line, oracle_text, power: null, toughness: null, loyalty: null, defense: null, colors: null, image_face: 0,
});

const cards: Record<string, CardData> = {
  forest: card("forest", "Basic Land — Forest"),
  temple: card("temple", "Land", { oracle_text: "{T}: Add {G} or {U}." }),
  command: card("command", "Land", { oracle_text: "{T}: Add one mana of any color in your commander's color identity." }),
  wastes: card("wastes", "Basic Land", { oracle_text: "{T}: Add {C}." }),
  bolt: card("bolt", "Instant", { mana_cost: "{R}" }),
  hybrid: card("hybrid", "Creature — Elf", { mana_cost: "{1}{G/U}{G/P}" }),
  smash: card("smash", "Sorcery // Land", { layout: "modal_dfc", faces: [face("Sorcery", "{X}{R}{R}"), face("Land", null, "{T}: Add {R}.")] }),
  cmdr: card("cmdr", "Legendary Creature — Elf", { mana_cost: "{G}{G}" }),
};

describe("deck stats", () => {
  it("counts pips, land sources, types and MDFC land backs", () => {
    const s = deckStats([entry("cmdr", 1, "commander"), entry("forest", 10), entry("temple", 1), entry("command", 1), entry("wastes", 1),
      entry("bolt", 2), entry("hybrid", 1), entry("smash", 1), { section: "main", quantity: 3, name: "Unknown", printing_id: null } as DeckEntry], cards);
    expect(s.library).toBe(20);
    expect(s.missing).toBe(3);
    expect(s.lands).toBe(14);
    expect(s.mdfc).toBe(1);
    // commander GG + bolt 2×R + hybrid G/U, G/P + smash front RR
    expect(s.pips).toEqual({ W: 0, U: 1, B: 0, R: 4, G: 4 });
    expect(s.sources).toEqual({ W: 1, U: 2, B: 1, R: 2, G: 12 });
    expect(s.types).toEqual([{ label: "Creature", count: 1 }, { label: "Instant", count: 2 }, { label: "Sorcery", count: 1 }, { label: "Land", count: 13 }]);
  });

  it("reads pips and land colours", () => {
    expect(pips("{2}{W}{W}{U/B}")).toEqual({ W: 2, U: 1, B: 1, R: 0, G: 0 });
    expect(landColors("Land — Mountain Forest", "")).toEqual(["R", "G"]);
    expect(landColors("Land", "{T}, Sacrifice: Search your library for a basic land card")).toHaveLength(5);
    expect(landColors("Land", "{T}: Add {C}.")).toEqual([]);
  });
});

describe("hypergeometric odds", () => {
  it("sums to one and agrees with known values", () => {
    let total = 0;
    for (let k = 0; k <= 7; k++) total += hypergeometric(99, 37, 7, k);
    expect(total).toBeCloseTo(1, 10);
    expect(hypergeometric(60, 24, 7, 3)).toBeCloseTo(0.3087, 3);
    expect(atLeast(10, 10, 7, 7)).toBe(1);
    expect(atLeast(99, 0, 7, 1)).toBe(0);
  });

  it("is likelier on the draw and less likely for later drops", () => {
    const [t2, t3, t4] = landDrops(99, 37);
    for (const t of [t2!, t3!, t4!]) expect(t.draw).toBeGreaterThan(t.play);
    expect(t2!.play).toBeGreaterThan(t4!.play);
  });
});

describe("sample hands", () => {
  const pool = libraryPool([entry("forest", 40), entry("bolt", 59), entry("smash", 1)], cards);
  it("deals seven from the library, the same for the same seed", () => {
    expect(pool).toHaveLength(100);
    expect(pool.filter((c) => c.land)).toHaveLength(41);
    const a = sampleHand(pool, 42, 0);
    expect(a).toHaveLength(7);
    expect(sampleHand(pool, 42, 0)).toEqual(a);
    expect(sampleHand(pool, 42, 1)).not.toEqual(a);
  });

  it("keeps two to five lands", () => {
    const rate = keepRate(pool, 7, 100);
    expect(rate).toBe(keepRate(pool, 7, 100));
    expect(rate).toBeGreaterThan(60);
    expect(keepRate(libraryPool([entry("bolt", 99)], cards), 7, 20)).toBe(0);
  });
});
