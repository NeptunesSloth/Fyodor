import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { GameView } from "../types/game";
import { MOTION } from "../game/motion/timing";
import { tableEvents, type TableEvent } from "../game/motion/tableEvents";
import {
  arcLift, combatStrikes, cubicBezier, easeOut, flightMs, floaterAt, hiddenZone, lungeAt, MINUS, otherHandSpot, planMotion, riffleAt,
  standInOpacity, turnAt, type SceneFacts,
} from "./flights3d";
import { CARD_H, MAT_D, onBattlefield, plaqueSpot, seats, toWorld, type Seat } from "./layout";
import { fitCamera, seatElevation, seatPoints, tableRect, viewDir } from "./framing";

type Card = Record<string, unknown> & { id: string; zone: string; owner: string };
/** A table as p1 is sent it (as in tableEvents.test.ts): ``zones`` lists ids, a library its size. */
function table(cards: Card[], extra: { libraries?: Record<string, number>; phase?: string } = {}): GameView {
  const zones: Record<string, unknown> = {};
  const views: Record<string, unknown> = {};
  for (const c of cards) {
    views[c.id] = { controller: c.owner, face_down: false, ...c };
    if (!c.zone.endsWith(":library")) ((zones[c.zone] ??= []) as string[]).push(c.id);
  }
  for (const [key, count] of Object.entries(extra.libraries ?? {})) zones[key] = { count, known: [] };
  return { zones, cards: views, players: [{ id: "p1", life: 40 }, { id: "p2", life: 40 }], turn: { number: 1, active_player: "p1", phase: extra.phase ?? "main1" } } as unknown as GameView;
}
const seen = (id: string, zone: string, owner = zone.split(":")[0]!, more: Record<string, unknown> = {}): Card => ({ id, zone, owner, name: id, ...more });
const hidden = (n: number, zone: string): Card[] =>
  Array.from({ length: n }, (_, i) => ({ id: `hidden:${zone}:${i}`, zone, owner: zone.split(":")[0]!, hidden: true }));

/** What the 3D table shows after laying out ``next``: battlefields, the stack, command zones and each pile's top card. */
function facts(next: GameView, prevShown: string[] = [], fresh?: string[]): SceneFacts {
  const shown = new Set<string>();
  for (const [key, ids] of Object.entries(next.zones)) {
    if (!Array.isArray(ids) || !ids.length) continue;
    if (key.endsWith(":battlefield") || key === "stack" || key.endsWith(":command")) ids.forEach((id) => shown.add(id));
    else if (key.endsWith(":graveyard") || key.endsWith(":exile")) shown.add(ids[ids.length - 1]!);
  }
  const before = new Set(prevShown);
  return {
    me: "p1",
    shows: (id) => shown.has(id),
    fresh: (id) => shown.has(id) && (fresh ? fresh.includes(id) : !before.has(id)),
    had: (id) => before.has(id) && !shown.has(id),
  };
}
const plan = (prev: GameView, next: GameView, prevShown: string[] = []) => planMotion(tableEvents(prev, next), next, prev, facts(next, prevShown));

describe("3D table motion: what flies where", () => {
  it("another player's card cast from their hidden hand leaves their hand as a back and turns face up", () => {
    const prev = table([...hidden(3, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand"), seen("ring", "stack", "p2")]);
    expect(plan(prev, next).flights).toEqual([{ card: "ring", owner: "p2", from: { zone: "p2:hand" }, turn: "up", delay: 0, ms: MOTION.cardTravel }]);
  });

  it("my own cast starts at my hand (I see it: no turn); a card already on the table flies from where it is", () => {
    const prev = table([seen("bolt", "p1:hand"), seen("bear", "p1:battlefield")]);
    const next = table([seen("bolt", "stack", "p1"), seen("bear", "p1:graveyard")]);
    expect(plan(prev, next, ["bear"]).flights).toEqual([
      { card: "bolt", owner: "p1", from: { zone: "p1:hand" }, delay: 0, ms: MOTION.cardTravel },
      { card: "bear", owner: "p1", from: { card: "bear" }, delay: MOTION.millStagger, ms: MOTION.cardTravel },
    ]);
  });

  it("my draw travels face down to my hand; another player's draw is card backs to their fan, one after another", () => {
    const prev = table([...hidden(7, "p2:hand")], { libraries: { "p1:library": 30, "p2:library": 30 } });
    const next = table([seen("elf", "p1:hand"), ...hidden(9, "p2:hand")], { libraries: { "p1:library": 29, "p2:library": 28 } });
    expect(plan(prev, next).flights).toEqual([
      { look: { back: "p1" }, owner: "p1", from: { zone: "p1:library" }, to: { zone: "p1:hand" }, delay: 0, ms: MOTION.drawTravel },
      { look: { back: "p2" }, owner: "p2", from: { zone: "p2:library" }, to: { zone: "p2:hand" }, delay: MOTION.millStagger, ms: MOTION.drawTravel },
      { look: { back: "p2" }, owner: "p2", from: { zone: "p2:library" }, to: { zone: "p2:hand" }, delay: 2 * MOTION.millStagger, ms: MOTION.drawTravel },
    ]);
  });

  it("a mill: every card leaves the library as a back and turns face up; the top one is the real card", () => {
    const prev = table([], { libraries: { "p2:library": 30 } });
    const next = table([seen("a", "p2:graveyard"), seen("b", "p2:graveyard"), seen("c", "p2:graveyard")], { libraries: { "p2:library": 27 } });
    const flights = plan(prev, next).flights;
    expect(flights.map((f) => [f.card ?? f.look, f.turn, f.delay])).toEqual([
      [{ face: "a" }, "up", 0],
      [{ face: "b" }, "up", MOTION.millStagger],
      ["c", "up", 2 * MOTION.millStagger],
    ]);
    expect(flights.every((f) => "zone" in f.from && f.from.zone === "p2:library")).toBe(true);
  });

  it("a card bounced to a hidden hand flies there as it looked and turns face down; a token that left fades where it was", () => {
    const prev = table([seen("bear", "p2:battlefield"), seen("goblin", "p2:battlefield", "p2", { is_token: true }), ...hidden(1, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand")]);
    expect(plan(prev, next, ["bear", "goblin"]).flights).toEqual([
      { look: { seen: "bear" }, owner: "p2", from: { gone: "bear" }, to: { zone: "p2:hand" }, turn: "down", delay: 0, ms: MOTION.cardTravel },
      { look: { seen: "goblin" }, owner: "p2", from: { gone: "goblin" }, vanish: true, delay: MOTION.millStagger, ms: MOTION.cardTravel * 0.6 },
    ]);
  });

  it("a token is put down where it belongs; an ability comes from its source permanent", () => {
    const prev = table([seen("krenko", "p1:battlefield")]);
    const next = table([seen("krenko", "p1:battlefield"), seen("t1", "p1:battlefield", "p1", { is_token: true }),
      seen("trig", "stack", "p1", { ability: { source_id: "krenko", text: "", source_card_id: null, source_name: "Krenko", kind: "activated" } })]);
    expect(plan(prev, next, ["krenko"]).flights.map((f) => [f.card, f.from])).toEqual([["t1", { drop: true }], ["trig", { card: "krenko" }]]);
  });

  it("a card bounced to my own hand flies to it face up (I see my hand)", () => {
    const prev = table([seen("bear", "p1:battlefield")]);
    const next = table([seen("bear", "p1:hand")]);
    expect(plan(prev, next, ["bear"]).flights).toEqual([{ look: { seen: "bear" }, owner: "p1", from: { gone: "bear" }, to: { zone: "p1:hand" }, delay: 0, ms: MOTION.cardTravel }]);
  });

  it("only the first maxFlights cards fly, staggered no further than groupMax; the rest just appear", () => {
    const prev = table([...hidden(1, "p2:hand")], { libraries: { "p2:library": 60 } });
    const next = table([...hidden(31, "p2:hand")], { libraries: { "p2:library": 30 } });
    const flights = plan(prev, next).flights;
    expect(flights).toHaveLength(MOTION.maxFlights);
    expect(Math.max(...flights.map((f) => f.delay))).toBeLessThanOrEqual(MOTION.groupMax);
  });

  it("privacy: a stand-in shows a face only for a card this viewer sees face up; hidden traffic is always card backs", () => {
    // Bob puts a face-down card (this viewer can't look at it) from the battlefield into his library; draws and puts back
    const prev = table([seen("morph", "p2:battlefield", "p2", { face_down: true }), ...hidden(4, "p2:hand")], { libraries: { "p2:library": 30 } });
    const next = table([...hidden(2, "p2:hand")], { libraries: { "p2:library": 33 } });
    const flights = plan(prev, next).flights;
    expect(flights.length).toBeGreaterThan(0);
    for (const f of flights) expect(f.look && "face" in f.look).toBe(false);
    // a card the table never showed and the viewer can't see: a back, whatever the event says about it
    const events: TableEvent[] = [{ kind: "move", id: "x", from: "p2:hand", to: "p2:library" }, { kind: "arrive", id: "y", from: "p2:library", to: "p2:hand" }];
    const secret = table([{ id: "x", zone: "p2:library", owner: "p2", hidden: true }, { id: "y", zone: "p2:hand", owner: "p2", hidden: true }]);
    for (const f of planMotion(events, secret, secret, facts(secret)).flights) expect(f.look).toEqual({ back: "p2" });
  });

  it("hidden zones: libraries and other players' hands, not my hand", () => {
    expect(hiddenZone("p1:library", "p1")).toBe(true);
    expect(hiddenZone("p2:hand", "p1")).toBe(true);
    expect(hiddenZone("p1:hand", "p1")).toBe(false);
    expect(hiddenZone("p2:graveyard", "p1")).toBe(false);
  });

  it("a shuffle riffles the library (once); damage and life rise as signed numbers", () => {
    const events: TableEvent[] = [
      { kind: "shuffle", zone: "p1:library", times: 2 }, { kind: "shuffle", zone: "p2:hand", times: 1 },
      { kind: "damage", id: "bear", amount: 3 }, { kind: "life", player: "p2", delta: -5 }, { kind: "life", player: "p1", delta: 3 },
    ];
    const view = table([seen("bear", "p1:battlefield")]);
    const p = planMotion(events, view, view, facts(view, ["bear"]));
    expect(p.shuffles).toEqual(["p1:library"]);
    expect(p.floaters).toEqual([
      { at: { card: "bear" }, text: `${MINUS}3`, gain: false },
      { at: { player: "p2" }, text: `${MINUS}5`, gain: false },
      { at: { player: "p1" }, text: "+3", gain: true },
    ]);
    expect(MINUS).toBe("−");
  });
});

describe("3D table motion: combat strikes", () => {
  const fight = (phase: string) => table([
    seen("bear", "p1:battlefield", "p1", { attacking: { kind: "player", id: "p2" }, damage: 2 }),
    seen("wall", "p2:battlefield", "p2", { blocking: "bear", damage: 2 }),
    seen("elf", "p1:battlefield", "p1", { attacking: { kind: "player", id: "p2" } }),
  ], { phase });

  it("when combat damage lands, an attacker and its blocker strike at each other; an unblocked attacker at the player", () => {
    const events: TableEvent[] = [{ kind: "damage", id: "wall", amount: 2 }, { kind: "life", player: "p2", delta: -1 }];
    expect(combatStrikes(events, fight("combat_damage"))).toEqual([
      { id: "bear", toward: { card: "wall" } },
      { id: "wall", toward: { card: "bear" } },
      { id: "elf", toward: { player: "p2" } },
    ]);
  });

  it("no strikes outside the combat damage step (a burn spell on a blocker isn't a fight)", () => {
    expect(combatStrikes([{ kind: "damage", id: "wall", amount: 2 }], fight("declare_blockers"))).toEqual([]);
  });
});

describe("3D table motion: curves", () => {
  it("the theme's ease-out curve, solved exactly: from 0 to 1, monotonic, strong early", () => {
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    let last = 0;
    for (let t = 0.02; t <= 1; t += 0.02) {
      const v = easeOut(t);
      expect(v).toBeGreaterThanOrEqual(last - 1e-9);
      last = v;
    }
    expect(easeOut(0.25)).toBeGreaterThan(0.6);
    // linear is linear
    expect(cubicBezier(0.25, 0.25, 0.75, 0.75)(0.3)).toBeCloseTo(0.3, 4);
  });

  it("a flight arcs over the middle, lasts longer for longer trips and never past 450 ms", () => {
    expect(arcLift(0, 1)).toBe(0);
    expect(arcLift(1, 1)).toBe(0);
    expect(arcLift(0.5, 1)).toBe(1);
    expect(flightMs(260, 2)).toBeLessThan(flightMs(260, 14));
    expect(flightMs(300, 100)).toBeLessThanOrEqual(450);
  });

  it("a card turns over in the middle of its flight, showing its new side past edge-on", () => {
    expect(turnAt(0)).toEqual({ angle: 0, over: false });
    expect(turnAt(1).angle).toBeCloseTo(Math.PI);
    expect(turnAt(1).over).toBe(true);
    expect(turnAt(0.3).over).toBe(false);
    expect(turnAt(0.7).over).toBe(true);
  });

  it("a stand-in stays whole until it reaches its destination, then merges into it; a vanishing one fades", () => {
    expect(standInOpacity(0.5)).toBe(1);
    expect(standInOpacity(1)).toBeCloseTo(0);
    expect(standInOpacity(0, true)).toBe(1);
    expect(standInOpacity(1, true)).toBe(0);
  });

  it("a strike lunges out and back", () => {
    expect(lungeAt(0)).toBe(0);
    expect(lungeAt(1)).toBe(0);
    expect(lungeAt(0.35)).toBeCloseTo(1);
  });

  it("a number fades in, rises and fades out; reduced motion drops its punch, not the number", () => {
    expect(floaterAt(0, false).opacity).toBe(0);
    expect(floaterAt(0.4, false).opacity).toBe(1);
    expect(floaterAt(1, false).opacity).toBe(0);
    expect(floaterAt(0.05, false).scale).toBeGreaterThan(1);
    expect(floaterAt(0.05, true).scale).toBe(1);
    expect(floaterAt(0.4, true).opacity).toBe(1);
  });

  it("a riffle splits the cards to both sides, then falls back in interleaved, ending where it began", () => {
    const n = 6;
    const split = Array.from({ length: n }, (_, i) => riffleAt(i, n, 0.42, 1, 0.01));
    expect(split.slice(0, 3).every((o) => o.dx < 0)).toBe(true);
    expect(split.slice(3).every((o) => o.dx > 0)).toBe(true);
    const start = Array.from({ length: n }, (_, i) => riffleAt(i, n, 0, 1, 0.01));
    expect(start.every((o) => o.dx === 0)).toBe(true);
    const end = Array.from({ length: n }, (_, i) => riffleAt(i, n, 1, 1, 0.01));
    expect(end.every((o) => Math.abs(o.dx) < 1e-9 && Math.abs(o.turn) < 1e-9)).toBe(true);
    // interleaved: the halves alternate from the bottom up
    expect(end.map((o) => Math.round(o.dy / 0.01))).toEqual([0, 2, 4, 1, 3, 5]);
  });
});

// ------------------------------------------------------------------ another player's hand, seen from my seat

/** Where a table point lands in the seat camera's frame (normalized: -1..1 across, -1 bottom .. 1 top), as TableScene frames it. */
function onScreen(all: Seat[], aspect: number, x: number, y: number, z: number): { x: number; y: number } {
  const h = 900;
  const w = h * aspect;
  const camera = new THREE.PerspectiveCamera(42, aspect, 0.1, 400);
  const band = Math.round(h * 0.16);
  camera.setViewOffset(w, h + band, 0, band, w, h);
  camera.updateProjectionMatrix();
  const mine = all[0]!;
  const cam = fitCamera(camera, all.flatMap((s) => seatPoints(s, { buttons: s === mine })), viewDir(mine.rot, seatElevation(all.length)), tableRect(w, h));
  camera.position.copy(cam.pos);
  camera.lookAt(cam.look);
  camera.updateMatrixWorld();
  const v = new THREE.Vector3(x, y, z).project(camera);
  return { x: v.x, y: v.y };
}
const tables = [2, 3, 4, 5, 6].map((n) => seats(Array.from({ length: n }, (_, i) => `p${i + 1}`), "p1"));

describe("3D table motion: where another player's hand is", () => {
  it("on their side of the table: on their mat, in the half that faces the aisle, past their plaque, low on the mat", () => {
    for (const all of tables) for (const seat of all.slice(1)) {
      const spot = otherHandSpot(seat);
      expect(onBattlefield(spot.lx, spot.lz)).toBe(true);
      expect(spot.lz).toBeLessThan(0); // the aisle half (their own edge, past which their fan lies, is +MAT_D / 2)
      expect(spot.lz - CARD_H / 2).toBeGreaterThan(-MAT_D / 2 + 0.5); // the whole card clears the plaque by the aisle edge
      expect(Math.sign(spot.lx)).toBe(Math.sign(plaqueSpot(seat)[0]));
      expect(spot.y).toBeLessThan(0.2); // it rises out of the mat
    }
  });

  it("well inside the seat camera's frame at every table size, where their fan of card backs sat at its top edge (or under my hand)", () => {
    for (const aspect of [16 / 9, 1440 / 900, 4 / 3]) for (const all of tables) for (const seat of all.slice(1)) {
      const spot = otherHandSpot(seat);
      const at = onScreen(all, aspect, ...((([x, z]) => [x, spot.y, z])(toWorld(seat, spot.lx, spot.lz)) as [number, number, number]));
      // (the seat view fills the screen with the table: table3d/framing.ts)
      expect(Math.abs(at.x)).toBeLessThan(0.85);
      expect(at.y).toBeGreaterThan(-0.6);
      expect(at.y).toBeLessThan(0.85);
    }
    // the fan of backs, for comparison: past the owner's edge of their mat, at the far rim of the table (two players)
    const [me, bob] = tables[0]!;
    const fan = onScreen([me!, bob!], 16 / 9, ...((([x, z]) => [x, 0.3, z])(toWorld(bob!, 0, MAT_D / 2 + 1.25)) as [number, number, number]));
    expect(fan.y).toBeGreaterThan(0.6);
  });
});
