import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { PROP_TOP, propSpots } from "../framing";
import { RAIL, seats, tableSize } from "../layout";
import { rng } from "../textures";
import { PLANES } from "../../theme/planes";
import { Batch } from "./batch";
import { Flames } from "./flames";
import { Put, type SetCtx } from "./kit";
import { buildTableProp, PROP_HALF } from "./props";
import { RoomLight } from "./roomShader";
import { roomFor, SETS } from "./sets";

function build(planeId: string, n: number) {
  const all = seats(Array.from({ length: n }, (_, i) => `p${i + 1}`), "p1");
  const size = tableSize(all);
  const spots = propSpots(all, size);
  const batch = new Batch();
  const flames = new Flames(64, { value: 0 });
  const room = new RoomLight("#000", 0.2);
  const ctx: SetCtx = { set: batch, glow: batch, flames, room, rand: rng(7), floorY: 0, rich: true };
  const spec = SETS[planeId as keyof typeof SETS];
  const lights = spec.props.flatMap((kind, i) => buildTableProp(ctx, new Put(ctx).at(spots[i]![0], 0, spots[i]![1]), kind, "#ffae52"));
  return { size, spots, geo: batch.build(), flames, lights };
}

describe("the table's props", () => {
  for (const p of PLANES) {
    for (const n of [2, 4, 6]) {
      it(`${p.name}, ${n} seats: each prop stands within its spot, inside the rail and under the framed height`, () => {
        const { size, spots, geo, flames, lights } = build(p.id, n);
        expect(geo).not.toBeNull();
        const pos = geo!.getAttribute("position");
        const v = new THREE.Vector3();
        for (let i = 0; i < pos.count; i++) {
          v.fromBufferAttribute(pos, i);
          const [sx, sz] = spots.reduce((a, b) => (Math.hypot(v.x - a[0], v.z - a[1]) < Math.hypot(v.x - b[0], v.z - b[1]) ? a : b));
          expect(Math.abs(v.x - sx)).toBeLessThanOrEqual(PROP_HALF[0] + 1e-6);
          expect(Math.abs(v.z - sz)).toBeLessThanOrEqual(PROP_HALF[1] + 1e-6);
          expect(v.y).toBeGreaterThanOrEqual(-0.04); // (a drip or a coin may rest a hair into the wood)
          expect(v.y).toBeLessThanOrEqual(PROP_TOP + 1e-6);
          expect(Math.abs(v.x)).toBeLessThanOrEqual(size.w / 2 - RAIL + 0.05);
          expect(Math.abs(v.z)).toBeLessThanOrEqual(size.d / 2 - RAIL + 0.05);
        }
        // the flames' tips are framed too
        const m = new THREE.Matrix4();
        const fl = flames.mesh.geometry.getAttribute("aFlame");
        for (let i = 0; i < flames.count; i++) {
          flames.mesh.getMatrixAt(i, m);
          const base = new THREE.Vector3().setFromMatrixPosition(m);
          const scale = new THREE.Vector3().setFromMatrixScale(m).x;
          expect(base.y + scale * fl.getY(i)).toBeLessThanOrEqual(PROP_TOP + 0.02);
        }
        // a lit prop casts real light on the table, from above the table top
        for (const l of lights) expect(l.pos.y).toBeGreaterThan(0);
      });
    }
  }

  it("Dominaria's pair is a chamberstick of three candles (three flames) and a stack of books", () => {
    const { flames, lights } = build("dominaria", 2);
    expect(flames.count).toBe(3);
    expect(lights).toHaveLength(1);
  });
});

describe("the room around the table", () => {
  it("stands clear of the table on every side, wider for a wider table", () => {
    for (const n of [2, 4, 6]) {
      const size = tableSize(seats(Array.from({ length: n }, (_, i) => `p${i + 1}`), "p1"));
      const r = roomFor(size, -9);
      expect(r.left).toBeLessThan(-size.w / 2 - 10);
      expect(r.right).toBeGreaterThan(size.w / 2 + 10);
      expect(r.back).toBeLessThan(-size.d / 2 - 10);
      expect(r.front).toBeGreaterThan(size.d / 2 + 10);
      expect(r.right).toBeCloseTo(-r.left);
    }
  });
});
