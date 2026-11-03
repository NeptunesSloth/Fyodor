import { describe, expect, it } from "vitest";
import type { DecisionOptionView, DecisionView } from "../../types/game";
import { boxOf, faceOf, HUB, indexAt, NO_KEYS, placeWheel, ringAngles, TYPE_MS, wheelEligible, wheelFits, wheelKey, wheelLayout, type WheelKeys } from "./wheel";

const opt = (id: string, label = id, extra: Partial<DecisionOptionView> = {}): DecisionOptionView => ({ id, label, card_id: null, ...extra });
const COLORS = ["White", "Blue", "Black", "Red", "Green"].map((c) => opt(c));
const PLAYERS = [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }, { id: "p3", name: "cara", color: "#3a3" }];
const IDS = PLAYERS.map((p) => p.id);

function decision(patch: Partial<DecisionView> = {}): DecisionView {
  return { id: "d1", player: "p1", kind: "choose_one", prompt: "Prism: choose a color", source_id: null, options: COLORS,
    min_choices: 1, max_choices: 1, rememberable: false, cancelable: false, public_choice: true, ...patch };
}

describe("wheelEligible", () => {
  it("offers the wheel for a public single choice among a few options", () => {
    expect(wheelEligible(decision(), IDS)).toBe(true);
    expect(wheelEligible(decision({ options: [opt("heads", "Heads"), opt("tails", "Tails")] }), IDS)).toBe(true);
    expect(wheelEligible(decision({ options: Array.from({ length: 10 }, (_, i) => opt(String(i + 1))) }), IDS)).toBe(true);
    expect(wheelEligible(decision({ options: [opt("p2", "Bob"), opt("p3", "A very long player name indeed, really")] }), IDS)).toBe(true);
  });

  it("keeps the list for a choice the server didn't mark public (private, secret, a target)", () => {
    expect(wheelEligible(decision({ public_choice: undefined }), IDS)).toBe(false);
    expect(wheelEligible(decision({ public_choice: false }), IDS)).toBe(false);
    // other players only ever see "waiting" (no options): never a wheel
    expect(wheelEligible({ id: "d1", player: "p2", kind: "waiting", prompt: "Bob is making a choice", source_id: null }, IDS)).toBe(false);
    expect(wheelEligible(null, IDS)).toBe(false);
  });

  it("keeps the list for other kinds and for several answers", () => {
    for (const kind of ["choose_cards", "confirm", "order", "divide", "reconcile", "manual_resolution", "declare_attackers"] as const) {
      expect(wheelEligible(decision({ kind }), IDS)).toBe(false);
    }
    expect(wheelEligible(decision({ max_choices: 2 }), IDS)).toBe(false);
    expect(wheelEligible(decision({ min_choices: 0 }), IDS)).toBe(false);
  });

  it("needs 2–12 options", () => {
    expect(wheelEligible(decision({ options: [opt("White")] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: [] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: Array.from({ length: 12 }, (_, i) => opt(String(i))) }), IDS)).toBe(true);
    expect(wheelEligible(decision({ options: Array.from({ length: 13 }, (_, i) => opt(String(i))) }), IDS)).toBe(false);
    // every creature type: the list (with its scrolling) is the better tool
    expect(wheelEligible(decision({ options: Array.from({ length: 280 }, (_, i) => opt(`Type${i}`)) }), IDS)).toBe(false);
  });

  it("keeps the list for options naming or looking at cards, typed answers, and long texts", () => {
    expect(wheelEligible(decision({ options: [opt("c1", "Bear", { card_id: "c1" }), opt("c2", "Elf", { card_id: "c2" })] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: [opt("__name__", "Type a card name", { group: "card name" }), opt("x", "Seen", { group: "seen" })] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: [opt("__number__", "Type a number ≥ 0"), opt("pass", "Pass")] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: [opt("a", "Put three +1/+1 counters on Ajani's Pridemate"), opt("b", "Create a token")] }), IDS)).toBe(false);
    expect(wheelEligible(decision({ options: [opt("a", "Same"), opt("a", "Same")] }), IDS)).toBe(false);
  });

  it("keeps the list when the answer has more to it than one option (remember, cancel, a payment)", () => {
    expect(wheelEligible(decision({ rememberable: true }), IDS)).toBe(false);
    expect(wheelEligible(decision({ cancelable: true }), IDS)).toBe(false);
    expect(wheelEligible(decision({ display: { kind: "payment" } }), IDS)).toBe(false);
  });
});

describe("faces", () => {
  it("draws colors with their mana symbol, players with their seat color and initial, numbers and mana as discs", () => {
    expect(faceOf(opt("Blue"), PLAYERS)).toEqual({ kind: "color", symbol: "U" });
    expect(faceOf(opt("W", "White"), PLAYERS)).toEqual({ kind: "color", symbol: "W" });
    expect(faceOf(opt("p3", "cara"), PLAYERS)).toEqual({ kind: "player", initial: "C", color: "#3a3" });
    expect(faceOf(opt("0", "{G}{G}"), PLAYERS)).toEqual({ kind: "mana" });
    expect(faceOf(opt("7"), PLAYERS)).toEqual({ kind: "number" });
    expect(faceOf(opt("heads", "Heads"), PLAYERS)).toEqual({ kind: "text" });
    expect(boxOf({ kind: "number" }, "7").disc).toBe(true);
    expect(boxOf({ kind: "text" }, "Heads").disc).toBe(false);
  });
});

describe("layout", () => {
  const sets: string[][] = [
    ["Heads", "Tails"], ["White", "Blue", "Black", "Red", "Green"],
    ["Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"],
    Array.from({ length: 12 }, (_, i) => String(i)), Array.from({ length: 12 }, (_, i) => `Option number ${i}`),
  ];
  it.each(sets)("keeps every token apart and off the hub (%s …)", (...labels: string[]) => {
    const boxes = labels.map((l) => boxOf(faceOf(opt(l), PLAYERS), l));
    const { points, radius, bounds } = wheelLayout(boxes);
    expect(points).toHaveLength(labels.length);
    points.forEach((p, i) => {
      const b = boxes[i]!;
      expect(Math.hypot(Math.max(Math.abs(p.x) - b.w / 2, 0), Math.max(Math.abs(p.y) - b.h / 2, 0))).toBeGreaterThanOrEqual(HUB);
      points.forEach((q, j) => {
        if (j === i) return;
        const c = boxes[j]!;
        const apart = Math.abs(p.x - q.x) >= (b.w + c.w) / 2 || Math.abs(p.y - q.y) >= (b.h + c.h) / 2;
        expect(apart).toBe(true);
      });
    });
    expect(radius).toBeLessThan(480);
    expect(bounds.left).toBeLessThan(0);
    expect(bounds.bottom).toBeGreaterThan(0);
  });

  it("falls back to the list when the wheel would be too big to aim quickly or doesn't fit the screen", () => {
    const of = (labels: string[]) => wheelLayout(labels.map((l) => boxOf(faceOf(opt(l), PLAYERS), l)));
    const colors = of(COLORS.map((o) => o.label));
    expect(wheelFits(colors, { w: 1920, h: 1080 })).toBe(true);
    expect(wheelFits(colors, { w: 1366, h: 768 })).toBe(true);
    expect(wheelFits(colors, { w: 300, h: 300 })).toBe(false);
    expect(wheelFits(of(Array.from({ length: 12 }, (_, i) => `Option number ${i}`)), { w: 2560, h: 1440 })).toBe(false);
    expect(wheelFits(of(["Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"]), { w: 1366, h: 768 })).toBe(true);
  });

  it("starts at the top and goes clockwise; two options sit left and right", () => {
    expect(ringAngles(4).map((a) => Math.round((a * 180) / Math.PI))).toEqual([-90, 0, 90, 180]);
    expect(ringAngles(2)).toEqual([Math.PI, 0]);
  });

  it("opens at the pointer, moved to stay on screen, or centered after keys", () => {
    const layout = wheelLayout(COLORS.map((o) => boxOf(faceOf(o, PLAYERS), o.label)));
    const screen = { w: 1920, h: 1080 };
    expect(placeWheel({ x: 900, y: 600 }, layout, screen)).toEqual({ x: 900, y: 600 });
    expect(placeWheel(null, layout, screen)).toEqual({ x: 960, y: 540 });
    const corner = placeWheel({ x: 2, y: 1078 }, layout, screen);
    expect(corner.x + layout.bounds.left).toBeGreaterThanOrEqual(12);
    expect(corner.y + layout.bounds.bottom).toBeLessThanOrEqual(1068);
    const top = placeWheel({ x: 900, y: 0 }, layout, screen);
    expect(top.y + layout.bounds.top).toBeGreaterThanOrEqual(12 + 58); // room for the prompt above
  });

  it("aims at the option in the pointer's direction, nothing inside the hub", () => {
    expect(indexAt(0, -100, 4)).toBe(0); // up
    expect(indexAt(100, 10, 4)).toBe(1); // right
    expect(indexAt(-100, 0, 2)).toBe(0); // left of a two-option wheel
    expect(indexAt(5, 5, 4)).toBeNull();
    expect(indexAt(-70, -75, 8)).toBe(7); // up-left
  });
});

describe("wheelKey", () => {
  const press = (keys: WheelKeys, key: string, labels: string[], now = 1000) => wheelKey(keys, key, labels, now);
  const colors = COLORS.map((o) => o.label);

  it("aims by position with digits, then chooses with Enter", () => {
    const r = press(NO_KEYS, "3", colors)!;
    expect(r).toEqual({ keys: { index: 2, typed: "3", at: 1000 }, act: null });
    expect(press(r.keys, "Enter", colors)!.act).toBe("choose");
  });

  it("Enter with nothing aimed isn't the wheel's (a held key never answers); Space stays the table's", () => {
    expect(press(NO_KEYS, "Enter", colors)).toBeNull();
    expect(press({ index: 1, typed: "", at: 0 }, " ", colors)).toBeNull();
  });

  it("Esc falls back to the list", () => {
    expect(press(NO_KEYS, "Escape", colors)!.act).toBe("list");
  });

  it("goes round the ring with the arrows", () => {
    expect(press(NO_KEYS, "ArrowRight", colors)!.keys.index).toBe(0);
    expect(press(NO_KEYS, "ArrowLeft", colors)!.keys.index).toBe(4);
    expect(press({ index: 4, typed: "", at: 0 }, "ArrowDown", colors)!.keys.index).toBe(0);
    expect(press({ index: 0, typed: "", at: 0 }, "ArrowUp", colors)!.keys.index).toBe(4);
    expect(press({ index: 2, typed: "", at: 0 }, "Home", colors)!.keys.index).toBe(0);
    expect(press({ index: 2, typed: "", at: 0 }, "End", colors)!.keys.index).toBe(4);
  });

  it("with two options Left and Right pick that side", () => {
    const two = ["Heads", "Tails"];
    expect(press(NO_KEYS, "ArrowRight", two)!.keys.index).toBe(1);
    expect(press({ index: 1, typed: "", at: 0 }, "ArrowRight", two)!.keys.index).toBe(1);
    expect(press({ index: 1, typed: "", at: 0 }, "ArrowLeft", two)!.keys.index).toBe(0);
    expect(press({ index: 0, typed: "", at: 0 }, "ArrowLeft", two)!.keys.index).toBe(0);
  });

  it("types two digits for options 10–12; 0 is the tenth; a pause starts over", () => {
    const twelve = Array.from({ length: 12 }, (_, i) => `Opt ${String.fromCharCode(65 + i)}`);
    const one = press(NO_KEYS, "1", twelve, 1000)!;
    expect(one.keys.index).toBe(0);
    expect(press(one.keys, "2", twelve, 1000 + TYPE_MS - 1)!.keys.index).toBe(11);
    expect(press(one.keys, "2", twelve, 1000 + TYPE_MS + 1)!.keys.index).toBe(1);
    expect(press(NO_KEYS, "0", twelve)!.keys.index).toBe(9);
    // 1 then 2 on a five-option wheel: no 12th option, so the 2 starts over
    expect(press(press(NO_KEYS, "1", colors)!.keys, "2", colors)!.keys.index).toBe(1);
  });

  it("on a wheel of numbers, digits pick the number itself", () => {
    const zeroToTen = Array.from({ length: 11 }, (_, i) => String(i));
    expect(press(NO_KEYS, "0", zeroToTen)!.keys.index).toBe(0);
    const one = press(NO_KEYS, "1", zeroToTen, 1000)!;
    expect(one.keys.index).toBe(1);
    expect(press(one.keys, "0", zeroToTen, 1200)!.keys.index).toBe(10);
    const oneToTen = Array.from({ length: 10 }, (_, i) => String(i + 1));
    expect(press(NO_KEYS, "3", oneToTen)!.keys.index).toBe(2); // the option "3"
  });

  it("keeps a digit with no option (it is not a camera key while the wheel is open) and ignores other keys", () => {
    expect(press({ index: 1, typed: "", at: 0 }, "9", colors)).toEqual({ keys: { index: 1, typed: "", at: 0 }, act: null });
    expect(press(NO_KEYS, "a", colors)).toBeNull();
    expect(press(NO_KEYS, "Tab", colors)).toBeNull();
  });
});
