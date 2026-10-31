import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { dieShape } from "./dice";
import { poseAt, seeded, simulate, trackSeconds, type BodyInit } from "./physics";

const bounds = { minX: -10, maxX: 10, minZ: -8, maxZ: 8 };

function throwDie(sides: number, key: string): { pos: THREE.Vector3; rot: THREE.Quaternion; seconds: number } {
  const shape = dieShape(sides);
  const rnd = seeded(key);
  const body: BodyInit = {
    verts: shape.hull, radius: shape.radius,
    pos: new THREE.Vector3(0, 1.4, 5), vel: new THREE.Vector3((rnd() - 0.5) * 2, 2, -6),
    spin: new THREE.Vector3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize().multiplyScalar(20),
    rot: new THREE.Quaternion().setFromEuler(new THREE.Euler(rnd() * 6, rnd() * 6, rnd() * 6)),
  };
  const [track] = simulate([body], { bounds });
  const pos = new THREE.Vector3();
  const rot = new THREE.Quaternion();
  poseAt(track!, track!.count - 1, pos, rot);
  return { pos, rot, seconds: trackSeconds(track!) };
}

describe("dice physics", () => {
  it("finds every face of every die", () => {
    expect([4, 6, 8, 10, 12, 20].map((n) => dieShape(n).faces)).toEqual([4, 6, 8, 10, 12, 20]);
  });

  it("throws dice that come to rest flat on a face, on the table, within a few seconds", () => {
    for (const sides of [4, 6, 8, 10, 12, 20]) {
      for (const key of ["a", "b", "c", "d"]) {
        const { pos, rot, seconds } = throwDie(sides, `${sides}${key}`);
        const down = Math.min(...dieShape(sides).normals.map((n) => n.clone().applyQuaternion(rot).y));
        expect(down, `d${sides} ${key} rests on a face`).toBeLessThan(-0.97);
        expect(pos.y).toBeGreaterThan(0);
        expect(pos.y).toBeLessThan(0.5);
        expect(Math.abs(pos.x)).toBeLessThan(10);
        expect(Math.abs(pos.z)).toBeLessThan(8);
        expect(seconds).toBeLessThan(4.01);
      }
    }
  });

  it("is the same throw on every screen (seeded by the roll)", () => {
    const a = throwDie(20, "42:1700000000");
    const b = throwDie(20, "42:1700000000");
    expect(a.pos.toArray()).toEqual(b.pos.toArray());
    expect(a.rot.toArray()).toEqual(b.rot.toArray());
    expect(throwDie(20, "43:1700000000").pos.toArray()).not.toEqual(a.pos.toArray());
  });
});
