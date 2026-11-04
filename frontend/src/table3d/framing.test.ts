import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { depthStep, fitCamera, ndcBox, nearFarFor, offMat, plateCorners, propSpots, PROP_TOP, seatElevation, tableLens, tablePoints, tableRect, viewDir, type FrameRect } from "./framing";
import { CARD_W, HEART, heartSpot, heartTilt, MAT_D, MAT_W, seatCamera, seats, STRIP_X, tableSize, toWorld, type Seat } from "./layout";

/** The old lens, before the aspect fix and the long lens: the baseline the old seat camera is measured with. */
function oldLens(w: number, h: number): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(42, w / h, 0.1, 400);
  const band = Math.round(h * 0.16);
  cam.setViewOffset(w, h + band, 0, band, w, h);
  cam.updateProjectionMatrix();
  return cam;
}

type Box = { left: number; top: number; right: number; bottom: number };

/** px on the canvas of a world point. */
function px(cam: THREE.PerspectiveCamera, p: THREE.Vector3, w: number, h: number): [number, number] {
  const v = p.clone().project(cam);
  return [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h];
}

/** A mat's height and width on screen (px), measured across its middle; with `piles`, the width of its whole strip. */
function matOnScreen(cam: THREE.PerspectiveCamera, seat: Seat, w: number, h: number, piles = false): { w: number; h: number } {
  const at = (lx: number, lz: number) => {
    const [x, z] = toWorld(seat, lx, lz);
    return px(cam, new THREE.Vector3(x, 0, z), w, h);
  };
  const half = piles ? STRIP_X + CARD_W / 2 : MAT_W / 2;
  const near = at(0, MAT_D / 2), far = at(0, -MAT_D / 2), l = at(-half, 0), r = at(half, 0);
  return { w: Math.hypot(r[0] - l[0], r[1] - l[1]), h: Math.hypot(near[0] - far[0], near[1] - far[1]) };
}

function seatView(n: number, w: number, h: number, chrome: Box[] = []) {
  const s = seats(Array.from({ length: n }, (_, i) => `p${i + 1}`), "p1");
  const mine = s[0]!;
  const pts = tablePoints(s, mine, tableSize(s), seatElevation(n, w / h));
  const cam = tableLens(w, h);
  const rect = tableRect(w, h);
  const keep = chrome.map((b) => ndcBox(b, w, h));
  const f = fitCamera(cam, pts, viewDir(mine.rot, seatElevation(n, w / h)), rect, keep);
  cam.position.copy(f.pos);
  cam.lookAt(f.look);
  cam.updateMatrixWorld(true);
  return { s, mine, pts, cam, rect, keep };
}

/**
 * The canvas (the window less the 46 px top bar) and the fixed chrome over it as the app lays it out (measured in the
 * real app): the camera strip top left, the stack pill top right, the turn dial bottom right.
 */
const SCREENS: { name: string; w: number; h: number; chrome: Box[] }[] = [
  { name: "1280×640", w: 1280, h: 594, chrome: [{ left: 14, top: 10, right: 75, bottom: 45 }, { left: 1208, top: 8, right: 1268, bottom: 35 }, { left: 974, top: 343, right: 1264, bottom: 536 }] },
  { name: "1920×1080", w: 1920, h: 1034, chrome: [{ left: 14, top: 10, right: 75, bottom: 45 }, { left: 1848, top: 8, right: 1908, bottom: 35 }, { left: 1614, top: 755, right: 1904, bottom: 976 }] },
  { name: "748×851", w: 748, h: 805, chrome: [{ left: 14, top: 10, right: 75, bottom: 45 }, { left: 676, top: 8, right: 736, bottom: 35 }, { left: 442, top: 526, right: 732, bottom: 747 }] },
];

const inside = (v: THREE.Vector3, r: FrameRect, eps = 0.01) => v.x >= r.left - eps && v.x <= r.right + eps && v.y >= r.bottom - eps && v.y <= r.top + eps;
const over = (v: THREE.Vector3, r: FrameRect) => v.x > r.left + 0.005 && v.x < r.right - 0.005 && v.y > r.bottom + 0.005 && v.y < r.top - 0.005;

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

  it("draws the picture unsqueezed: a square on the felt under the camera is as wide as it is deep, seen from above", () => {
    const cam = tableLens(1280, 594);
    cam.position.set(0, 40, 0);
    cam.up.set(0, 0, -1);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld(true);
    const [ax, ay] = px(cam, new THREE.Vector3(-1, 0, -1), 1280, 594);
    const [bx, by] = px(cam, new THREE.Vector3(1, 0, 1), 1280, 594);
    expect(Math.abs(bx - ax) / Math.abs(by - ay)).toBeCloseTo(1, 2);
  });

  it("gives a 4-player table's far mats more of the screen than the old seat camera did", () => {
    const w = 1440, h = 855;
    const { s, cam } = seatView(4, w, h);
    const old = oldLens(w, h);
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
    const old = oldLens(w, h);
    const mine = s[0]!;
    const c = seatCamera(mine, tableSize(s), w / h);
    old.position.set(...c.pos);
    old.lookAt(new THREE.Vector3(...c.look));
    old.updateMatrixWorld(true);
    const far = s.find((x) => x.side !== mine.side && Math.abs(x.x) < 1)!;
    expect(matOnScreen(cam, far, w, h).h).toBeGreaterThan(matOnScreen(old, far, w, h).h * 1.15);
  });

  it("keeps points level with a box in a corner on its open side", () => {
    const pts = [new THREE.Vector3(-5, 0, -3), new THREE.Vector3(5, 0, -3), new THREE.Vector3(5, 0, 3), new THREE.Vector3(-5, 0, 3)];
    const cam = tableLens(1000, 600);
    const rect = tableRect(1000, 600);
    const dial = ndcBox({ left: 700, top: 380, right: 990, bottom: 590 }, 1000, 600);
    const f = fitCamera(cam, pts, viewDir(0, 0.9), rect, [dial]);
    cam.position.copy(f.pos);
    cam.lookAt(f.look);
    cam.updateMatrixWorld(true);
    for (const p of pts) expect(over(p.clone().project(cam), dial)).toBe(false);
    // and it still fills the screen as far as the box allows (it moves aside rather than shrinking to nothing)
    const [l] = px(cam, pts[3]!, 1000, 600);
    const [r] = px(cam, pts[2]!, 1000, 600);
    expect(r - l).toBeGreaterThan(560);
  });

  for (const screen of SCREENS) {
    it(`1v1 at ${screen.name}: mats, piles, hearts, plates, the fan and the props' tops all framed, clear of the chrome`, () => {
      const { s, mine, pts, cam, rect, keep } = seatView(2, screen.w, screen.h, screen.chrome);
      for (const p of pts) {
        const v = p.clone().project(cam);
        expect(inside(v, rect), `${p.toArray().map((x) => x.toFixed(2))}`).toBe(true);
        for (const k of keep) expect(over(v, k)).toBe(false);
      }
      // the props stand where the frame holds them whole
      for (const [x, z] of propSpots(s, tableSize(s))) expect(inside(new THREE.Vector3(x, PROP_TOP, z).project(cam), rect)).toBe(true);
      // my heart stands below my mat on screen (its raised far edge never covers the felt)
      const [lx, lz] = heartSpot(mine);
      const t = heartTilt(mine);
      const [tx, tz] = toWorld(mine, lx, lz - (HEART.h / 2) * Math.cos(t));
      const [, topY] = px(cam, new THREE.Vector3(tx, HEART.y + HEART.h * Math.sin(t), tz), screen.w, screen.h);
      const [ex, ez] = toWorld(mine, lx, MAT_D / 2);
      const [, edgeY] = px(cam, new THREE.Vector3(ex, 0, ez), screen.w, screen.h);
      expect(topY).toBeGreaterThan(edgeY);
    });
  }

  it("1v1 fills a wide screen: each player's mats and zone strips span at least 55% of a 1280×640 window and 65% of a 16:9 one", () => {
    for (const [screen, play, felt] of [[SCREENS[0]!, 0.55, 0.42], [SCREENS[1]!, 0.65, 0.5]] as const) {
      const { mine, cam } = seatView(2, screen.w, screen.h, screen.chrome);
      expect(matOnScreen(cam, mine, screen.w, screen.h, true).w / screen.w, screen.name).toBeGreaterThanOrEqual(play);
      expect(matOnScreen(cam, mine, screen.w, screen.h).w / screen.w, screen.name).toBeGreaterThanOrEqual(felt);
    }
  });

  it("1v1: the far mat is nearly as large on screen as mine, as wide and as tall (a long lens, seen not too low)", () => {
    for (const screen of SCREENS) {
      const { s, mine, cam } = seatView(2, screen.w, screen.h, screen.chrome);
      const far = matOnScreen(cam, s.find((x) => x !== mine)!, screen.w, screen.h);
      const near = matOnScreen(cam, mine, screen.w, screen.h);
      expect(far.w / near.w, screen.name).toBeGreaterThanOrEqual(0.85);
      expect(far.h / near.h, screen.name).toBeGreaterThanOrEqual(0.85);
    }
  });

  it("every seat count: each heart and plate is framed whole, off every mat on screen", () => {
    for (const [n, w, h] of [[2, 1280, 594], [3, 1280, 675], [4, 1920, 1034], [5, 1920, 1034], [6, 1920, 1034]] as const) {
      const { s, cam } = seatView(n, w, h, n === 2 ? SCREENS[0]!.chrome : []);
      const screenBox = (pts: THREE.Vector3[]) => {
        const p = pts.map((v) => px(cam, v, w, h));
        return { l: Math.min(...p.map((q) => q[0])), r: Math.max(...p.map((q) => q[0])), t: Math.min(...p.map((q) => q[1])), b: Math.max(...p.map((q) => q[1])) };
      };
      const mats = s.map((seat) => screenBox([[-MAT_W / 2, -MAT_D / 2], [MAT_W / 2, -MAT_D / 2], [MAT_W / 2, MAT_D / 2], [-MAT_W / 2, MAT_D / 2]].map(([lx, lz]) => {
        const [x, z] = toWorld(seat, lx!, lz!);
        return new THREE.Vector3(x, 0, z);
      })));
      for (const seat of s) {
        const [hx, hz] = heartSpot(seat);
        const t = heartTilt(seat);
        const half = (HEART.h / 2) * Math.cos(t);
        const box = screenBox([
          ...[[hx - HEART.w / 2, HEART.y, hz - half], [hx + HEART.w / 2, HEART.y + HEART.h * Math.sin(t), hz + half], [hx - HEART.w / 2, HEART.y + HEART.h * Math.sin(t), hz - half], [hx + HEART.w / 2, HEART.y, hz + half]].map(([lx, y, lz]) => {
            const [x, z] = toWorld(seat, lx!, lz!);
            return new THREE.Vector3(x, y!, z);
          }),
          ...plateCorners(seat, seatElevation(n, w / h)),
        ]);
        expect(box.l, `${n} seats`).toBeGreaterThan(0);
        expect(box.r, `${n} seats`).toBeLessThan(w);
        expect(box.t, `${n} seats`).toBeGreaterThan(0);
        for (const m of mats) {
          const overlap = Math.min(box.r, m.r) - Math.max(box.l, m.l) > 0 && Math.min(box.b, m.b) - Math.max(box.t, m.t) > 2;
          expect(overlap, `${n} seats: ${seat.player}'s heart and plate over a mat`).toBe(false);
        }
      }
    }
  });

  it("keeps depth fine enough at every zoom that the flat layers a hair apart never fight (the far-zoom flicker)", () => {
    // the smallest gap between flat layers on the felt: the mats (0.002), the contact shadows (0.0026), the pile slots
    // (0.0034), a card's face over its body (0.0012)
    const gap = 0.0006;
    const { cam } = seatView(2, 1920, 1034, SCREENS[1]!.chrome);
    const seat = cam.position.length();
    for (const zoom of [0.3, 0.6, 1, 1.5, 2, 2.5]) {
      const dist = seat * zoom;
      const { near, far } = nearFarFor(dist, dist + 10);
      expect(depthStep(dist * 1.3, near, far), `zoom ${zoom}`).toBeLessThan(gap / 3);
      expect(far).toBeGreaterThan(dist + 10 + 900); // the room's sky dome (radius 900) stays inside the far plane
    }
    // the cause: a fixed near plane of 0.1 at the farthest zoom left steps coarser than the gaps
    expect(depthStep(seat * 2.5, 0.1, 400)).toBeGreaterThan(gap);
  });
});

describe("a plate stays off its own mat", () => {
  // the mat's edge on screen: level from x 100 to 500 at y 300 (the mat above it), or slanting (seen turned)
  it("moves a plate that would reach over the mat's edge away from the mat, and leaves one clear of it", () => {
    const level: [[number, number], [number, number]] = [[100, 300], [500, 300]];
    expect(offMat({ x: 300, y: 310, w: 140, h: 60 }, level, true)).toBe(300 + 30 + 3);
    expect(offMat({ x: 300, y: 360, w: 140, h: 60 }, level, true)).toBe(360);
    // the mat below the plate (a far seat): moved up
    expect(offMat({ x: 300, y: 290, w: 140, h: 60 }, level, false)).toBe(300 - 30 - 3);
    // beside the mat, not over it: left alone
    expect(offMat({ x: 700, y: 300, w: 140, h: 60 }, level, true)).toBe(300);
    // a slanting edge: clear of its lowest point under the plate
    const slant: [[number, number], [number, number]] = [[100, 280], [500, 320]];
    expect(offMat({ x: 300, y: 300, w: 200, h: 40 }, slant, true)).toBeCloseTo(310 + 20 + 3, 6);
  });
});
