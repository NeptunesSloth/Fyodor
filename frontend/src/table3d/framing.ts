/**
 * Camera framing for the 3D table: the seat view, the whole-table view and Look (2–6) frame the play area as large as
 * it will go on this screen, between the top bar and the hand and clear of the fixed chrome (the camera strip, the
 * stack pill, the turn dial), instead of a fixed distance that left the far mats small and a band of empty wood around
 * the table. A long lens keeps the far row nearly as large as mine; a 1v1 table, two mats facing across a narrow aisle,
 * is seen lower, so the pair reads wider than tall and fills a wide screen.
 *
 * Camera only (never game state). three.js math only, no WebGL, so it is unit-tested.
 */
import * as THREE from "three";
import { fanCorners, handFan, showsFan } from "./handFan";
import { CARD_W, DUEL_VIEW, HEART, heartSpot, heartTilt, MAT_D, MAT_W, PLATE, plaqueSpot, screenX, STRIP_X, taxSpot, toWorld, type Seat, type TableSize } from "./layout";

/** The part of the canvas (normalized device coordinates, −1..1) the framed area must fit in. */
export interface FrameRect { left: number; right: number; bottom: number; top: number }

/**
 * The table's lens (vertical field of view, degrees): very long, so the far row is foreshortened little (in 1v1 the far
 * mat is about 0.9 as wide and as tall as mine) even though the table is seen low.
 */
export const TABLE_FOV = 8;
/** How much further back a view framed for the old 42° lens must stand to frame the same (the close-ups C, K, X). */
export const LENS_REACH = Math.tan(THREE.MathUtils.degToRad(21)) / Math.tan(THREE.MathUtils.degToRad(TABLE_FOV / 2));
/** The share of the canvas height the frame is lifted by (the hand's band): the picture is the lower part of a taller frame. */
export const HAND_BAND = 0.16;

/**
 * The table's camera lens for a w × h canvas: the picture is the lower part of a frame taller by the hand band (which
 * lifts what the camera looks at above my hand); the aspect is the whole frame's, so nothing is squeezed.
 */
export function tableLens(w: number, h: number, cam = new THREE.PerspectiveCamera()): THREE.PerspectiveCamera {
  const W = Math.max(1, w);
  const H = Math.max(1, h);
  const band = Math.round(H * HAND_BAND);
  cam.fov = TABLE_FOV;
  cam.aspect = W / (H + band);
  cam.setViewOffset(W, H + band, 0, band, W, H);
  cam.updateProjectionMatrix();
  return cam;
}

/**
 * The camera's near and far planes for a camera `dist` from what it looks at and `reach` from the middle of the table:
 * the near plane follows the distance (a fixed 0.1 left the depth buffer too coarse from far out, so the felt, the mats,
 * the pile slots and the card faces, a hair apart, fought and flickered), the far one takes in the whole room.
 */
export function nearFarFor(dist: number, reach: number): { near: number; far: number } {
  const near = Math.min(40, Math.max(0.1, dist * 0.12));
  return { near, far: Math.max(near * 20, reach + ROOM_REACH) };
}

/** How far the room reaches from the table's middle (its sky dome's radius, environment.ts), for the far plane. */
export const ROOM_REACH = 950;

/** The smallest depth step a 24-bit depth buffer tells apart at distance z (perspective, for these near and far planes). */
export function depthStep(z: number, near: number, far: number): number {
  return (z * z * (far - near)) / (far * near * 2 ** 24);
}

/** How steeply each view looks down (radians from the table top). */
export const FOCUS_ELEVATION = 1.0;
export const OVERVIEW_ELEVATION = 1.4;
/** 1v1: low enough that the two facing mats, stacked, read wider than tall and fill a wide screen. */
export const DUEL_ELEVATION = DUEL_VIEW;

/**
 * The seat view's: steep enough that the far row is nearly as large as mine (and my mat as large as it gets: up to
 * four seats, the table fills the width at about this angle); five or six seats make a wide table that can only fill
 * the screen's width, so it looks down further to give every mat more height. Two seats face each other in one
 * column: seen lower, so the pair isn't a tall strip in the middle of a wide screen (a little higher on a narrow,
 * tall screen, which has the height for it). `aspect`: the canvas's width over its height.
 */
export function seatElevation(seats: number, aspect = 16 / 9): number {
  if (seats === 2) return aspect < 1.25 ? DUEL_ELEVATION + 0.12 : DUEL_ELEVATION;
  return seats > 4 ? 1.4 : 1.2;
}

/** How tall a table prop may stand (world units): its top is framed with the table. */
export const PROP_TOP = 1.4;

/**
 * Where the table's props stand (left, then right as I see them), where the seat view sees them whole, a safe way in
 * from the frame's edges and clear of every pile, mat, heart and plate. 1v1: the far corners of the far seat's own
 * edge, beyond its command zone and its library, either side of its heart, plate and fan. More seats: along the aisle's
 * middle line, well inside the outermost piles (the hearts and plates sit by their own mats).
 */
export function propSpots(all: Seat[], size: TableSize): [number, number][] {
  const far = all.find((s) => s.duel && s.side === "north");
  if (far) return [-1, 1].map((sx) => toWorld(far, screenX(far, sx * (STRIP_X + 0.3)), MAT_D / 2 + 0.95));
  let reach = 0;
  for (const s of all) reach = Math.max(reach, Math.abs(s.x) + STRIP_X);
  const x = Math.min(reach - 1.4, size.w / 2 - 2);
  return [[-x, 0], [x, 0]];
}

/**
 * A seat's play area on the felt: its mat and the piles on either side; with `buttons`, my seat's buttons row past my
 * mat's near edge too. In 1v1 also its heart and plate past its own edge and, across the table, its fan of backs.
 */
export function seatPoints(seat: Seat, opts: { buttons?: boolean; piles?: boolean; elevation?: number } = {}): THREE.Vector3[] {
  const hx = opts.piles === false ? MAT_W / 2 + 0.2 : STRIP_X + CARD_W / 2 + 0.1;
  const hz = MAT_D / 2 + 0.2;
  const local: [number, number, number][] = [[-hx, 0, -hz], [hx, 0, -hz], [hx, 0, hz], [-hx, 0, hz]];
  if (opts.piles !== false) {
    // the commander tax counters, just outside the command zone's slots
    const [tx, tz] = taxSpot(0, seat);
    const [, tz2] = taxSpot(1, seat);
    local.push([tx + Math.sign(tx) * 0.32, 0, tz], [tx + Math.sign(tx) * 0.32, 0, tz2]);
  }
  if (opts.piles !== false) {
    // the heart, tipped up toward the camera (my side of the table): its edge nearest me resting over the felt, its far
    // edge raised; and the plate on its left (as I see it), a box standing as tall as the heart
    const [lx, lz] = heartSpot(seat);
    const t = heartTilt(seat);
    const half = (HEART.h / 2) * Math.cos(t);
    const toMe = Math.cos(seat.rot) >= 0 ? 1 : -1; // mat-local +z is toward me for my row
    for (const dx of [-HEART.w / 2, HEART.w / 2]) local.push([lx + dx, HEART.y, lz + toMe * half], [lx + dx, HEART.y + HEART.h * Math.sin(t), lz - toMe * half]);
  }
  if (seat.duel && opts.buttons) local.push([-hx, 0, MAT_D / 2 + 1.0], [hx, 0, MAT_D / 2 + 1.0]);
  else if (opts.buttons) local.push([-4.7, 0, MAT_D / 2 + 0.85], [0.7, 0, MAT_D / 2 + 0.85]);
  const out = local.map(([lx, y, lz]) => {
    const [x, z] = toWorld(seat, lx, lz);
    return new THREE.Vector3(x, y, z);
  });
  if (opts.piles !== false) out.push(...plateCorners(seat, opts.elevation ?? (seat.duel ? DUEL_VIEW : 1.2)));
  // a seat across the table: its fan of backs standing past its own edge (as large as the fan gets)
  if (!opts.buttons && opts.piles !== false && showsFan(seat)) for (const c of handFan(seat, 12)) out.push(...fanCorners(c));
  return out;
}

/**
 * A seat's plate as the camera sees it: a box facing the camera (the DOM plate, drawn at its size on the table:
 * layout.ts PLATE), its middle level with its heart's, just left of it. `elevation`: the camera's, from my side.
 */
export function plateCorners(seat: Seat, elevation: number): THREE.Vector3[] {
  const [px, pz] = plaqueSpot(seat);
  const [x, z] = toWorld(seat, px, pz);
  const mid = new THREE.Vector3(x, HEART.y + Math.sin(heartTilt(seat)) * HEART.h * 0.5, z);
  const up = new THREE.Vector3(0, Math.cos(elevation), -Math.sin(elevation)).multiplyScalar(PLATE.h / 2);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => mid.clone().add(new THREE.Vector3((sx! * PLATE.w) / 2, 0, 0)).addScaledVector(up, sy!));
}

/** Everything the seat view and the whole-table view must show: every seat's area, and the props' tops. */
export function tablePoints(all: Seat[], mine: Seat, size: TableSize, elevation?: number): THREE.Vector3[] {
  const pts = all.flatMap((s) => seatPoints(s, { buttons: s === mine, elevation }));
  for (const [x, z] of propSpots(all, size)) pts.push(new THREE.Vector3(x, PROP_TOP, z), new THREE.Vector3(x, 0, z));
  return pts;
}

/** The unit direction from the look point to a camera at my side of the table, `elevation` up from the felt. */
export function viewDir(rot: number, elevation: number): THREE.Vector3 {
  const flat = Math.cos(elevation);
  return new THREE.Vector3(Math.sin(rot) * flat, Math.sin(elevation), Math.cos(rot) * flat);
}

const tmp = new THREE.Vector3();

/** A point to frame: a world point, or one with a fixed offset on screen (NDC) from it, for a DOM box tied to it. */
export type FitPoint = THREE.Vector3 | { at: THREE.Vector3; ox: number; oy: number };

/**
 * The camera (position and look point) that shows every point as large as it will go inside `rect`, looking along
 * `dir` (from the look point toward the camera), and keeps every point out of the `keepOut` boxes (fixed chrome in a
 * corner: a point level with a box stays on the open side of it). `cam` brings the lens (fov, aspect, view offset) and
 * is moved to try distances; the caller keeps its own camera.
 */
export function fitCamera(cam: THREE.PerspectiveCamera, pts: FitPoint[], dir: THREE.Vector3, rect: FrameRect, keepOut: FrameRect[] = []): { pos: THREE.Vector3; look: THREE.Vector3 } {
  const free = fitFree(cam, pts, dir, rect);
  if (!keepOut.length) return free;
  // with chrome in the corners: as large as it can be while every point keeps clear of it, the table moved up, down
  // or aside as needed (as near the middle as allowed); found by halving the range of distances
  const d0 = free.pos.distanceTo(free.look);
  let lo = 1, hi = 1;
  let best = clearOf(cam, pts, dir, rect, keepOut, free.look, d0);
  if (best) return best;
  while (hi < 6) {
    hi *= 1.25;
    best = clearOf(cam, pts, dir, rect, keepOut, free.look, d0 * hi);
    if (best) break;
  }
  if (!best) return free;
  for (let i = 0; i < 14; i++) {
    const mid = (lo + hi) / 2;
    const f = clearOf(cam, pts, dir, rect, keepOut, free.look, d0 * mid);
    if (f) { hi = mid; best = f; } else lo = mid;
  }
  cam.position.copy(best.pos);
  cam.lookAt(best.look);
  cam.updateMatrixWorld(true);
  return best;
}

/**
 * The camera at `dist` along `dir`, its look point moved from `look` so that every point is inside `rect` and clear
 * of the boxes, as near the middle as allowed; null when no move does it at this distance.
 */
function clearOf(cam: THREE.PerspectiveCamera, all: FitPoint[], dir: THREE.Vector3, rect: FrameRect, keepOut: FrameRect[], look0: THREE.Vector3, dist: number): { pos: THREE.Vector3; look: THREE.Vector3 } | null {
  const n = all.length;
  const pts = all.map((p) => (p instanceof THREE.Vector3 ? p : p.at));
  const ox = all.map((p) => (p instanceof THREE.Vector3 ? 0 : p.ox));
  const oy = all.map((p) => (p instanceof THREE.Vector3 ? 0 : p.oy));
  const look = look0.clone();
  const right = new THREE.Vector3();
  const ahead = new THREE.Vector3(-dir.x, 0, -dir.z).normalize();
  const px = new Float64Array(n);
  const py = new Float64Array(n);
  const place = () => {
    cam.position.copy(look).addScaledVector(dir, dist);
    cam.up.set(0, 1, 0);
    cam.lookAt(look);
    cam.updateMatrixWorld(true);
    for (let i = 0; i < n; i++) {
      tmp.copy(pts[i]!).project(cam);
      px[i] = tmp.x + ox[i]!;
      py[i] = tmp.y + oy[i]!;
    }
  };
  // the open span of a row at height y: the rect, less any box level with it
  const span = (y: number): [number, number] => {
    let l = rect.left, r = rect.right;
    for (const k of keepOut) {
      if (y < k.bottom || y > k.top) continue;
      if (k.left > 0) r = Math.min(r, k.left);
      else if (k.right < 0) l = Math.max(l, k.right);
    }
    return [l, r];
  };
  for (let pass = 0; pass < 3; pass++) {
    place();
    let y0 = Infinity, y1 = -Infinity, x0 = Infinity, x1 = -Infinity;
    for (let i = 0; i < n; i++) {
      y0 = Math.min(y0, py[i]!); y1 = Math.max(y1, py[i]!); x0 = Math.min(x0, px[i]!); x1 = Math.max(x1, px[i]!);
    }
    const syLo = rect.bottom - y0;
    const syHi = rect.top - y1;
    if (syLo > syHi + 1e-9) return null;
    const centredY = (rect.bottom + rect.top) / 2 - (y0 + y1) / 2;
    const centredX = (rect.left + rect.right) / 2 - (x0 + x1) / 2;
    // try heights from the middle outward; the first that leaves room sideways wins
    const steps = 40;
    const tries: number[] = [];
    for (let i = 0; i <= steps; i++) tries.push(syLo + ((syHi - syLo) * i) / steps);
    tries.push(Math.min(syHi, Math.max(syLo, centredY)));
    tries.sort((a, b) => Math.abs(a - centredY) - Math.abs(b - centredY));
    let found: [number, number] | null = null;
    for (const sy of tries) {
      let a = -Infinity, b = Infinity;
      for (let i = 0; i < n && a <= b; i++) {
        const [l, r] = span(py[i]! + sy);
        a = Math.max(a, l - px[i]!);
        b = Math.min(b, r - px[i]!);
      }
      if (a <= b) { found = [Math.min(b, Math.max(a, centredX)), sy]; break; }
    }
    if (!found) return null;
    const [sx, sy] = found;
    if (Math.abs(sx) < 1e-4 && Math.abs(sy) < 1e-4) break;
    // move the look point to shift the picture by (sx, sy)
    const c = tmp.copy(look).project(cam);
    const cx = c.x, cy = c.y;
    right.setFromMatrixColumn(cam.matrixWorld, 0).setY(0).normalize();
    const rx = tmp.copy(look).add(right).project(cam).x - cx;
    const ry = tmp.copy(look).add(ahead).project(cam).y - cy;
    if (Math.abs(rx) > 1e-6) look.addScaledVector(right, -sx / rx);
    if (Math.abs(ry) > 1e-6) look.addScaledVector(ahead, -sy / ry);
  }
  place();
  // the shift is close to a plain slide of the picture, not exactly one: only an answer that holds counts
  for (let i = 0; i < n; i++) {
    if (py[i]! < rect.bottom - 0.004 || py[i]! > rect.top + 0.004) return null;
    const [l, r] = span(py[i]!);
    if (px[i]! < l - 0.004 || px[i]! > r + 0.004) return null;
  }
  return { pos: cam.position.clone(), look: look.clone() };
}

/** The fit with nothing in the way: the points' box as large as the rect allows, centred in it. */
function fitFree(cam: THREE.PerspectiveCamera, all: FitPoint[], dir: THREE.Vector3, rect: FrameRect): { pos: THREE.Vector3; look: THREE.Vector3 } {
  const n = all.length;
  const pts = all.map((p) => (p instanceof THREE.Vector3 ? p : p.at));
  const ox = Float64Array.from(all, (p) => (p instanceof THREE.Vector3 ? 0 : p.ox));
  const oy = Float64Array.from(all, (p) => (p instanceof THREE.Vector3 ? 0 : p.oy));
  const look = new THREE.Vector3();
  for (const p of pts) look.add(p);
  look.multiplyScalar(1 / Math.max(1, n)).setY(0);
  let span = 1;
  for (const p of pts) span = Math.max(span, p.distanceTo(look));
  let dist = (span * 2) / Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
  const right = new THREE.Vector3();
  const ahead = new THREE.Vector3();
  const place = () => {
    cam.position.copy(look).addScaledVector(dir, dist);
    cam.up.set(0, 1, 0);
    cam.lookAt(look);
    cam.updateMatrixWorld(true);
  };
  const px = new Float64Array(n);
  const py = new Float64Array(n);
  // each point's bounds (for its projection, so less its screen offset): x between lo and hi, y between ylo and yhi
  const lo = new Float64Array(n);
  const hi = new Float64Array(n);
  const ylo = Float64Array.from(oy, (o) => rect.bottom - o);
  const yhi = Float64Array.from(oy, (o) => rect.top - o);
  for (let iter = 0; iter < 24; iter++) {
    place();
    for (let i = 0; i < n; i++) {
      tmp.copy(pts[i]!).project(cam);
      px[i] = tmp.x;
      py[i] = tmp.y;
      lo[i] = rect.left - ox[i]!;
      hi[i] = rect.right - ox[i]!;
    }
    const c = tmp.copy(look).project(cam);
    const cx = c.x, cy = c.y;
    // the zoom that lets every pair of points fit between their bounds (one scale for both axes)
    let k = 0;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const dx = px[j]! - px[i]!;
        if (dx > 0) k = Math.max(k, dx / Math.max(1e-3, hi[j]! - lo[i]!));
        const dy = py[j]! - py[i]!;
        if (dy > 0) k = Math.max(k, dy / Math.max(1e-3, yhi[j]! - ylo[i]!));
      }
    }
    if (k <= 0) k = 1;
    // at that zoom, the shift that keeps everyone in bounds, as near the middle of the rect as allowed
    let a = -Infinity, b = Infinity, ay = -Infinity, by = Infinity, x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < n; i++) {
      const x = cx + (px[i]! - cx) / k;
      const y = cy + (py[i]! - cy) / k;
      a = Math.max(a, lo[i]! - x);
      b = Math.min(b, hi[i]! - x);
      ay = Math.max(ay, ylo[i]! - y);
      by = Math.min(by, yhi[i]! - y);
      x0 = Math.min(x0, x + ox[i]!); x1 = Math.max(x1, x + ox[i]!); y0 = Math.min(y0, y + oy[i]!); y1 = Math.max(y1, y + oy[i]!);
    }
    const centred = (rect.left + rect.right) / 2 - (x0 + x1) / 2;
    const sx = a <= b ? Math.min(b, Math.max(a, centred)) : (a + b) / 2;
    const placed = (rect.bottom + rect.top) / 2 - (y0 + y1) / 2;
    const sy = ay <= by ? Math.min(by, Math.max(ay, placed)) : (ay + by) / 2;
    // what one world unit along the felt (to the right, and away from me) moves on screen, here
    right.setFromMatrixColumn(cam.matrixWorld, 0).setY(0).normalize();
    ahead.set(-dir.x, 0, -dir.z).normalize();
    const rx = tmp.copy(look).add(right).project(cam).x - cx;
    const ry = tmp.copy(look).add(ahead).project(cam).y - cy;
    if (Math.abs(rx) > 1e-6) look.addScaledVector(right, -sx * k / rx);
    if (Math.abs(ry) > 1e-6) look.addScaledVector(ahead, -sy * k / ry);
    dist *= k;
    if (Math.abs(k - 1) < 0.001 && Math.abs(sx) < 0.001 && Math.abs(sy) < 0.001) break;
  }
  place();
  return { pos: cam.position.clone(), look };
}

/**
 * The canvas area the table may fill, in normalized device coordinates: a hair inside the top and the sides, and
 * above my hand's resting fan (its cards peek ~52% of their height, table3d.css), so my near row is never under it;
 * `reserveTop` keeps a strip clear under the top bar (a first-game tip sits there, over the wood, not the cards).
 */
export function tableRect(width: number, height: number, reserveTop = 0): FrameRect {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  const handW = Math.min(184, Math.max(112, w * 0.084));
  const hand = Math.min(h * 0.3, handW * 0.72 + 12);
  const side = Math.min(10, w * 0.02);
  const top = Math.min(h * 0.3, Math.max(8, reserveTop));
  return { left: -1 + (2 * side) / w, right: 1 - (2 * side) / w, top: 1 - (2 * top) / h, bottom: -1 + (2 * hand) / h };
}

/** A box on the canvas (CSS px, from its top left) in normalized device coordinates, grown by `pad` px. */
export function ndcBox(box: { left: number; top: number; right: number; bottom: number }, width: number, height: number, pad = 8): FrameRect {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  return {
    left: ((box.left - pad) / w) * 2 - 1, right: ((box.right + pad) / w) * 2 - 1,
    top: 1 - ((box.top - pad) / h) * 2, bottom: 1 - ((box.bottom + pad) / h) * 2,
  };
}
