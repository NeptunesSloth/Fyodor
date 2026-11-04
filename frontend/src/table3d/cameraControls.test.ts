import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { adjustCamera, clampAdjust, isUnmoved, NO_ADJUST, orbitBy, panBy, panKey, PITCH_MAX, PITCH_MIN, ZOOM_MAX, ZOOM_MIN, zoomAt, type CamPose } from "./cameraControls";
import { tableLens } from "./framing";

const base: CamPose = { look: new THREE.Vector3(0, 0, 1), pos: new THREE.Vector3(0, 20, 36) };
const bounds = { hx: 8, hz: 10 };

function camAt(p: CamPose): THREE.PerspectiveCamera {
  const cam = tableLens(1280, 594);
  cam.position.copy(p.pos);
  cam.lookAt(p.look);
  cam.updateMatrixWorld(true);
  return cam;
}

const elevation = (p: CamPose) => Math.asin((p.pos.y - p.look.y) / p.pos.distanceTo(p.look));

describe("3D table camera, Tabletop Simulator style", () => {
  it("unmoved, it is exactly the view's own camera (Home and 1 put it back)", () => {
    const p = adjustCamera(base, NO_ADJUST);
    expect(p.pos.distanceTo(base.pos)).toBeLessThan(1e-9);
    expect(p.look.distanceTo(base.look)).toBeLessThan(1e-9);
    expect(isUnmoved(NO_ADJUST)).toBe(true);
    expect(isUnmoved(orbitBy(NO_ADJUST, 30, 0, base, bounds))).toBe(false);
  });

  it("right-drag orbits: sideways turns around the look point, down raises the camera, up lowers it, between 25° and 85°", () => {
    const turned = adjustCamera(base, orbitBy(NO_ADJUST, 120, 0, base, bounds));
    expect(turned.look.distanceTo(base.look)).toBeLessThan(1e-9); // around the same point
    expect(turned.pos.distanceTo(turned.look)).toBeCloseTo(base.pos.distanceTo(base.look), 6);
    expect(Math.abs(turned.pos.x)).toBeGreaterThan(5);
    const e0 = elevation(base);
    expect(elevation(adjustCamera(base, orbitBy(NO_ADJUST, 0, 40, base, bounds)))).toBeGreaterThan(e0);
    expect(elevation(adjustCamera(base, orbitBy(NO_ADJUST, 0, -40, base, bounds)))).toBeLessThan(e0);
    expect(elevation(adjustCamera(base, orbitBy(NO_ADJUST, 0, 5000, base, bounds)))).toBeCloseTo(PITCH_MAX, 6);
    expect(elevation(adjustCamera(base, orbitBy(NO_ADJUST, 0, -5000, base, bounds)))).toBeCloseTo(PITCH_MIN, 6);
  });

  it("the wheel zooms toward the pointer: the point of the table under it stays under it", () => {
    const cam = camAt(base);
    const ray = new THREE.Raycaster();
    for (const [nx, ny] of [[0.3, -0.2], [-0.6, 0.4], [0, 0]] as const) {
      ray.setFromCamera(new THREE.Vector2(nx, ny), cam);
      const ground = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3())!;
      for (const factor of [0.8, 1.25]) {
        const a = zoomAt(NO_ADJUST, base, ground, factor);
        const v = ground.clone().project(camAt(adjustCamera(base, a)));
        expect(v.x).toBeCloseTo(nx, 6);
        expect(v.y).toBeCloseTo(ny, 6);
        expect(adjustCamera(base, a).pos.distanceTo(adjustCamera(base, a).look)).toBeCloseTo(base.pos.distanceTo(base.look) * factor, 6);
      }
    }
  });

  it("zoom stops at its limits (0.3 to 2.5 of the view's distance)", () => {
    let a = NO_ADJUST;
    for (let i = 0; i < 100; i++) a = zoomAt(a, base, new THREE.Vector3(), 0.8);
    expect(a.zoom).toBeCloseTo(ZOOM_MIN, 9);
    for (let i = 0; i < 100; i++) a = zoomAt(a, base, new THREE.Vector3(), 1.25);
    expect(a.zoom).toBeCloseTo(ZOOM_MAX, 9);
  });

  it("panning keeps the look point on the table", () => {
    const far = adjustCamera(base, panBy(NO_ADJUST, 100, -100, base, bounds));
    expect(far.look.x).toBeCloseTo(bounds.hx, 9);
    expect(far.look.z).toBeCloseTo(-bounds.hz, 9);
    const clamped = clampAdjust({ ...NO_ADJUST, panX: -50, zoom: 9, pitch: 3 }, base, bounds);
    expect(base.look.x + clamped.panX).toBeCloseTo(-bounds.hx, 9);
    expect(clamped.zoom).toBe(ZOOM_MAX);
  });

  it("the arrow keys pan as the screen shows the table: up is away from me, Shift goes three times as far", () => {
    const up = adjustCamera(base, panKey(NO_ADJUST, base, "up", false, bounds));
    expect(up.look.z).toBeLessThan(base.look.z); // away from my seat (I sit at +z)
    const right = adjustCamera(base, panKey(NO_ADJUST, base, "right", false, bounds));
    expect(right.look.x).toBeGreaterThan(base.look.x);
    const fast = adjustCamera(base, panKey(NO_ADJUST, base, "left", true, bounds));
    const slow = adjustCamera(base, panKey(NO_ADJUST, base, "left", false, bounds));
    expect(base.look.x - fast.look.x).toBeCloseTo(3 * (base.look.x - slow.look.x), 6);
    // turned around the table, "up" follows the view, not the table's axes
    const turned = orbitBy(NO_ADJUST, Math.PI / 2 / 0.006, 0, base, bounds);
    const before = adjustCamera(base, turned);
    const after = adjustCamera(base, panKey(turned, base, "up", false, bounds));
    const moved = after.look.clone().sub(before.look);
    const fwd = before.look.clone().sub(before.pos).setY(0).normalize();
    expect(moved.normalize().dot(fwd)).toBeGreaterThan(0.99);
  });
});
