import { describe, expect, it } from "vitest";
import { cannonSpot } from "./cannon3d";
import { CARD_H, CARD_W, HEART, heartSpot, MAT_D, MAT_W, planarSpot, PLATE, plaqueSpot, RAIL, seats, STACK_REACH, tableSize, toLocal, toWorld } from "./layout";

// -- planechase -- the face-up plane lying in the aisle of the 3D table (TableScene.syncPlanar; table3d/planar3d.ts)
describe("the plane's place on the 3D table", () => {
  for (const n of [1, 2, 3, 4, 5, 6]) {
    it(`lies flat in the aisle, on no mat, clear of the stack, the hearts and the plates (${n} seat${n > 1 ? "s" : ""})`, () => {
      const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
      const { x, z, scale } = planarSpot(all);
      const hw = (CARD_H * scale) / 2; // landscape: its long side along the aisle
      const hd = (CARD_W * scale) / 2;
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
      expect(Math.abs(x) + hw).toBeLessThan(size.w / 2 - RAIL - 0.3); // on the table, inside the rail
      if (n === 2) {
        // a duel's stack lies at the aisle's left end and the dice cannon rolls in at its right end: the plane between
        expect(x - hw).toBeGreaterThan(0);
        expect(x + hw).toBeLessThan(cannonSpot(size.w).spot.x - 1);
      } else {
        expect(x + hw).toBeLessThan(-STACK_REACH - 0.3); // left of the stack's widest fan
      }
    });
  }
});
