import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { dieSolid, tilt, type DieKind } from "./diceGeometry";
import { diceOf, tableEnv, throwRoll } from "./diceThrow";
import { poseAt, seeded, simulate, type BodyInit, type Track } from "./physics";

const bounds = { minX: -10, maxX: 10, minZ: -8, maxZ: 8 };
const KINDS: [number, Exclude<DieKind, "coin">][] = [[4, "d4"], [6, "d6"], [8, "d8"], [10, "d10"], [12, "d12"], [20, "d20"]];
const end = (track: Track) => {
  const pos = new THREE.Vector3();
  const rot = new THREE.Quaternion();
  poseAt(track, track.count - 1, pos, rot);
  return { pos, rot };
};

describe("dice physics (cannon-es)", () => {
  it("throws every kind of die across the roller's mat to rest flat on the table, never cocked or sunk, in about 1.5–2.5 s", () => {
    const env = tableEnv([{ x: 6.1, z: 2.4, w: 0.84, d: 1.17, h: 0.4 }]);
    for (const [sides, kind] of KINDS) {
      const s = dieSolid(kind);
      const rests: number[] = [];
      for (let k = 0; k < 12; k++) {
        const r = throwRoll({ key: `${sides}:${k}`, sides, results: [1 + (k % sides), 1 + ((k + 3) % sides)], coin: false }, env);
        for (const d of r.dice) {
          const { pos, rot } = end(d.track);
          expect(tilt(s, rot), `d${sides} #${k} lies flat`).toBeLessThan(0.002);
          expect(pos.y, `d${sides} #${k} rests on the table, not in it`).toBeCloseTo(s.inradius, 2);
          // on the roller's side of the table: their mat or the aisle in front of it
          expect(Math.abs(pos.x)).toBeLessThan(5.6);
          expect(pos.z).toBeGreaterThan(-4.2);
          expect(pos.z).toBeLessThan(3.2);
          rests.push(d.rest);
        }
      }
      rests.sort((a, b) => a - b);
      expect(rests[Math.floor(rests.length / 2)]!, `d${sides}: typical settle`).toBeLessThan(2.4);
      expect(rests[Math.floor(rests.length / 2)]!).toBeGreaterThan(0.6);
      expect(rests.at(-1)!, `d${sides}: slowest`).toBeLessThan(3.7);
    }
  });

  it("lands a coin flat, heads or tails", () => {
    for (let k = 0; k < 10; k++) {
      const r = throwRoll({ key: `coin:${k}`, sides: 2, results: [k % 2], coin: true }, tableEnv());
      const { pos, rot } = end(r.dice[0]!.track);
      expect(Math.abs(new THREE.Vector3(0, 1, 0).applyQuaternion(rot).y)).toBeGreaterThan(0.998);
      expect(pos.y).toBeLessThan(0.1);
    }
  });

  it("bounces dice off a deck in the way", () => {
    const s = dieSolid("d6");
    const body = (): BodyInit => ({
      verts: s.verts, faces: s.polys, radius: s.radius,
      pos: new THREE.Vector3(0, 0.4, 4), vel: new THREE.Vector3(0, 0, -24), spin: new THREE.Vector3(), rot: new THREE.Quaternion(),
    });
    const z = (obstacles: { x: number; z: number; w: number; d: number; h: number }[]) => end(simulate([body()], { bounds, obstacles }).tracks[0]!).pos.z;
    expect(z([])).toBeLessThan(1); // without a deck, it slides on past z = 1
    expect(z([{ x: 0, z: 1, w: 2, d: 1, h: 1.2 }])).toBeGreaterThan(1.5); // a deck there stops it on its near side
  });

  it("knocks dice together and hears it: impacts with the table and between dice", () => {
    const r = throwRoll({ key: "clatter", sides: 6, results: [1, 2, 3, 4, 5, 6], coin: false }, tableEnv());
    expect(r.impacts.some((i) => i.with === "table")).toBe(true);
    expect(r.impacts.some((i) => i.with === "die")).toBe(true);
    for (const i of r.impacts) expect(i.speed).toBeGreaterThan(0.4);
  });

  it("is the same throw on every screen (seeded by the roll)", () => {
    const show = { key: "42:1700000000", sides: 20, results: [7, 13], coin: false };
    const a = throwRoll(show, tableEnv());
    const b = throwRoll(show, tableEnv());
    a.dice.forEach((d, i) => {
      expect(Array.from(d.track.frames.subarray(0, d.track.count * 7))).toEqual(Array.from(b.dice[i]!.track.frames.subarray(0, b.dice[i]!.track.count * 7)));
      expect(d.turn.toArray()).toEqual(b.dice[i]!.turn.toArray());
    });
    expect(a.impacts).toEqual(b.impacts);
    const c = throwRoll({ ...show, key: "43:1700000000" }, tableEnv());
    expect(end(c.dice[0]!.track).pos.toArray()).not.toEqual(end(a.dice[0]!.track).pos.toArray());
  });

  it("seeds from the roll's key alone", () => {
    expect([seeded("x")(), seeded("x")()]).toEqual([seeded("x")(), seeded("x")()]);
    expect(seeded("x")()).not.toEqual(seeded("y")());
  });

  it("throws a d100 as a tens die and a units die, and at most twelve dice", () => {
    expect(diceOf({ sides: 100, results: [37], coin: false }).map((d) => [d.kind, d.label])).toEqual([["d10x10", "30"], ["d10", "7"]]);
    expect(diceOf({ sides: 100, results: [100], coin: false }).map((d) => d.label)).toEqual(["00", "0"]);
    expect(diceOf({ sides: 10, results: [10], coin: false })[0]).toMatchObject({ face: 0, label: "10" });
    expect(diceOf({ sides: 6, results: Array.from({ length: 30 }, () => 3), coin: false })).toHaveLength(12);
  });
});
