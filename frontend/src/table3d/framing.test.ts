import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { fitCamera, seatElevation, seatPoints, tableRect, viewDir } from "./framing";
import { MAT_D, MAT_W, seatCamera, seats, tableSize, toWorld, type Seat } from "./layout";

/** The table's camera as TableScene sets it up: the frame lifted by the hand band (setViewOffset). */
function lens(w: number, h: number): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(42, w / h, 0.1, 400);
  const band = Math.round(h * 0.16);
  cam.setViewOffset(w, h + band, 0, band, w, h);
  cam.updateProjectionMatrix();
  return cam;
}

/** A mat's height and width on screen (px), measured across its middle. */
function matOnScreen(cam: THREE.PerspectiveCamera, seat: Seat, w: number, h: number): { w: number; h: number } {
  const at = (lx: number, lz: number) => {
    const [x, z] = toWorld(seat, lx, lz);
    const v = new THREE.Vector3(x, 0, z).project(cam);
    return [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h] as const;
  };
  const near = at(0, MAT_D / 2), far = at(0, -MAT_D / 2), l = at(-MAT_W / 2, 0), r = at(MAT_W / 2, 0);
  return { w: Math.hypot(r[0] - l[0], r[1] - l[1]), h: Math.hypot(near[0] - far[0], near[1] - far[1]) };
}

function seatView(n: number, w: number, h: number) {
  const s = seats(Array.from({ length: n }, (_, i) => `p${i + 1}`), "p1");
  const mine = s[0]!;
  const pts = s.flatMap((seat) => seatPoints(seat, { buttons: seat === mine }));
  const cam = lens(w, h);
  const rect = tableRect(w, h);
  const f = fitCamera(cam, pts, viewDir(mine.rot, seatElevation(n)), rect);
  cam.position.copy(f.pos);
  cam.lookAt(f.look);
  cam.updateMatrixWorld(true);
  return { s, mine, pts, cam, rect };
}

describe("3D table framing", () => {
  for (const [n, w, h] of [[4, 1440, 855], [4, 1920, 1035], [2, 1440, 855], [6, 1440, 855], [3, 1280, 675]] as const) {
    it(`fits ${n} seats at ${w}×${h} inside the screen, filling it one way or the other`, () => {
      const { pts, cam, rect } = seatView(n, w, h);
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const p of pts) {
        const v = p.clone().project(cam);
        x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y);
      }
      const eps = 0.01;
      expect(x0).toBeGreaterThanOrEqual(rect.left - eps);
      expect(x1).toBeLessThanOrEqual(rect.right + eps);
      expect(y0).toBeGreaterThanOrEqual(rect.bottom - eps);
      expect(y1).toBeLessThanOrEqual(rect.top + eps);
      const fillsW = x1 - x0 > (rect.right - rect.left) * 0.98;
      const fillsH = y1 - y0 > (rect.top - rect.bottom) * 0.98;
      expect(fillsW || fillsH).toBe(true);
    });
  }

  it("gives a 4-player table's far mats more of the screen than the old seat camera did", () => {
    const w = 1440, h = 855;
    const { s, cam } = seatView(4, w, h);
    const old = lens(w, h);
    const mine = s[0]!;
    const c = seatCamera(mine, tableSize(s), w / h);
    old.position.set(...c.pos);
    old.lookAt(new THREE.Vector3(...c.look));
    old.updateMatrixWorld(true);
    const far = s.find((x) => x.side !== mine.side)!;
    const now = matOnScreen(cam, far, w, h);
    const before = matOnScreen(old, far, w, h);
    expect(now.h * now.w).toBeGreaterThan(before.h * before.w * 1.2);
    // and the far row is nearly as tall on screen as my own
    const own = matOnScreen(cam, mine, w, h);
    expect(now.h / own.h).toBeGreaterThan(0.75);
  });

  it("gives six seats' far mats more height than the old seat camera did", () => {
    const w = 1440, h = 855;
    const { s, cam } = seatView(6, w, h);
    const old = lens(w, h);
    const mine = s[0]!;
    const c = seatCamera(mine, tableSize(s), w / h);
    old.position.set(...c.pos);
    old.lookAt(new THREE.Vector3(...c.look));
    old.updateMatrixWorld(true);
    const far = s.find((x) => x.side !== mine.side && Math.abs(x.x) < 1)!;
    expect(matOnScreen(cam, far, w, h).h).toBeGreaterThan(matOnScreen(old, far, w, h).h * 1.15);
  });
});
