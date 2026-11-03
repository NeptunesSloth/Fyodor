/**
 * Camera framing for the 3D table: the seat view, the whole-table view and Look (2–6) frame the play area as large as
 * it will go on this screen, between the top bar and the hand, instead of a fixed distance that left the far mats
 * small and a band of empty wood around the table. The camera looks steeply down, so the far row is foreshortened
 * less and gets nearly as much screen as my own row.
 *
 * Camera only (never game state). three.js math only, no WebGL, so it is unit-tested.
 */
import * as THREE from "three";
import { CARD_W, MAT_D, MAT_W, STRIP_X, toWorld, type Seat } from "./layout";

/** The part of the canvas (normalized device coordinates, −1..1) the framed area must fit in. */
export interface FrameRect { left: number; right: number; bottom: number; top: number }

/** How steeply each view looks down (radians from the table top). */
export const SEAT_ELEVATION = 1.08;
export const FOCUS_ELEVATION = 1.0;
export const OVERVIEW_ELEVATION = 1.36;

/**
 * A seat's play area on the felt: its mat and the piles on either side; with `buttons`, my seat's buttons row past my
 * mat's near edge too.
 */
export function seatPoints(seat: Seat, opts: { buttons?: boolean; piles?: boolean } = {}): THREE.Vector3[] {
  const hx = opts.piles === false ? MAT_W / 2 + 0.2 : STRIP_X + CARD_W / 2 + 0.1;
  const hz = MAT_D / 2 + 0.2;
  const local: [number, number][] = [[-hx, -hz], [hx, -hz], [hx, hz], [-hx, hz]];
  if (opts.buttons) local.push([-4.7, MAT_D / 2 + 0.85], [0.7, MAT_D / 2 + 0.85]);
  return local.map(([lx, lz]) => {
    const [x, z] = toWorld(seat, lx, lz);
    return new THREE.Vector3(x, 0, z);
  });
}

/** The unit direction from the look point to a camera at my side of the table, `elevation` up from the felt. */
export function viewDir(rot: number, elevation: number): THREE.Vector3 {
  const flat = Math.cos(elevation);
  return new THREE.Vector3(Math.sin(rot) * flat, Math.sin(elevation), Math.cos(rot) * flat);
}

const tmp = new THREE.Vector3();

function bounds(cam: THREE.PerspectiveCamera, pts: THREE.Vector3[]): [number, number, number, number] {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const p of pts) {
    tmp.copy(p).project(cam);
    x0 = Math.min(x0, tmp.x); x1 = Math.max(x1, tmp.x); y0 = Math.min(y0, tmp.y); y1 = Math.max(y1, tmp.y);
  }
  return [x0, x1, y0, y1];
}

/**
 * The camera (position and look point) that shows every point as large as it will go inside `rect`, looking along
 * `dir` (from the look point toward the camera). `cam` brings the lens (fov, aspect, view offset) and is moved to try
 * distances; the caller keeps its own camera.
 */
export function fitCamera(cam: THREE.PerspectiveCamera, pts: THREE.Vector3[], dir: THREE.Vector3, rect: FrameRect): { pos: THREE.Vector3; look: THREE.Vector3 } {
  const look = new THREE.Vector3();
  for (const p of pts) look.add(p);
  look.multiplyScalar(1 / Math.max(1, pts.length)).setY(0);
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
  for (let i = 0; i < 12; i++) {
    place();
    const [x0, x1, y0, y1] = bounds(cam, pts);
    const scale = Math.max((x1 - x0) / (rect.right - rect.left), (y1 - y0) / (rect.top - rect.bottom));
    // what one world unit along the felt (to the right, and away from me) moves on screen, here
    right.setFromMatrixColumn(cam.matrixWorld, 0).setY(0).normalize();
    ahead.set(-dir.x, 0, -dir.z).normalize();
    const c = tmp.copy(look).project(cam);
    const cx = c.x, cy = c.y;
    const rx = tmp.copy(look).add(right).project(cam).x - cx;
    const ay = tmp.copy(look).add(ahead).project(cam).y - cy;
    // centre the points' box in the rect (at this distance), then move in or out to fill it
    const dx = (x0 + x1) / 2 - (rect.left + rect.right) / 2;
    const dy = (y0 + y1) / 2 - (rect.bottom + rect.top) / 2;
    if (Math.abs(rx) > 1e-6) look.addScaledVector(right, dx / rx);
    if (Math.abs(ay) > 1e-6) look.addScaledVector(ahead, dy / ay);
    dist *= scale;
    if (Math.abs(scale - 1) < 0.002 && Math.abs(dx) < 0.002 && Math.abs(dy) < 0.002) break;
  }
  place();
  return { pos: cam.position.clone(), look };
}

/**
 * The canvas area the table may fill, in normalized device coordinates: a hair inside the top and the sides, and
 * above my hand's resting fan (its cards peek ~72% of their width, table3d.css), so my near row is never under it;
 * `reserveTop` keeps a strip clear under the top bar (a first-game tip sits there, over the wood, not the cards).
 */
export function tableRect(width: number, height: number, reserveTop = 0): FrameRect {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  const handW = Math.min(184, Math.max(112, w * 0.084));
  const hand = handW * 0.72 + 12;
  const side = 10;
  const top = Math.max(8, reserveTop);
  return { left: -1 + (2 * side) / w, right: 1 - (2 * side) / w, top: 1 - (2 * top) / h, bottom: -1 + (2 * hand) / h };
}
