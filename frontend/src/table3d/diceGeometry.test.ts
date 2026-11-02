import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { coinTurn, dieSolid, faceTurn, facesShowing, kindsFor, percentile, shownValue, tilt, topFace, topPoint, type DieKind } from "./diceGeometry";

type Solid = Exclude<DieKind, "coin">;
const SOLIDS: Solid[] = ["d4", "d6", "d8", "d10", "d10x10", "d12", "d20", "d3"];
const SIDES: Record<Solid, number> = { d4: 4, d6: 6, d8: 8, d10: 10, d10x10: 10, d12: 12, d20: 20, d3: 6, dx: 20 };

/** A seeded random rotation (no Math.random in tests). */
function rotations(n: number, seed = 7): THREE.Quaternion[] {
  let s = seed;
  const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  return Array.from({ length: n }, () => new THREE.Quaternion(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize());
}

/** A rotation that sets face `fi` of the solid flat on the table (its normal straight down), with a random spin. */
function restingOn(solid: ReturnType<typeof dieSolid>, fi: number, spin: number): THREE.Quaternion {
  const q = new THREE.Quaternion().setFromUnitVectors(solid.faces[fi]!.normal, new THREE.Vector3(0, -1, 0));
  return new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), spin).multiply(q);
}

describe("real dice: geometry and numbering", () => {
  it("has every face and the full rotation group of each solid", () => {
    const groups: Record<string, number> = { d4: 12, d6: 24, d8: 24, d10: 10, d10x10: 10, d12: 60, d20: 60, d3: 24 };
    for (const k of SOLIDS) {
      const s = dieSolid(k);
      expect(s.faces.length, k).toBe(SIDES[k]);
      expect(s.symmetries.length, `${k} symmetries`).toBe(groups[k]);
    }
  });

  it("numbers opposite faces to sum to n + 1 (d6, d8, d12, d20) and every number once", () => {
    for (const k of ["d6", "d8", "d12", "d20"] as const) {
      const s = dieSolid(k);
      const n = s.faces.length;
      expect(s.faces.map((f) => f.value).sort((a, b) => a - b), k).toEqual(Array.from({ length: n }, (_, i) => i + 1));
      for (const f of s.faces) {
        const opp = s.faces.find((g) => g.normal.dot(f.normal) < -0.999)!;
        expect(f.value + opp.value, `${k} ${f.value}`).toBe(n + 1);
      }
    }
  });

  it("puts a d6's 1, 2 and 3 counter-clockwise round their shared corner", () => {
    const s = dieSolid("d6");
    const n = (v: number) => s.faces.find((f) => f.value === v)!.normal;
    // seen from outside the corner, 1 → 2 → 3 turns counter-clockwise: (n1 × n2) · n3 > 0
    expect(n(1).clone().cross(n(2)).dot(n(3))).toBeGreaterThan(0);
  });

  it("numbers a d10 0–9 with the evens round one apex, the odds round the other, opposite faces summing to 9", () => {
    for (const k of ["d10", "d10x10"] as const) {
      const s = dieSolid(k);
      expect(s.faces.map((f) => f.value).sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
      for (const f of s.faces) {
        expect(f.value % 2 === 0, `${f.value} sits round the ${f.normal.y > 0 ? "upper" : "lower"} apex`).toBe(f.normal.y > 0);
        const opp = s.faces.find((g) => g.normal.dot(f.normal) < -0.999)!;
        expect(f.value + opp.value).toBe(9);
      }
    }
  });

  it("numbers a d4 at its points: each face shows the three points around it, the roll is the point on top", () => {
    const s = dieSolid("d4");
    expect([...s.pointValues].sort()).toEqual([1, 2, 3, 4]);
    for (const f of s.faces) expect(f.verts.length).toBe(3);
    for (let fi = 0; fi < 4; fi++) {
      const q = restingOn(s, fi, 0.3);
      // the point opposite the face it rests on is on top, and isn't one of that face's corners
      expect(s.faces[fi]!.verts.includes(topPoint(s, q))).toBe(false);
    }
  });

  it("numbers a d3 1–3 twice, opposite faces summing to 4", () => {
    const s = dieSolid("d3");
    for (const f of s.faces) {
      const opp = s.faces.find((g) => g.normal.dot(f.normal) < -0.999)!;
      expect(f.value + opp.value).toBe(4);
    }
  });

  it("splits a d100 into its tens die and units die (100 is 00 and 0)", () => {
    expect(kindsFor(100, false)).toEqual(["d10x10", "d10"]);
    expect(percentile(100)).toEqual([0, 0]);
    expect(percentile(37)).toEqual([3, 7]);
    expect(percentile(10)).toEqual([1, 0]);
    expect(percentile(5)).toEqual([0, 5]);
    for (let v = 1; v <= 100; v++) {
      const [t, u] = percentile(v);
      expect(t * 10 + u || 100).toBe(v);
    }
  });

  it("builds a closed, outward-facing rounded mesh", () => {
    for (const k of SOLIDS) {
      const s = dieSolid(k);
      const pos = s.geometry.getAttribute("position");
      const nor = s.geometry.getAttribute("normal");
      const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
      let volume = 0;
      for (let t = 0; t < pos.count; t += 3) {
        a.fromBufferAttribute(pos, t); b.fromBufferAttribute(pos, t + 1); c.fromBufferAttribute(pos, t + 2);
        n.fromBufferAttribute(nor, t);
        const face = b.clone().sub(a).cross(c.clone().sub(a));
        if (face.lengthSq() > 1e-14) expect(face.dot(n), `${k} triangle ${t / 3} faces out`).toBeGreaterThan(0);
        volume += a.dot(b.clone().cross(c)) / 6;
        // nothing pokes out of the sharp solid
        for (const p of [a, b, c]) expect(p.length()).toBeLessThanOrEqual(s.radius + 1e-6);
      }
      // the rounded die is a little smaller than the sharp one, never inside out
      expect(volume, k).toBeGreaterThan(0);
    }
  });
});

describe("the server's number ends up on top", () => {
  it("turns every die so that the face showing each result lands up, whichever face the physics landed on", () => {
    for (const k of SOLIDS) {
      const s = dieSolid(k);
      const values = k === "d4" ? s.pointValues : [...new Set(s.faces.map((f) => f.value))];
      for (let fi = 0; fi < s.faces.length; fi++) {
        const body = restingOn(s, fi, fi * 0.77);
        expect(tilt(s, body)).toBeLessThan(1e-6);
        const landed = k === "d4" ? topPoint(s, body) : topFace(s, body);
        for (const v of values) {
          const shown = body.clone().multiply(faceTurn(s, landed, v));
          expect(shownValue(s, shown), `${k} landed on ${landed}, server said ${v}`).toBe(v);
          // a symmetry: the die still occupies exactly the same space (still flat on the same plane)
          expect(tilt(s, shown)).toBeLessThan(1e-6);
        }
      }
    }
  });

  it("works from any orientation the physics leaves, not just exactly flat", () => {
    for (const k of SOLIDS) {
      const s = dieSolid(k);
      for (const body of rotations(40, k.length * 13)) {
        const landed = k === "d4" ? topPoint(s, body) : topFace(s, body);
        const v = k === "d4" ? s.pointValues[(landed + 1) % 4]! : s.faces[(landed + 3) % s.faces.length]!.value;
        expect(shownValue(s, body.clone().multiply(faceTurn(s, landed, v)))).toBe(v);
      }
    }
  });

  it("flips a coin to the server's side", () => {
    for (const body of rotations(20, 3)) {
      for (const heads of [true, false]) {
        const q = body.clone().multiply(coinTurn(body, heads));
        expect(new THREE.Vector3(0, 1, 0).applyQuaternion(q).y > 0).toBe(heads);
      }
    }
  });

  it("leaves a die without a real face for the number (a d7) as it fell", () => {
    expect(kindsFor(7, false)).toEqual(["dx"]);
    expect(facesShowing(dieSolid("dx"), 7)).toEqual([]);
    expect(faceTurn(dieSolid("dx"), 0, 7).equals(new THREE.Quaternion())).toBe(true);
  });
});
