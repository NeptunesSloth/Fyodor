import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { routeAround, type GroundBox } from "./arrows";

const box: GroundBox = { minX: -2, maxX: 2, minZ: -1.5, maxZ: 1.5 };
const outside = (c: THREE.Curve<THREE.Vector3>) => c.getPoints(200).every((p) => !(p.x > box.minX && p.x < box.maxX && p.z > box.minZ && p.z < box.maxZ));

describe("beam routing around the stack", () => {
  it("goes around the stack when the straight path would cross it", () => {
    const a = new THREE.Vector3(0.6, 0.05, -6);
    const b = new THREE.Vector3(0.9, 0.05, 6);
    expect(outside(routeAround(a, b, box))).toBe(true);
  });

  it("bends to the nearer side", () => {
    const a = new THREE.Vector3(1.5, 0.05, -6);
    const b = new THREE.Vector3(1.5, 0.05, 6);
    const mid = routeAround(a, b, box).getPoint(0.5);
    expect(mid.x).toBeGreaterThan(2); // the right side is closer than the left
  });

  it("keeps the plain arc when nothing is in the way", () => {
    const a = new THREE.Vector3(5, 0.05, -6);
    const b = new THREE.Vector3(5, 0.05, 6);
    const mid = routeAround(a, b, box).getPoint(0.5);
    expect(mid.x).toBeCloseTo(5, 5);
    expect(mid.y).toBeGreaterThan(1);
    expect(routeAround(a, b, null).getPoint(0.5).x).toBeCloseTo(5, 5);
  });
});
