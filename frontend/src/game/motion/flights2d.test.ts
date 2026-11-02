import { describe, expect, it } from "vitest";
import type { GameView } from "../../types/game";
import {
  cardIn, faceIn, lungeOffset, planMotion, rollMs, rollValue, signed, spotSelectors, staggerMs, transformFrom, travelMs, type Box,
} from "./flights2d";
import { tableEvents, type TableEvent } from "./tableEvents";
import { MOTION } from "./timing";

type Card = Record<string, unknown> & { id: string; zone: string; owner: string };
function table(cards: Card[], extra: { libraries?: Record<string, number>; life?: Record<string, number> } = {}): GameView {
  const zones: Record<string, unknown> = {};
  const views: Record<string, unknown> = {};
  for (const c of cards) {
    views[c.id] = { controller: c.owner, face_down: false, ...c };
    if (!c.zone.endsWith(":library")) ((zones[c.zone] ??= []) as string[]).push(c.id);
  }
  for (const [key, count] of Object.entries(extra.libraries ?? {})) zones[key] = { count, known: [] };
  const players = Object.entries(extra.life ?? { p1: 40, p2: 40 }).map(([id, life]) => ({ id, life }));
  return { zones, cards: views, players, viewer: "p1" } as unknown as GameView;
}
const seen = (id: string, zone: string, owner = zone.split(":")[0]!, more: Record<string, unknown> = {}): Card => ({ id, zone, owner, name: id, ...more });
const back = (id: string, zone: string, owner = zone.split(":")[0]!): Card => ({ id, zone, owner, hidden: true, face_down: true });
const hidden = (n: number, zone: string): Card[] => Array.from({ length: n }, (_, i) => back(`hidden:${zone}:${i}`, zone));
const plan = (prev: GameView, next: GameView) => planMotion(tableEvents(prev, next), next, prev);

describe("planMotion: cards fly from where they were", () => {
  it("a card cast from my hand flies face up from the hand to the stack, then to the battlefield", () => {
    const hand = table([seen("bolt", "p1:hand")]);
    const stack = table([seen("bolt", "stack", "p1")]);
    const p = plan(hand, stack);
    expect(p.flights).toEqual([expect.objectContaining({ id: "bolt", from: { zone: "p1:hand", card: "bolt" }, to: { zone: "stack", card: "bolt" }, kind: "card", delay: 0 })]);
    expect(p.flights[0]!.start).toMatchObject({ id: "bolt", zone: "stack" });
    expect(p.flights[0]!.end).toMatchObject({ id: "bolt" });
  });

  it("another player's card cast from their hidden hand starts at that hand as a card back and lands face up", () => {
    const prev = table([...hidden(3, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand"), seen("ring", "stack", "p2")]);
    const [f] = plan(prev, next).flights;
    expect(f).toMatchObject({ id: "ring", from: { zone: "p2:hand" }, to: { zone: "stack", card: "ring" }, start: null, owner: "p2" });
    expect(f!.end).toMatchObject({ id: "ring", name: "ring" });
  });

  it("my draw travels face down out of the library and shows its face as it lands in my hand", () => {
    const prev = table([], { libraries: { "p1:library": 30 } });
    const next = table([seen("elf", "p1:hand")], { libraries: { "p1:library": 29 } });
    const [f] = plan(prev, next).flights;
    expect(f).toMatchObject({ id: "elf", from: { zone: "p1:library" }, to: { zone: "p1:hand", card: "elf" }, start: null, kind: "draw" });
    expect(f!.end).toMatchObject({ id: "elf" });
  });

  it("another player's draw is card backs only, each landing on its own new card back in their hand", () => {
    const prev = table([...hidden(5, "p2:hand")], { libraries: { "p2:library": 30 } });
    const next = table([...hidden(7, "p2:hand")], { libraries: { "p2:library": 28 } });
    const p = plan(prev, next);
    expect(p.flights.map((f) => [f.id, f.from, f.to, f.start, f.end, f.owner, f.kind, f.nth])).toEqual([
      [null, { zone: "p2:library" }, { zone: "p2:hand" }, null, null, "p2", "draw", 1],
      [null, { zone: "p2:library" }, { zone: "p2:hand" }, null, null, "p2", "draw", 0],
    ]);
    expect(p.flights.map((f) => f.delay)).toEqual([0, MOTION.millStagger]);
  });

  it("a mill flies from the library to the graveyard, staggered, turning face up as the cards land", () => {
    const prev = table([], { libraries: { "p2:library": 30 } });
    const next = table([seen("a", "p2:graveyard"), seen("b", "p2:graveyard"), seen("c", "p2:graveyard")], { libraries: { "p2:library": 27 } });
    const p = plan(prev, next);
    expect(p.flights.map((f) => [f.id, f.kind, f.start, f.end?.id, f.delay])).toEqual([
      ["a", "mill", null, "a", 0], ["b", "mill", null, "b", 45], ["c", "mill", null, "c", 90],
    ]);
  });

  it("a card bounced to a hidden hand flies there and turns face down; it is never named at its destination", () => {
    const prev = table([seen("bear", "p2:battlefield"), ...hidden(1, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand")]);
    const [f] = plan(prev, next).flights;
    expect(f).toMatchObject({ id: null, from: { zone: "p2:battlefield", card: "bear" }, to: { zone: "p2:hand" }, end: null });
    expect(f!.start).toMatchObject({ id: "bear" });
  });

  it("a card nobody could see stays a card back the whole way (a face-down permanent put into a library)", () => {
    const prev = table([back("morph", "p2:battlefield")], { libraries: { "p2:library": 10 } });
    const next = table([], { libraries: { "p2:library": 11 } });
    const [f] = plan(prev, next).flights;
    expect(f).toMatchObject({ from: { zone: "p2:battlefield", card: "morph" }, to: { zone: "p2:library" }, start: null, end: null });
  });

  it("a face-down card turned face up as it moves leaves as a back and lands face up (and the reverse)", () => {
    const down = table([back("x", "p2:battlefield")]);
    const up = table([seen("x", "p2:graveyard")]);
    const [f] = plan(down, up).flights;
    expect(f!.start).toBeNull();
    expect(f!.end).toMatchObject({ id: "x" });
    const [g] = plan(up, table([back("x", "p2:exile")])).flights;
    expect(g!.start).toMatchObject({ id: "x" });
    expect(g!.end).toBeNull();
  });

  it("an ability grows out of its source permanent; a token settles in where it is made and fades when it goes", () => {
    const prev = table([seen("krenko", "p1:battlefield"), seen("old", "p1:battlefield", "p1", { is_token: true })]);
    const next = table([seen("krenko", "p1:battlefield"), seen("t1", "p1:battlefield", "p1", { is_token: true }),
      seen("trig", "stack", "p1", { ability: { source_id: "krenko", text: "", source_card_id: null, source_name: "Krenko", kind: "activated" } })]);
    const p = plan(prev, next);
    expect(p.flights).toEqual([expect.objectContaining({ id: "trig", from: { zone: "p1:battlefield", card: "krenko" }, to: { zone: "stack", card: "trig" }, emerge: true })]);
    expect(p.appear).toEqual(["t1"]);
    expect(p.vanish).toEqual([expect.objectContaining({ id: "old", zone: "p1:battlefield" })]);
  });

  it(`more than ${MOTION.maxFlights} cards at once: only the first ones fly, and the group never staggers past ${MOTION.groupMax} ms`, () => {
    const prev = table([], { libraries: { "p1:library": 60 } });
    const next = table(Array.from({ length: 30 }, (_, i) => seen(`c${i}`, "p1:graveyard")), { libraries: { "p1:library": 30 } });
    const p = plan(prev, next);
    expect(p.flights).toHaveLength(MOTION.maxFlights);
    expect(p.flights.map((f) => f.id)).toEqual(Array.from({ length: MOTION.maxFlights }, (_, i) => `c${i}`));
    expect(p.flights[p.flights.length - 1]!.delay).toBeLessThanOrEqual(MOTION.groupMax);
  });
});

describe("planMotion: combat, numbers and the library", () => {
  it("an attacker lunges toward the player or planeswalker it attacks; a blocker toward its attacker", () => {
    const prev = table([seen("bear", "p1:battlefield"), seen("ox", "p1:battlefield"), seen("wall", "p2:battlefield"), seen("pw", "p2:battlefield")]);
    const next = table([
      seen("bear", "p1:battlefield", "p1", { attacking: { kind: "player", id: "p2" } }),
      seen("ox", "p1:battlefield", "p1", { attacking: { kind: "card", id: "pw" } }),
      seen("wall", "p2:battlefield", "p2", { blocking: "bear" }), seen("pw", "p2:battlefield"),
    ]);
    expect(plan(prev, next).lunges).toEqual([
      { id: "bear", toward: { player: "p2" } },
      { id: "ox", toward: { card: "pw" } },
      { id: "wall", toward: { card: "bear" } },
    ]);
  });

  it("an attack with no recorded target doesn't lunge anywhere", () => {
    const events: TableEvent[] = [{ kind: "attack", id: "bear", target: null }];
    expect(planMotion(events, table([]), table([])).lunges).toEqual([]);
  });

  it("damage rises over the creature as −N; life changes as −N / +N by the life total, which rolls from the old total", () => {
    const prev = table([seen("bear", "p1:battlefield")]);
    const next = table([seen("bear", "p1:battlefield", "p1", { damage: 3 })], { life: { p1: 43, p2: 35 } });
    const p = plan(prev, next);
    expect(p.floaters).toEqual([
      { card: "bear", text: "−3", tone: "loss" },
      { player: "p1", text: "+3", tone: "gain" },
      { player: "p2", text: "−5", tone: "loss" },
    ]);
    expect(p.lives).toEqual([{ player: "p1", from: 40, to: 43 }, { player: "p2", from: 40, to: 35 }]);
  });

  it("a shuffle riffles its library once, however many times it was shuffled", () => {
    const events: TableEvent[] = [{ kind: "shuffle", zone: "p1:library", times: 3 }, { kind: "shuffle", zone: "p1:library", times: 1 }];
    expect(planMotion(events, table([]), table([])).shuffles).toEqual(["p1:library"]);
  });
});

describe("the 2D motion's arithmetic", () => {
  it("signs are always text: a real minus sign for a loss, a plus for a gain", () => {
    expect(signed(-3)).toBe("−3");
    expect(signed(5)).toBe("+5");
    expect(signed(0)).toBe("+0");
  });

  it("only a card face up to this viewer has a face; anything else is a back", () => {
    const v = table([seen("a", "p1:hand"), back("b", "p2:battlefield")]);
    expect(faceIn(v, "a")).toMatchObject({ id: "a" });
    expect(faceIn(v, "b")).toBeNull();
    expect(faceIn(v, "nope")).toBeNull();
  });

  it("a group staggers 45 ms a card, never more than 300 ms in all", () => {
    expect(staggerMs(1)).toBe(0);
    expect(staggerMs(3)).toBe(MOTION.millStagger);
    expect(staggerMs(12) * 11).toBeLessThanOrEqual(MOTION.groupMax);
  });

  it("travel grows with the distance but a card's flight and settle stay within 450 ms", () => {
    expect(travelMs(260, 0, 90)).toBe(195);
    expect(travelMs(260, 400, 90)).toBeGreaterThan(travelMs(260, 100, 90));
    expect(travelMs(300, 5000, 90) + 90).toBeLessThanOrEqual(450);
    expect(travelMs(260, 5000, 0)).toBe(338);
  });

  it("a ghost laid out where it lands starts over where it left (FLIP), turned and scaled like the card there", () => {
    const from: Box = { cx: 100, cy: 500, w: 52, h: 73, rot: 0 };
    const to: Box = { cx: 400, cy: 200, w: 104, h: 145, rot: 90 };
    expect(transformFrom(from, to)).toBe("translate(-300px, 300px) rotate(0deg) scale(0.5)");
    expect(transformFrom(from, to, 0.6)).toBe("translate(-300px, 300px) rotate(0deg) scale(0.3)");
  });

  it("a card-shaped box stands in the middle of an anchor that isn't a card", () => {
    expect(cardIn({ cx: 10, cy: 20, w: 300, h: 40, rot: 0 })).toEqual({ cx: 10, cy: 20, w: 40 * (63 / 88), h: 40, rot: 0 });
    expect(cardIn({ cx: 0, cy: 0, w: 12, h: 12, rot: 0 }).h).toBe(28);
  });

  it("a lunge is a short step along the line toward the target, never all the way", () => {
    const up = lungeOffset({ x: 0, y: 500 }, { x: 0, y: 100 }, 140);
    expect(up).toEqual({ dx: 0, dy: -42 });
    const near = lungeOffset({ x: 0, y: 0 }, { x: 30, y: 40 }, 140);
    expect(Math.hypot(near.dx, near.dy)).toBeCloseTo(10, 0);
    const small = lungeOffset({ x: 0, y: 0 }, { x: 1000, y: 0 }, 60);
    expect(small.dx).toBeCloseTo(21.6, 1);
    expect(lungeOffset({ x: 5, y: 5 }, { x: 5, y: 5 }, 100)).toEqual({ dx: 0, dy: 0 });
  });

  it("the life total rolls through whole numbers to its new value in 300–600 ms", () => {
    expect(rollValue(40, 35, 0)).toBe(40);
    expect(rollValue(40, 35, 0.5)).toBe(38);
    expect(rollValue(40, 35, 1)).toBe(35);
    expect(rollMs(1)).toBe(330);
    expect(rollMs(-5)).toBe(450);
    expect(rollMs(40)).toBe(600);
  });

  it("a spot is found by the card's own element first, then by its zone (pile, hand, stack, seat)", () => {
    expect(spotSelectors({ zone: "p1:battlefield", card: "c1" })[0]).toBe('.battlefield [data-card-id="c1"]');
    expect(spotSelectors({ zone: "stack", card: "c1" }).slice(0, 2)).toEqual(['.chain-list [data-card-id="c1"] .chain-thumb', '.chain-list [data-card-id="c1"]']);
    expect(spotSelectors({ zone: "p2:library" })).toEqual(['[data-drop="p2:library"] .pile-card', '.t3d-seat[data-player-id="p2"]']);
    expect(spotSelectors({ zone: "p2:hand" })).toEqual([
      '[data-drop="p2:hand"] .hand-card:last-child', '[data-drop="p2:hand"]', '.t3d-seat[data-player-id="p2"] .seat-hand', '.t3d-seat[data-player-id="p2"]',
    ]);
    expect(spotSelectors({ zone: "p1:graveyard", card: "x" })).toEqual(['.zone-browser [data-card-id="x"]', '[data-drop="p1:graveyard"] .pile-card', '.t3d-seat[data-player-id="p1"]']);
    expect(spotSelectors({ zone: "p1:hand", card: 'a"b' })[0]).toBe('.hand [data-card-id="a\\"b"]');
  });
});
