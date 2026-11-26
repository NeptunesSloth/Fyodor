import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { MotionCard } from "./motion3d";
import { arc, TableFlip } from "./tableFlip";

// -- flip the table -- cosmetic only: every card goes up and comes back exactly where the table has it
const card = (id: string, x: number): MotionCard => {
  const group = new THREE.Group();
  const target = new THREE.Vector3(x, 0.01, 2);
  group.position.copy(target);
  return { id, group, face: new THREE.Mesh(), overlay: null, target, rot: 0.3, tilt: 0, scale: 1 };
};

describe("table flip (3D)", () => {
  it("rests at both ends of the arc and lifts in between", () => {
    expect(arc(0)).toBe(0);
    expect(arc(1)).toBe(0);
    expect(arc(0.35)).toBeCloseTo(1, 5);
    expect(arc(0.6)).toBeGreaterThan(0.3);
  });

  it("throws the cards up, then puts every one back where it was and gives it back to the glide", () => {
    const cards = [card("a", 0), card("b", 1), card("c", 2)];
    const flip = new TableFlip();
    flip.start(cards, 0, 0, 900);
    expect(flip.active).toBe(true);
    expect(cards.every((c) => c.flying)).toBe(true);
    flip.update(300);
    expect(cards[0]!.group.position.y).toBeGreaterThan(0.5);
    flip.update(5000);
    expect(flip.active).toBe(false);
    for (const c of cards) {
      expect(c.flying).toBe(false);
      expect(c.group.position.distanceTo(c.target)).toBeLessThan(1e-9);
      expect(c.group.rotation.z).toBe(0);
      expect(c.group.rotation.y).toBeCloseTo(0.3);
    }
  });

  it("skips to the end on a click and leaves cards a real flight holds alone", () => {
    const busy = card("busy", 0);
    busy.flying = true;
    const free = card("free", 1);
    const flip = new TableFlip();
    flip.start([busy, free], Math.PI, 0, 900);
    expect(flip.count).toBe(1);
    flip.finish();
    flip.update(10);
    expect(flip.active).toBe(false);
    expect(free.flying).toBe(false);
    expect(busy.flying).toBe(true);
  });
});
