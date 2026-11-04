import { describe, expect, it } from "vitest";
import * as THREE from "three";
import type { GameView } from "../types/game";
import { tableEvents } from "../game/motion/tableEvents";
import { MAT_D, onBattlefield, seats, toLocal } from "./layout";
import { TableMotion, type MotionCard, type MotionHost } from "./motion3d";

type Card = Record<string, unknown> & { id: string; zone: string; owner: string };
function table(cards: Card[], libraries: Record<string, number> = {}): GameView {
  const zones: Record<string, unknown> = {};
  const views: Record<string, unknown> = {};
  for (const c of cards) {
    views[c.id] = { controller: c.owner, face_down: false, ...c };
    if (!c.zone.endsWith(":library")) ((zones[c.zone] ??= []) as string[]).push(c.id);
  }
  for (const [key, count] of Object.entries(libraries)) zones[key] = { count, known: [] };
  return { zones, cards: views, players: [{ id: "p1", life: 40 }, { id: "p2", life: 40 }], turn: { number: 1, active_player: "p1", phase: "main1" }, stack: [] } as unknown as GameView;
}
const seen = (id: string, zone: string, owner = zone.split(":")[0]!, more: Record<string, unknown> = {}): Card => ({ id, zone, owner, name: id, ...more });
const hidden = (n: number, zone: string): Card[] => Array.from({ length: n }, (_, i) => ({ id: `hidden:${zone}:${i}`, zone, owner: zone.split(":")[0]!, hidden: true }));

/** A stand-in for TableScene: cards it shows, card backs and faces as named textures (a face only for a card the view shows face up). */
function fakeTable() {
  const world = new THREE.Group();
  const cards = new Map<string, MotionCard>();
  const tex = new Map<string, THREE.Texture>();
  const mat = (name: string) => {
    let t = tex.get(name);
    if (!t) tex.set(name, (t = new THREE.Texture()));
    t.name = name;
    return new THREE.MeshStandardMaterial({ map: t });
  };
  let view: GameView | null = null;
  const all = seats(["p1", "p2"], "p1");
  const host: MotionHost = {
    world, faceGeo: new THREE.PlaneGeometry(1, 1), thick: 0.016,
    me: () => "p1", view: () => view, card: (id) => cards.get(id),
    seat: (p) => all.find((s) => s.player === p), pileY: () => 0.2,
    back: (owner) => mat(`back:${owner}`),
    face: (id) => {
      const c = view?.cards[id];
      return c && !c.hidden && !c.face_down ? mat(`face:${id}`) : mat(`back:${c?.owner ?? ""}`);
    },
    heart: () => new THREE.Vector3(0, 0.2, 2),
  };
  /** The table lays out ``next``: shows these cards (new ones fresh, at the origin), drops (and remembers) the rest. */
  const layout = (motion: TableMotion, next: GameView, shown: Record<string, [number, number]>) => {
    view = next;
    motion.layout();
    for (const [id, c] of cards) if (!(id in shown)) {
      motion.forget(c);
      world.remove(c.group);
      cards.delete(id);
    }
    for (const [id, [x, z]] of Object.entries(shown)) {
      let c = cards.get(id);
      if (!c) {
        const face = new THREE.Mesh(host.faceGeo, host.face(id));
        const group = new THREE.Group();
        group.add(face);
        world.add(group);
        c = { id, group, face, overlay: null, target: new THREE.Vector3(), rot: 0, tilt: 0, scale: 1, fresh: true };
        cards.set(id, c);
      }
      c.target.set(x, 0.004, z);
    }
  };
  const mapName = (m: THREE.Material | THREE.Material[]) => ((m as THREE.MeshStandardMaterial).map?.name ?? "");
  return { host, world, cards, layout, mapName };
}

/** Stand-ins in the world (groups that aren't the table's cards). */
const standIns = (t: ReturnType<typeof fakeTable>) => t.world.children.filter((g) => ![...t.cards.values()].some((c) => c.group === g)) as THREE.Group[];

describe("3D table motion, played", () => {
  it("another player's cast leaves their hand as a card back, turns face up on the way and lands where it belongs", () => {
    const t = fakeTable();
    const motion = new TableMotion(t.host);
    const prev = table([...hidden(3, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand"), seen("ring", "stack", "p2")]);
    t.layout(motion, next, { ring: [0, 1.6] });
    motion.play(tableEvents(prev, next), next, prev);
    const ring = t.cards.get("ring")!;
    expect(ring.flying).toBe(true);
    expect(ring.fresh).toBe(false);
    expect(t.mapName(ring.face.material)).toBe("back:p2"); // a back while it's in the air from the hidden hand
    // 1v1: it rises out of Bob's fan of backs, which stands in sight past his own edge behind his heart and plate
    // (flights3d otherHandSpot), not out of his mat
    const bob = t.host.seat("p2")!;
    const [lx, lz] = toLocal(bob, ring.group.position.x, ring.group.position.z);
    expect(onBattlefield(lx, lz)).toBe(false);
    expect(lz).toBeGreaterThan(MAT_D / 2);
    expect(ring.group.position.z).toBeLessThan(-1.5); // Bob's side of the table, not the middle
    const t0 = performance.now();
    motion.update(t0 + 40, false);
    motion.update(t0 + 200, false);
    expect(t.mapName(ring.face.material)).toBe("face:ring"); // turned over
    motion.update(t0 + 2000, false);
    expect(ring.flying).toBe(false);
    expect(ring.group.position.distanceTo(ring.target)).toBeLessThan(1e-6);
    expect(motion.active).toBe(false); // nothing running when idle
  });

  it("another player's draw: card backs from the library to their hand, which go back to the pool when they land", () => {
    const t = fakeTable();
    const motion = new TableMotion(t.host);
    const prev = table([...hidden(7, "p2:hand")], { "p2:library": 30 });
    const next = table([...hidden(9, "p2:hand")], { "p2:library": 28 });
    t.layout(motion, next, {});
    motion.play(tableEvents(prev, next), next, prev);
    const flying = standIns(t);
    expect(flying).toHaveLength(2);
    for (const g of flying) expect(t.mapName((g.children[0] as THREE.Mesh).material)).toBe("back:p2");
    motion.update(performance.now() + 2000, false);
    expect(standIns(t)).toHaveLength(0);
    // the pool hands the same stand-ins out again
    motion.play(tableEvents(prev, next), next, prev);
    expect(standIns(t).every((g) => flying.includes(g))).toBe(true);
  });

  it("a mill's lower cards turn face up on the way (the graveyard is public); a bounce into a hidden hand turns face down", () => {
    const t = fakeTable();
    const motion = new TableMotion(t.host);
    const prev = table([seen("bear", "p2:battlefield"), ...hidden(1, "p2:hand")], { "p2:library": 30 });
    t.layout(motion, prev, { bear: [0, -4] });
    motion.update(performance.now(), false); // (the table placed the bear)
    t.cards.get("bear")!.fresh = false;
    const next = table([seen("a", "p2:graveyard"), seen("b", "p2:graveyard"), ...hidden(2, "p2:hand")], { "p2:library": 28 });
    t.layout(motion, next, { b: [6, -3] });
    motion.play(tableEvents(prev, next), next, prev);
    const looks = () => standIns(t).map((g) => t.mapName((g.children[0] as THREE.Mesh).material)).sort();
    expect(looks()).toEqual(["back:p2", "face:bear"]); // the mill's "a" leaves as a back; the bear as it was seen
    motion.update(performance.now() + 200, false);
    expect(looks()).toEqual(["back:p2", "face:a"]); // and they've turned over
    motion.update(performance.now() + 2000, false);
    expect(motion.active).toBe(false);
  });

  it("any click or key press lands every flight at once", () => {
    const t = fakeTable();
    const motion = new TableMotion(t.host);
    const prev = table([seen("bolt", "p1:hand")]);
    const next = table([seen("bolt", "stack", "p1")]);
    t.layout(motion, next, { bolt: [0, 1.6] });
    motion.play(tableEvents(prev, next), next, prev);
    expect(motion.active).toBe(true);
    motion.finish();
    motion.update(performance.now(), false);
    const bolt = t.cards.get("bolt")!;
    expect(bolt.flying).toBe(false);
    expect(bolt.group.position.distanceTo(bolt.target)).toBeLessThan(1e-6);
    expect(motion.active).toBe(false);
  });

  it("frozen for a screenshot, a flight holds its place until released", () => {
    const t = fakeTable();
    const motion = new TableMotion(t.host);
    const prev = table([seen("bolt", "p1:hand")]);
    const next = table([seen("bolt", "stack", "p1")]);
    t.layout(motion, next, { bolt: [0, 1.6] });
    motion.freeze(60);
    motion.play(tableEvents(prev, next), next, prev);
    motion.update(performance.now() + 5000, false);
    const at = t.cards.get("bolt")!.group.position.clone();
    motion.update(performance.now() + 9000, false);
    expect(t.cards.get("bolt")!.group.position.equals(at)).toBe(true);
    expect(t.cards.get("bolt")!.flying).toBe(true);
    motion.freeze(null);
    motion.update(performance.now() + 9000, false);
    expect(t.cards.get("bolt")!.flying).toBe(false);
  });
});
