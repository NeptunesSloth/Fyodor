import { beforeEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import type { PlanechaseView } from "../types/game";

// the pictures (no DOM here): each "loads" at once, upright (Scryfall's 488 × 680) unless a test says otherwise, or fails
const scan = { w: 488, h: 680, fail: false };
vi.mock("./textures", () => ({
  cardCornerMask: () => new THREE.Texture(),
  contactShadowTexture: () => new THREE.Texture(),
  textCardTexture: () => Object.assign(new THREE.Texture(), { name: "text" }),
  cardImageTexture: (url: string, onError?: () => void, onLoad?: (t: THREE.Texture) => void) => {
    const t = Object.assign(new THREE.Texture(), { name: url });
    queueMicrotask(() => {
      if (scan.fail) onError?.();
      else {
        t.image = { width: scan.w, height: scan.h };
        onLoad?.(t);
      }
    });
    return t;
  },
}));
const { PlanarTable } = await import("./planar3d");
const { CARD_H, CARD_W } = await import("./layout");

const pc = (over: Partial<PlanechaseView> = {}): PlanechaseView => ({
  current: { printing_id: "a", name: "Academy at Tolaria West", phenomenon: false },
  count: 10, visited: [], visited_count: 0, walks: 0, cost: 0, rolls: 0, last_roll: null, ...over,
});
const spot = { x: -7, z: 0, scale: 1.8 };
const loaded = () => new Promise((r) => setTimeout(r, 0));
const planes = (t: InstanceType<typeof PlanarTable>) => t.group.children.length;
const card = (t: InstanceType<typeof PlanarTable>) => t.targets()[0] as THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>;

describe("the plane on the 3D table", () => {
  beforeEach(() => Object.assign(scan, { w: 488, h: 680, fail: false }));

  it("lies flat at its spot, an upright scan turned a quarter clockwise into landscape, clickable once its picture is in", async () => {
    const t = new PlanarTable();
    t.sync(pc(), spot, 0, 0);
    expect(t.group.visible).toBe(true);
    expect(t.group.position.x).toBeCloseTo(-7);
    expect(t.targets()).toEqual([]); // (not shown before its picture: never unturned)
    await loaded();
    const m = card(t);
    expect(m.userData.planar).toBe(true);
    expect(m.rotation.x).toBeCloseTo(-Math.PI / 2); // flat, its picture up
    expect(m.rotation.z).toBeCloseTo(-Math.PI / 2); // a quarter clockwise, seen from above
    // its long side runs along the table: the scan's top edge ends up on my right, its left edge (the name) away from me
    m.updateMatrixWorld(true);
    const top = new THREE.Vector3(0, 0.5, 0).applyMatrix4(m.matrixWorld).sub(new THREE.Vector3().setFromMatrixPosition(m.matrixWorld));
    const left = new THREE.Vector3(-0.5, 0, 0).applyMatrix4(m.matrixWorld).sub(new THREE.Vector3().setFromMatrixPosition(m.matrixWorld));
    expect(top.x).toBeCloseTo((CARD_H * 1.8) / 2);
    expect(left.z).toBeCloseTo(-(CARD_W * 1.8) / 2);
    expect(t.active).toBe(false);
  });

  it("doesn't turn a landscape scan, and lies a text card upright when there's no picture", async () => {
    scan.w = 680;
    scan.h = 488;
    const t = new PlanarTable();
    t.sync(pc(), spot, 0, 0);
    await loaded();
    expect(card(t).rotation.z).toBeCloseTo(0);
    expect(card(t).scale.x).toBeCloseTo(CARD_H * 1.8);
    scan.fail = true;
    const off = new PlanarTable();
    off.sync(pc(), spot, 0, 0);
    await loaded();
    expect(card(off).material.map?.name).toBe("text");
    expect(card(off).rotation.z).toBeCloseTo(0);
    expect(card(off).scale.y).toBeGreaterThan(card(off).scale.x); // (portrait: it reads upright)
  });

  it("plays a planeswalk (the old plane off, the new one turning over) and a chaos pulse, finished at once by a click", async () => {
    const t = new PlanarTable();
    t.sync(pc(), spot, 0, 0);
    await loaded();
    t.sync(pc({ current: { printing_id: "b", name: "Llanowar", phenomenon: false }, walks: 1, last_roll: { player: "p1", face: "planeswalker", cost: 0, seq: 3 } }), spot, 0, 1000);
    await loaded();
    expect(t.active).toBe(true);
    expect(planes(t)).toBe(2); // the old one still sliding away
    t.update(1100);
    const [old, now] = t.group.children as THREE.Group[];
    expect(old!.position.x).toBeLessThan(0);
    expect(now!.rotation.x).toBeGreaterThan(0); // (still turning over)
    t.finish();
    t.update(1101);
    expect(t.active).toBe(false);
    expect(planes(t)).toBe(1);
    expect(now!.rotation.x).toBe(0);
    expect(card(t).material.opacity).toBe(1);
    t.sync(pc({ current: { printing_id: "b", name: "Llanowar", phenomenon: false }, walks: 1, last_roll: { player: "p1", face: "chaos", cost: 1, seq: 5 } }), spot, 0, 2000);
    expect(t.active).toBe(true);
    t.update(2000 + 350);
    expect(card(t).material.emissiveIntensity).toBeGreaterThan(0.3);
    t.finish();
    t.update(2351);
    expect(t.active).toBe(false);
    expect(card(t).material.emissiveIntensity).toBe(0);
  });

  it("is gone when the table puts the planar deck away (nothing on first sight animates)", async () => {
    const t = new PlanarTable();
    t.sync(pc({ walks: 4, last_roll: { player: "p1", face: "chaos", cost: 0, seq: 9 } }), spot, 0, 0);
    expect(t.active).toBe(false);
    await loaded();
    t.sync(null, spot, 0, 10);
    expect(t.group.visible).toBe(false);
    expect(t.targets()).toEqual([]);
    expect(planes(t)).toBe(0);
  });

  it("lays a second face-up plane beside the first (901.11c), both clickable, and takes it away when the table planeswalks", async () => {
    const t = new PlanarTable();
    const two = pc({ faces: [{ printing_id: "a", name: "Academy at Tolaria West", phenomenon: false },
      { printing_id: "b", name: "Llanowar", phenomenon: false }] });
    t.sync(two, spot, 0, 0);
    await loaded();
    expect(planes(t)).toBe(2);
    const [first, second] = t.targets();
    expect(second).toBeDefined();
    expect(second!.parent!.position.x - first!.parent!.position.x).toBeCloseTo(CARD_H * 1.8 * 1.08);
    t.sync(pc({ current: { printing_id: "c", name: "Krosa", phenomenon: false }, walks: 1 }), spot, 0, 1);
    t.finish();
    t.update(10_000);
    await loaded();
    expect(t.targets()).toHaveLength(1);
  });
});
