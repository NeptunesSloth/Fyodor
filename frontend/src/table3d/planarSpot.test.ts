import { describe, expect, it } from "vitest";
import { cannonSpot } from "./cannon3d";
import * as THREE from "three";
import { fitCamera, seatElevation, tableLens, tablePoints, tableRect, viewDir } from "./framing";
import { CARD_H, CARD_W, COMMAND_WELL, commandSlot, DUEL_VIEW, FELT_HEM, HEART, heartSpot, MAT_D, MAT_W, pileSpot, planarSpot, PLATE, plaqueSpot, RAIL, seats, STACK_REACH, tableSize, toLocal, toWorld, WELL, type Seat } from "./layout";

// -- planechase -- the face-up plane lying in the aisle of the 3D table (TableScene.syncPlanar; table3d/planar3d.ts)
describe("the plane's place on the 3D table", () => {
  for (const n of [1, 2, 3, 4, 5, 6]) {
    it(`lies flat in the aisle, on no mat, clear of the stack, the hearts and the plates (${n} seat${n > 1 ? "s" : ""})`, () => {
      const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
      const { x, z, scale, tilt } = planarSpot(all);
      const hw = (CARD_H * scale) / 2; // landscape: its long side along the aisle
      const hd = (CARD_W * scale * Math.cos(tilt)) / 2; // (its footprint: a duel's stands tipped up toward me)
      expect(scale).toBeGreaterThanOrEqual(1.25); // (bigger than a card on the mats: it is the table's one plane)
      const corners = [[x - hw, z - hd], [x + hw, z - hd], [x - hw, z + hd], [x + hw, z + hd]] as const;
      for (const seat of all) {
        for (const [cx, cz] of corners) {
          const [lx, lz] = toLocal(seat, cx, cz);
          const hem = seat.duel ? 0 : 0.25; // (a duel's aisle is narrow: the plane reaches over the mats' felt hems, never onto a mat)
          expect(Math.abs(lx) <= MAT_W / 2 + hem && Math.abs(lz) <= MAT_D / 2 + hem).toBe(false);
        }
        if (seat.duel) continue; // (a duel's hearts and plates stand past each seat's own edge, not in the aisle)
        const bands = [[heartSpot(seat), HEART.w], [plaqueSpot(seat), PLATE.w]] as const;
        for (const [[lx, lz], w] of bands) {
          const [wx] = toWorld(seat, lx, lz);
          expect(x + hw < wx - w / 2 - 0.2 || x - hw > wx + w / 2 + 0.2).toBe(true);
        }
      }
      const size = tableSize(all);
      expect(Math.abs(x) + hw).toBeLessThan(size.w / 2 - RAIL - (n === 2 ? 0.05 : 0.3)); // on the table, inside the rail (a duel's stands on the wood up to it)
      if (n === 2) {
        // big enough to read from the duel's low seat view: twice a mat card, its face turned toward my seat
        expect(scale).toBeGreaterThanOrEqual(2);
        expect(tilt + DUEL_VIEW).toBeGreaterThan(1.3);
        expect(tilt + DUEL_VIEW).toBeLessThan(Math.PI / 2 + 0.2);
        // past the mats' left ends (a card standing in the aisle rises over the far mat): clear of the stack, which lies on
        // the felt at the aisle's left end, and far from the dice cannon, which rolls in at its right end
        expect(x + hw).toBeLessThan(-MAT_W / 2);
        expect(x + hw).toBeLessThan(cannonSpot(size.w).spot.x - 1);
      } else {
        expect(tilt).toBe(0); // (a pod's aisle is wide and seen from higher: it lies flat)
        expect(x + hw).toBeLessThan(-STACK_REACH - 0.3); // left of the stack's widest fan
      }
    });
  }
});

// -- planechase -- what a duel's seat sees: the standing plane overlaps no mat and no zone well on screen (framing.ts's default view)
describe("the duel plane on screen", () => {
  for (const [w, h] of [[1920, 1034], [1366, 722], [1440, 809]] as const) {
    it(`covers no mat and no well at ${w}×${h}`, () => {
      const all = seats(["p1", "p2"], "p1");
      const mine = all[0]!;
      const elevation = seatElevation(2, w / h);
      const cam = tableLens(w, h);
      const f = fitCamera(cam, tablePoints(all, mine, tableSize(all), elevation), viewDir(mine.rot, elevation), tableRect(w, h));
      cam.position.copy(f.pos);
      cam.lookAt(f.look);
      cam.updateMatrixWorld(true);
      const screen = (p: THREE.Vector3): [number, number] => {
        const v = p.clone().project(cam);
        return [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h];
      };
      // the plane: its near edge on the felt, its far edge raised (planar3d.ts tips it about its width)
      const { x, z, scale, tilt } = planarSpot(all);
      const hw = (CARD_H * scale) / 2;
      const d = (CARD_W * scale) / 2;
      const plane = [[-hw, 0, d], [hw, 0, d], [hw, 2 * d * Math.sin(tilt), -d], [-hw, 2 * d * Math.sin(tilt), -d]]
        .map(([px, py, pz]) => screen(new THREE.Vector3(x + px!, py!, z + (pz! > 0 ? d * Math.cos(tilt) : -d * Math.cos(tilt)))));
      // every mat (to its felt hem) and every zone well, flat on the table
      const rect = (seat: Seat, cx: number, cz: number, rw: number, rd: number) => [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sz]) => {
        const [wx, wz] = toWorld(seat, cx + (sx! * rw) / 2, cz + (sz! * rd) / 2);
        return screen(new THREE.Vector3(wx, 0, wz));
      });
      const keepOff: [number, number][][] = [];
      for (const seat of all) {
        keepOff.push(rect(seat, 0, 0, MAT_W + 2 * FELT_HEM, MAT_D + 2 * FELT_HEM));
        for (const zone of ["library", "graveyard", "exile"] as const) keepOff.push(rect(seat, ...pileSpot(seat, zone), WELL.w, WELL.h));
        for (const slot of [0, 1]) keepOff.push(rect(seat, ...commandSlot(seat, slot), COMMAND_WELL.w, COMMAND_WELL.h));
      }
      for (const [i, poly] of keepOff.entries()) expect([i, overlaps(plane, poly)]).toEqual([i, false]);
      // and it is on screen
      for (const [px, py] of plane) expect(px > 0 && px < w && py > 0 && py < h).toBe(true);
    });
  }
});

/** Two convex polygons (screen px) overlap: no separating axis among their edges' normals. */
function overlaps(a: [number, number][], b: [number, number][]): boolean {
  for (const poly of [a, b]) {
    for (let i = 0; i < poly.length; i++) {
      const [x1, y1] = poly[i]!;
      const [x2, y2] = poly[(i + 1) % poly.length]!;
      const nx = y2 - y1;
      const ny = x1 - x2;
      const span = (p: [number, number][]) => p.map(([px, py]) => px * nx + py * ny);
      const sa = span(a);
      const sb = span(b);
      if (Math.max(...sa) <= Math.min(...sb) || Math.max(...sb) <= Math.min(...sa)) return false;
    }
  }
  return true;
}

