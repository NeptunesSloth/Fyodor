import { describe, expect, it } from "vitest";
import type { CardData } from "../types/cards";
import {
  CANVAS_TIER, CARD_H, costWidth, estimateMeasure, fieldColours, fitLabel, fitText, frameKey, GLYPHS, glyphKind, layoutProxy, luminance, mix,
  PALETTE, proxyColours, proxyFace, stripReminders, textHeight, TIERS, tokenize, wrap, type TextBox,
} from "./proxy";

const card = (over: Partial<CardData>): CardData => ({
  id: "x", oracle_id: "o", name: "Card", layout: "normal", set_code: "one", set_name: "Set", collector_number: "12", rarity: "rare",
  mana_cost: null, cmc: 0, type_line: null, oracle_text: null, power: null, toughness: null, loyalty: null, defense: null,
  colors: [], color_identity: [], keywords: [], is_token: false, faces: [], double_faced: false, image_faces: 1, has_image: false, ...over,
});

const ATRAXA = "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)";

describe("frame and icon", () => {
  it("picks the printed frame from type and colours", () => {
    expect(frameKey("Instant", ["U"])).toBe("U");
    expect(frameKey("Legendary Creature — Phyrexian Angel Horror", ["W", "U", "B", "G"])).toBe("M");
    expect(frameKey("Artifact", [])).toBe("A");
    expect(frameKey("Artifact Creature — Golem", ["B"])).toBe("B");
    expect(frameKey("Legendary Planeswalker — Karn", [])).toBe("C");
    expect(frameKey("Land — Forest Dryad", ["G"])).toBe("L");
    expect(frameKey("Sorcery", null)).toBe("C");
  });

  it("shows the most telling type, ignoring subtypes", () => {
    expect(glyphKind("Artifact Creature — Thopter")).toBe("creature");
    expect(glyphKind("Legendary Planeswalker — Karn")).toBe("planeswalker");
    expect(glyphKind("Battle — Siege")).toBe("battle");
    expect(glyphKind("Artifact Land")).toBe("land");
    expect(glyphKind("Kindred Instant — Elf")).toBe("instant");
    expect(glyphKind("Enchantment — Aura")).toBe("enchantment");
    expect(glyphKind("Artifact — Equipment")).toBe("artifact");
    expect(glyphKind("Instant // Instant")).toBe("instant");
    expect(glyphKind("Unknown card")).toBe("other");
    expect(glyphKind("Creature — Land Elemental")).toBe("creature"); // "Land" as a subtype isn't the land icon
  });

  it("gives every icon a path", () => {
    for (const k of ["creature", "planeswalker", "battle", "land", "instant", "sorcery", "artifact", "enchantment", "other"] as const) {
      expect(GLYPHS[k]).toMatch(/^M[\d. ]/);
    }
  });

  it("colours a land's art window with what it makes, in WUBRG order", () => {
    expect(fieldColours("Basic Land — Island", [], ["U"])).toEqual(["U"]);
    expect(fieldColours("Land — Island Plains", [], [])).toEqual(["W", "U"]);
    expect(fieldColours("Land", [], ["U", "W"])).toEqual(["W", "U"]);
    expect(fieldColours("Instant", ["R", "U"])).toEqual(["U", "R"]);
    expect(fieldColours("Artifact", [])).toEqual([]);
  });
});

describe("proxyFace", () => {
  it("reads a normal card", () => {
    const p = proxyFace(card({ name: "Atraxa, Praetors' Voice", mana_cost: "{G}{W}{U}{B}", type_line: "Legendary Creature — Phyrexian Angel Horror", oracle_text: ATRAXA, power: "4", toughness: "4", colors: ["W", "U", "B", "G"] }));
    expect(p).toMatchObject({ name: "Atraxa, Praetors' Voice", cost: "{G}{W}{U}{B}", frame: "M", kind: "creature", stat: { text: "4/4", kind: "pt" } });
  });

  it("prints one face of a double-faced card, without the front's stats on the back", () => {
    const c = card({
      name: "Front // Back", double_faced: true, power: null,
      faces: [
        { name: "Front", mana_cost: "{1}{W}", type_line: "Creature — Human", oracle_text: "A", power: "2", toughness: "2", loyalty: null, defense: null, colors: ["W"], image_face: 0 },
        { name: "Back", mana_cost: "", type_line: "Enchantment", oracle_text: "B", power: null, toughness: null, loyalty: null, defense: null, colors: ["B"], image_face: 1 },
      ],
    });
    expect(proxyFace(c, 0)).toMatchObject({ name: "Front", stat: { text: "2/2" }, frame: "W" });
    expect(proxyFace(c, 1)).toMatchObject({ name: "Back", stat: null, frame: "B", kind: "enchantment" });
  });

  it("prints both halves of a split card that has no combined text", () => {
    const c = card({
      name: "Fire // Ice", mana_cost: "{1}{R} // {1}{U}", type_line: "Instant // Instant", colors: ["U", "R"],
      faces: [
        { name: "Fire", mana_cost: "{1}{R}", type_line: "Instant", oracle_text: "Fire deals 2 damage.", power: null, toughness: null, loyalty: null, defense: null, colors: ["R"], image_face: 0 },
        { name: "Ice", mana_cost: "{1}{U}", type_line: "Instant", oracle_text: "Tap target permanent.", power: null, toughness: null, loyalty: null, defense: null, colors: ["U"], image_face: 0 },
      ],
    });
    expect(proxyFace(c).text).toBe("Fire {1}{R}\nFire deals 2 damage.\nIce {1}{U}\nTap target permanent.");
  });

  it("reads loyalty, defense and custom tokens", () => {
    expect(proxyFace(card({ type_line: "Legendary Planeswalker — Karn", loyalty: "6" })).stat).toEqual({ text: "6", kind: "loyalty" });
    expect(proxyFace(card({ type_line: "Battle — Siege", defense: "5" })).stat).toEqual({ text: "5", kind: "defense" });
    const t = proxyFace(undefined, 0, { name: "Soldier", type_line: "Token Creature — Soldier", power: "1", toughness: "1", colors: ["W"] });
    expect(t).toMatchObject({ name: "Soldier", frame: "W", kind: "creature", stat: { text: "1/1" }, text: "" });
    expect(proxyFace(undefined, 0, undefined, "Mystery").name).toBe("Mystery");
  });
});

describe("colour", () => {
  it("mixes and measures", () => {
    expect(mix("#000000", "#ffffff", 0.5)).toBe("#808080");
    expect(luminance("#ffffff")).toBeCloseTo(1);
    expect(luminance("#000000")).toBe(0);
  });

  it("splits a two-colour art window and keeps every icon legible on its field", () => {
    expect(proxyColours({ frame: "M", field: ["W", "U"] }).field).toEqual([PALETTE.W.field, PALETTE.U.field]);
    expect(proxyColours({ frame: "M", field: ["W", "U", "B"] }).field).toEqual([PALETTE.M.field, PALETTE.M.field]);
    for (const k of Object.keys(PALETTE) as (keyof typeof PALETTE)[]) {
      const c = proxyColours({ frame: k, field: [] });
      const [hi, lo] = [luminance(c.field[0]), luminance(c.glyph)].sort((a, b) => b - a);
      expect((hi! + 0.05) / (lo! + 0.05), k).toBeGreaterThan(1.25);
      // the bars carry dark ink: they must stay pale whatever the frame
      expect(luminance(c.bar), k).toBeGreaterThan(0.5);
    }
  });
});

describe("text", () => {
  it("tokenizes words, symbols and reminder text", () => {
    const t = tokenize("{T}: Add {G}. (Mana!)");
    expect(t.map((x) => x.t)).toEqual(["sym", "word", "space", "word", "space", "sym", "word", "space", "word"]);
    expect(t.filter((x) => x.rem).map((x) => (x.t === "word" ? x.s : x.t))).toEqual(["(Mana!)"]);
    expect(tokenize("a (b c) d").filter((x) => x.t === "word").map((x) => x.rem)).toEqual([false, true, true, false]);
  });

  it("strips reminder text", () => {
    expect(stripReminders("Flying (It can't be blocked.)\n(Only reminder.)\nTrample")).toBe("Flying\nTrample");
  });

  it("wraps greedily, the first line beside the cost", () => {
    const m = (s: string) => s.length; // 1em per character
    const lines = wrap(tokenize("aaa bbb ccc"), 1, [7, 3], m);
    expect(lines.map((l) => l.tokens.filter((t) => t.t === "word").map((t) => (t.t === "word" ? t.s : "")).join(" "))).toEqual(["aaa bbb", "ccc"]);
    expect(wrap(tokenize("aaaaaaaa"), 1, [3], m)).toHaveLength(1); // one long word overflows rather than vanishing
  });

  const box: TextBox = { width: 80, base: 40, max: 70, padY: 2, foot: 0, sizes: { max: 6, comfort: 5, min: 4 }, lh: 1.2, gap: 0.3 };

  it("keeps short text big in the usual box", () => {
    const f = fitText("Flying", box, estimateMeasure);
    expect(f).toMatchObject({ size: 6, box: 40, fits: true, reminders: true });
  });

  it("shrinks to the comfortable size, then grows the box, then drops reminders, then fades", () => {
    const medium = fitText(ATRAXA, box, estimateMeasure);
    expect(medium.fits).toBe(true);
    expect(medium.size).toBeLessThanOrEqual(6);
    if (medium.size < box.sizes.comfort) expect(medium.box).toBe(box.base);
    const long = `${ATRAXA}\n${ATRAXA}\n${ATRAXA}`;
    const grown = fitText(long, box, estimateMeasure);
    expect(grown.box).toBeGreaterThan(box.base);
    expect(grown.box).toBeLessThanOrEqual(box.max);
    const huge = fitText(Array(12).fill(ATRAXA).join("\n"), box, estimateMeasure);
    expect(huge).toMatchObject({ size: 4, box: 70, fits: false, reminders: false });
    // whatever fits really fits
    for (const f of [medium, grown]) {
      expect(textHeight(f.lines, f.size, box.lh, box.gap) + box.padY * 2).toBeLessThanOrEqual(f.box + 1e-6);
      for (const p of f.lines) for (const l of p) expect(l.width).toBeLessThanOrEqual(box.width + 1e-6);
    }
  });

  it("fits a label in its lines or reports it clipped", () => {
    expect(fitLabel("Island", [80], 1, 8, 6, estimateMeasure, "name")).toMatchObject({ size: 8, fits: true });
    const long = fitLabel("Elesh Norn, Mother of Machines", [80], 3, 13.5, 9.5, estimateMeasure, "name");
    expect(long.fits).toBe(true);
    expect(long.lines.length).toBeLessThanOrEqual(3);
    expect(fitLabel("Supercalifragilisticexpialidocious", [20], 1, 8, 6, estimateMeasure, "name").fits).toBe(false);
  });

  it("measures a cost, split costs included", () => {
    expect(costWidth("", 8)).toBe(0);
    expect(costWidth("{1}{R} // {1}{U}", 8)).toBeGreaterThan(costWidth("{1}{R}{1}{U}", 8));
  });
});

describe("layoutProxy", () => {
  const atraxa = proxyFace(card({ name: "Atraxa, Praetors' Voice", mana_cost: "{G}{W}{U}{B}", type_line: "Legendary Creature — Phyrexian Angel Horror", oracle_text: ATRAXA, power: "4", toughness: "4", colors: ["W", "U", "B", "G"] }));
  const island = proxyFace(card({ name: "Island", type_line: "Basic Land — Island", oracle_text: "({T}: Add {U}.)" }));
  const vanilla = proxyFace(card({ name: "Grizzly Bears", mana_cost: "{1}{G}", type_line: "Creature — Bear", power: "2", toughness: "2", colors: ["G"] }));

  for (const [tierName, tier] of [["full", TIERS.full], ["small", TIERS.small], ["canvas", CANVAS_TIER]] as const) {
    it(`stacks name, art window, type and text inside the card (${tierName})`, () => {
      for (const p of [atraxa, island, vanilla]) {
        const L = layoutProxy(p, tier, estimateMeasure);
        expect(L.field.top).toBeGreaterThan(tier.border);
        expect(L.field.h).toBeGreaterThanOrEqual(tier.text.minField - 1e-6);
        const bottom = L.field.top + L.field.h + tier.gap + tier.type.h + tier.gap + L.text.box;
        expect(bottom).toBeCloseTo(CARD_H - tier.border - tier.bottom, 5);
        expect(L.name.lines.length).toBeLessThanOrEqual(tier.name.lines);
      }
    });
  }

  it("gives a card without rules text a bigger art window", () => {
    const bear = layoutProxy(vanilla, TIERS.small, estimateMeasure);
    const isl = layoutProxy(island, TIERS.small, estimateMeasure);
    expect(bear.text.box).toBeLessThan(isl.text.box);
    expect(bear.field.h).toBeGreaterThan(isl.field.h);
  });

  it("wraps a long name under the cost at the small size", () => {
    const L = layoutProxy(atraxa, TIERS.small, estimateMeasure);
    expect(L.name.lines.length).toBe(2);
    expect(L.name.fits).toBe(true);
  });
});
