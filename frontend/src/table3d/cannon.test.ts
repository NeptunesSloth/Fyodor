import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { CANNON_MS, fireTimes, firstHeadline, flightSeconds, tagLabel, volleyCount, volleys } from "../game/cannon";
import type { DiceShow } from "../game/dice";
import { DiceTray } from "./dice";
import { dieSolid, shownValue } from "./diceGeometry";
import { cannonEnv, cannonLaunch, judge, diceOf, placeRoll, prefixTrack, throwRoll } from "./diceThrow";
import { poseAt } from "./physics";

const first: DiceShow = {
  key: "7:1.5", actor: "p1", sides: 20, coin: false, results: [12, 19, 19, 7, 15],
  cannon: { mode: "first", players: ["p1", "p2", "p3", "p2", "p3"], rounds: [0, 0, 0, 1, 1], winner: "p3" },
};
const volley: DiceShow = {
  key: "8:2.5", actor: "p2", sides: 6, coin: false, results: [2, 5, 6],
  cannon: { mode: "volley", players: ["p2", "p2", "p2"], rounds: [0, 0, 0], winner: null },
};

/** The value a thrown die shows at rest, read off its pose (body × the turn that shows the server's number). */
function landed(d: { kind: string; track: Parameters<typeof poseAt>[0]; turn: THREE.Quaternion }): { value: number; at: THREE.Vector3 } {
  const p = new THREE.Vector3();
  const q = new THREE.Quaternion();
  poseAt(d.track, d.track.count - 1, p, q);
  const s = dieSolid(d.kind as Exclude<Parameters<typeof dieSolid>[0], never>);
  return { value: shownValue(s, q.multiply(d.turn)), at: p };
}

describe("the dice cannon's volleys (game/cannon.ts)", () => {
  it("throws one die at each player per volley, tags the tied and the winner, in firing order", () => {
    const v = volleys(first);
    expect(v.map((x) => [x.round, x.player, x.show.results, x.tag])).toEqual([
      [0, "p1", [12], null], [0, "p2", [19], "tie"], [0, "p3", [19], "tie"], [1, "p2", [7], null], [1, "p3", [15], "first"],
    ]);
    // each throw has its own key (its own seeded throw), the same on every screen, and lands in front of its player
    expect(new Set(v.map((x) => x.key)).size).toBe(5);
    expect(v.every((x) => x.show.key === x.key && x.show.actor === x.player)).toBe(true);
    expect(volleyCount(first)).toBe(2);
    expect(firstHeadline(first, (p) => ({ p1: "Alice", p2: "Bob", p3: "Cleo" })[p]!)).toBe("Cleo goes first (15)");
    expect([tagLabel("first"), tagLabel("tie"), tagLabel(null)]).toEqual(["Goes first", "Tied: fired again", null]);
  });

  it("keeps a volley's dice together, in front of the player who fired it", () => {
    const v = volleys(volley);
    expect(v).toHaveLength(1);
    expect(v[0]!.show.results).toEqual([2, 5, 6]);
    expect(v[0]!.player).toBe("p2");
    expect(firstHeadline(volley, () => "")).toBeNull();
    expect(volleys({ ...volley, cannon: null })).toEqual([]);
  });

  it("fires a tie's re-fire after the dice before it have landed", () => {
    expect(fireTimes(3, (_r, at) => at + 2000)).toEqual([CANNON_MS.first, CANNON_MS.first + 2000 + CANNON_MS.refire, CANNON_MS.first + 2 * (2000 + CANNON_MS.refire)]);
    expect(flightSeconds(0)).toBe(0.5);
    expect(flightSeconds(100)).toBe(1.25);
  });
});

describe("a die fired from the cannon (table3d/diceThrow.ts)", () => {
  it("drops onto its player's mat and comes to rest flat, showing the server's number, the same throw every time", () => {
    for (const results of [[19], [4], [20], [1]]) {
      const show = { key: `k${results[0]}`, sides: 20, results, coin: false };
      const env = cannonEnv([], 0);
      const a = throwRoll(show, env, cannonLaunch);
      const b = throwRoll(show, env, cannonLaunch);
      const die = a.dice[0]!;
      const { value, at } = landed(die);
      expect(value).toBe(results[0]);
      // on the mat (10 × 6 round the origin), not in the aisle
      expect(Math.abs(at.x)).toBeLessThan(5);
      expect(Math.abs(at.z)).toBeLessThan(3);
      expect(Array.from(b.dice[0]!.track.frames.subarray(0, die.track.count * 7))).toEqual(Array.from(die.track.frames.subarray(0, die.track.count * 7)));
    }
  });

  it("lands a volley of six on the mat too", () => {
    const show = { key: "six", sides: 6, results: [1, 2, 3, 4, 5, 6], coin: false };
    const env = cannonEnv([], 0);
    const thrown = throwRoll(show, env, cannonLaunch);
    expect(thrown.dice.map((d) => landed(d).value)).toEqual([1, 2, 3, 4, 5, 6]);
    for (const d of thrown.dice) {
      const { at } = landed(d);
      expect(Math.abs(at.x)).toBeLessThan(5);
      expect(Math.abs(at.z)).toBeLessThan(3);
    }
  });

  it("lands a tie's re-fire beside the die before it", () => {
    expect(cannonEnv([], 1).land.minX).toBeGreaterThan(cannonEnv([], 0).land.maxX - 0.5);
  });

  it("flies from the muzzle into the throw's first pose, then the throw plays on unchanged", () => {
    const show = { key: "fly", sides: 20, results: [11], coin: false };
    const die = throwRoll(show, cannonEnv(), cannonLaunch).dice[0]!;
    const from = new THREE.Vector3(14, 1.2, -9);
    const flown = prefixTrack(die.track, from, 0.8);
    const n = flown.count - die.track.count;
    expect(n).toBe(96); // 0.8 s at 120 frames a second
    expect(flown.rest).toBe(die.track.rest + n);
    const p = new THREE.Vector3();
    const q = new THREE.Quaternion();
    poseAt(flown, 0, p, q);
    expect(p.distanceTo(from)).toBeLessThan(1e-4); // out of the muzzle
    const p0 = new THREE.Vector3();
    const q0 = new THREE.Quaternion();
    poseAt(die.track, 0, p0, q0);
    poseAt(flown, n, p, q);
    expect(p.distanceTo(p0)).toBeLessThan(1e-5); // then exactly the throw
    // no jump where they meet: the frame before is a frame's travel away
    poseAt(flown, n - 1, p, q);
    expect(p.distanceTo(p0)).toBeLessThan(0.4);
    expect(Math.abs(q.dot(q0))).toBeGreaterThan(0.95);
    // and it went up out of the muzzle, as fired
    let top = -Infinity;
    for (let i = 0; i < n; i++) { poseAt(flown, i, p, q); top = Math.max(top, p.y); }
    expect(top).toBeGreaterThan(from.y + 0.5);
  });

  it("without physics (low graphics): the dice lie flat in the landing area with the server's numbers", () => {
    const show = { key: "still", sides: 6, results: [3, 6, 1, 4], coin: false };
    const env = cannonEnv([], 0);
    const placed = placeRoll(show, env);
    expect(placed.impacts).toEqual([]);
    const specs = diceOf(show);
    expect(judge(specs, placed.dice.map((d) => d.track), env).every((c) => c.flat && c.inside)).toBe(true);
    expect(placed.dice.map((d) => landed(d).value)).toEqual([3, 6, 1, 4]);
    const d20 = placeRoll({ key: "s20", sides: 20, results: [17], coin: false }, env).dice[0]!;
    expect(landed(d20).value).toBe(17);
  });
});

// the dice's engraving is drawn on a 2D canvas: a do-nothing one is enough here
function canvasStub() {
  const method = (k: string | symbol) => {
    if (k === "getImageData") return (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) });
    if (k === "measureText") return () => ({ width: 10 });
    return () => ({ addColorStop() {} });
  };
  const ctx: unknown = new Proxy({}, { get: (_t, k) => method(k), set: () => true });
  return { width: 0, height: 0, getContext: () => ctx };
}

describe("a cannon's throw on the table (table3d/dice.ts)", () => {
  beforeEach(() => vi.stubGlobal("document", { createElement: canvasStub }));
  afterEach(() => vi.unstubAllGlobals());

  it("waits in the barrel until its volley fires, flies, lands with its line and tag; reduced motion shows only the result", () => {
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    const show = { key: "c1", actor: "p2", sides: 20, results: [19], coin: false };
    const { settles } = tray.throw(show, "#5fa8d3", "Bob", { x: 0, z: -5, rotY: Math.PI }, cannonEnv(), 0,
      { launcher: cannonLaunch, from: new THREE.Vector3(14, 1.2, 0), delay: 900, tag: "Goes first" });
    expect(settles).toBeGreaterThan(900 + 500); // fired at 900, then the flight and the roll
    const project = (p: THREE.Vector3) => ({ x: p.x * 10, y: -p.z * 10, visible: true });
    tray.update(400, false, 1);
    expect(tray.group.children[0]!.visible).toBe(false); // still in the barrel
    expect(tray.hud(project)[0]!.shown).toBe(false);
    tray.update(1200, false, 1);
    expect(tray.group.children[0]!.visible).toBe(true);
    tray.update(settles + 1000, false, 1);
    const [t] = tray.hud(project);
    expect([t!.line, t!.tag, t!.shown, t!.chips[0]!.label]).toEqual(["Bob · d20: 19", "Goes first", true, "19"]);
    // twice as fast: the same throw lands in half the time
    const fast = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    fast.throw({ ...show, key: "c2" }, "#5fa8d3", "Bob", { x: 0, z: -5, rotY: Math.PI }, cannonEnv(), 0, { launcher: cannonLaunch, delay: 900 });
    fast.update(500, false, 2);
    expect(fast.group.children[0]!.visible).toBe(true);
    // reduced motion: no wait, no flight, at rest
    const still = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    still.throw({ ...show, key: "c3" }, "#5fa8d3", "Bob", { x: 0, z: -5, rotY: Math.PI }, cannonEnv(), 0, { launcher: cannonLaunch, delay: 900, from: new THREE.Vector3(14, 1.2, 0) });
    still.update(1, true, 1);
    expect(still.describe()[0]!.dice[0]!.resting).toBe(true);
    // a throw cleared before it fired (a new turn) never shows
    tray.throw({ ...show, key: "c4" }, "#5fa8d3", "Bob", { x: 0, z: -5, rotY: Math.PI }, cannonEnv(), 0, { launcher: cannonLaunch, delay: 50_000 });
    tray.clear("p2", 10);
    tray.update(100, false, 1);
    tray.update(settles + 2000, false, 1);
    expect(tray.count).toBe(0);
    for (const x of [tray, fast, still]) x.dispose();
  });
});
