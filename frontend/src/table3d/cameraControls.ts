/**
 * The 3D table's camera, moved as in Tabletop Simulator: right-drag orbits (around the point the view looks at, its
 * pitch kept between 14° and 85° above the felt), middle-drag pans across the table, the wheel zooms toward the point
 * under the pointer, the arrow keys pan (Shift: faster). The player's moves are an adjustment on top of the current
 * view (the seat, the whole table, a player's board): it stays until Home or 1 (or 0 for the whole table) puts the
 * view back. Orbiting lower than the view's own pitch widens the lens (and brings the camera in to match), so leaning
 * in to the table gains perspective instead of looking flat.
 *
 * Camera only (never game state). three.js math only, no WebGL, so it is unit-tested; TableScene feeds it the pointer
 * and keys and eases the camera to what it returns.
 */
import * as THREE from "three";

/** The player's move of the camera, relative to the view it started from. */
export interface CamAdjust {
  /** Turned about the vertical axis through the look point (radians). */
  yaw: number;
  /** Raised (+) or lowered (−) from the view's own elevation (radians). */
  pitch: number;
  /** The distance, as a share of the view's (below 1: closer). */
  zoom: number;
  /** The look point moved across the table (world units). */
  panX: number;
  panZ: number;
}

export const NO_ADJUST: CamAdjust = { yaw: 0, pitch: 0, zoom: 1, panX: 0, panZ: 0 };

/** How low and how high the camera may orbit (elevation above the felt), and how near and far it may zoom. */
export const PITCH_MIN = THREE.MathUtils.degToRad(14);
export const PITCH_MAX = THREE.MathUtils.degToRad(85);
export const ZOOM_MIN = 0.3;
export const ZOOM_MAX = 2.5;
/** Radians of orbit per pixel dragged. */
export const ORBIT_SPEED = 0.006;

export interface CamPose { pos: THREE.Vector3; look: THREE.Vector3 }

/** The lens (vertical field of view, degrees) at the lowest orbit. */
export const LOW_FOV = 18;

/**
 * The lens for a camera at elevation `elev` (radians), on a view framed at `baseElev` with a `baseFov` lens: that lens
 * at the view's own pitch and above it; below it, widening smoothly to LOW_FOV at the lowest orbit (a long lens seen
 * low reads as flat as a map).
 */
export function fovAt(elev: number, baseElev: number, baseFov: number): number {
  if (elev >= baseElev || baseFov >= LOW_FOV || baseElev <= PITCH_MIN) return baseFov;
  const t = THREE.MathUtils.clamp((baseElev - elev) / (baseElev - PITCH_MIN), 0, 1);
  return baseFov + (LOW_FOV - baseFov) * t * t * (3 - 2 * t);
}

/** How far a camera with lens `fov` stands, as a share of one with `baseFov`, for what it looks at to be the same size. */
export function reachFor(fov: number, baseFov: number): number {
  const half = (deg: number) => Math.tan(THREE.MathUtils.degToRad(deg) / 2);
  return half(baseFov) / half(fov);
}

/** How far the look point may wander: the table top's half extents (it never leaves the table). */
export interface PanBounds { hx: number; hz: number }

function elevationOf(base: CamPose): { r: number; elev: number; az: number } {
  const off = base.pos.clone().sub(base.look);
  const r = Math.max(1e-6, off.length());
  return { r, elev: Math.asin(THREE.MathUtils.clamp(off.y / r, -1, 1)), az: Math.atan2(off.x, off.z) };
}

/** The adjustment kept in bounds: zoom and pitch in their ranges, the look point on the table. */
export function clampAdjust(a: CamAdjust, base: CamPose, bounds?: PanBounds): CamAdjust {
  const { elev } = elevationOf(base);
  const pitch = THREE.MathUtils.clamp(elev + a.pitch, PITCH_MIN, Math.max(PITCH_MIN, PITCH_MAX)) - elev;
  const zoom = THREE.MathUtils.clamp(a.zoom, ZOOM_MIN, ZOOM_MAX);
  let { panX, panZ } = a;
  if (bounds) {
    panX = THREE.MathUtils.clamp(base.look.x + panX, -bounds.hx, bounds.hx) - base.look.x;
    panZ = THREE.MathUtils.clamp(base.look.z + panZ, -bounds.hz, bounds.hz) - base.look.z;
  }
  return { yaw: a.yaw, pitch, zoom, panX, panZ };
}

/**
 * Where the camera is for a view (`base`) and the player's adjustment. With `baseFov` (the view's lens), an orbit below
 * the view's pitch widens the lens (fovAt) and the camera comes in to match (reachFor); `fov` is the lens to use.
 */
export function adjustCamera(base: CamPose, a: CamAdjust, baseFov?: number): CamPose & { fov?: number } {
  const { r, elev, az } = elevationOf(base);
  const e = THREE.MathUtils.clamp(elev + a.pitch, Math.min(elev, PITCH_MIN), Math.max(elev, PITCH_MAX));
  const yaw = az + a.yaw;
  const fov = baseFov === undefined ? undefined : fovAt(e, elev, baseFov);
  const dist = r * a.zoom * (fov === undefined ? 1 : reachFor(fov, baseFov!));
  const look = base.look.clone().add(new THREE.Vector3(a.panX, 0, a.panZ));
  const flat = Math.cos(e) * dist;
  const pos = look.clone().add(new THREE.Vector3(Math.sin(yaw) * flat, Math.sin(e) * dist, Math.cos(yaw) * flat));
  return fov === undefined ? { pos, look } : { pos, look, fov };
}

/** Right-drag: turn around the look point (dragging sideways) and tilt (dragging down raises the camera). */
export function orbitBy(a: CamAdjust, dx: number, dy: number, base: CamPose, bounds?: PanBounds): CamAdjust {
  return clampAdjust({ ...a, yaw: a.yaw - dx * ORBIT_SPEED, pitch: a.pitch + dy * ORBIT_SPEED }, base, bounds);
}

/** Pan: move the look point across the table by (dx, dz) world units. */
export function panBy(a: CamAdjust, dx: number, dz: number, base: CamPose, bounds?: PanBounds): CamAdjust {
  return clampAdjust({ ...a, panX: a.panX + dx, panZ: a.panZ + dz }, base, bounds);
}

/**
 * The wheel: zoom by `factor` (below 1: closer) toward `ground`, the point on the table under the pointer, which stays
 * under the pointer (the whole camera scales about it). At the zoom's limits it stops.
 */
export function zoomAt(a: CamAdjust, base: CamPose, ground: THREE.Vector3, factor: number, bounds?: PanBounds): CamAdjust {
  const zoom = THREE.MathUtils.clamp(a.zoom * factor, ZOOM_MIN, ZOOM_MAX);
  const f = zoom / a.zoom;
  if (Math.abs(f - 1) < 1e-9) return a;
  const now = adjustCamera(base, a);
  const g = ground.clone().setY(0);
  const look = g.clone().add(now.look.clone().sub(g).multiplyScalar(f));
  return clampAdjust({ ...a, zoom, panX: look.x - base.look.x, panZ: look.z - base.look.z }, base, bounds);
}

/**
 * An arrow key: pan a step across the table as the screen shows it (left/right along the screen's horizontal, up/down
 * away from or toward me), a step growing with the distance; Shift goes three times as far. `lens`: how much of the
 * view a unit of distance spans, against a 42° lens (a longer lens sees less, so it steps less).
 */
export function panKey(a: CamAdjust, base: CamPose, dir: "left" | "right" | "up" | "down", fast: boolean, bounds?: PanBounds, lens = 1): CamAdjust {
  const now = adjustCamera(base, a);
  const fwd = now.look.clone().sub(now.pos).setY(0);
  if (fwd.lengthSq() < 1e-9) fwd.set(0, 0, -1);
  fwd.normalize();
  const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
  const step = now.pos.distanceTo(now.look) * 0.045 * lens * (fast ? 3 : 1);
  const v = dir === "left" ? right.multiplyScalar(-step) : dir === "right" ? right.multiplyScalar(step) : dir === "up" ? fwd.multiplyScalar(step) : fwd.multiplyScalar(-step);
  return panBy(a, v.x, v.z, base, bounds);
}

/** Is this the view as the preset frames it (nothing moved)? */
export function isUnmoved(a: CamAdjust): boolean {
  return Math.abs(a.yaw) < 1e-6 && Math.abs(a.pitch) < 1e-6 && Math.abs(a.zoom - 1) < 1e-6 && Math.abs(a.panX) < 1e-6 && Math.abs(a.panZ) < 1e-6;
}
