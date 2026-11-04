/**
 * The world around the table for a plane: its lighting, the table itself, the props standing on it, and (graphics
 * medium and high) a lived-in set around it: the plane's room or ground (env/sets.ts), its floor and the piece under
 * the table, fire and candle flames, window light falling in shafts, and drifting particles. The play area stays clear;
 * props sit at the table's prop spots, and the room is dimmer and quieter than the lit table so the cards read first.
 * Low graphics keep the minimal room (the table and its props over a dark floor).
 */
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { PlaneTheme } from "../theme/planes";
import { rng, surfaceMaps } from "./textures";
import type { TableSize } from "./layout";
import { atlasMaps } from "./env/atlas";
import { Batch } from "./env/batch";
import { buildBeams } from "./env/beams";
import { Flames } from "./env/flames";
import { flicker } from "./env/flicker";
import { centreMaps, floorMaps } from "./env/floors";
import { Put, type SetCtx } from "./env/kit";
import { buildParticles } from "./env/particles";
import { buildTableProp } from "./env/props";
import { decorate, RoomLight } from "./env/roomShader";
import { roomFor, SETS } from "./env/sets";

export interface Environment {
  group: THREE.Group;
  update(time: number): void;
  dispose(): void;
  /** Top of the table (cards lie just above this). */
  tableY: number;
}

const TABLE_THICK = 0.7;

function roundedShape(w: number, d: number, r: number): THREE.Shape {
  const s = new THREE.Shape();
  const x = -w / 2;
  const y = -d / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + d - r);
  s.quadraticCurveTo(x + w, y + d, x + w - r, y + d);
  s.lineTo(x + r, y + d);
  s.quadraticCurveTo(x, y + d, x, y + d - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/** A flat ring between two rounded rectangles, extruded upward from y = 0. */
function roundedRing(w: number, d: number, r: number, inset: number, depth: number, bevel: number): THREE.ExtrudeGeometry {
  const outer = roundedShape(w, d, r);
  outer.holes.push(roundedShape(w - inset * 2, d - inset * 2, Math.max(0.05, r - inset)));
  const geo = new THREE.ExtrudeGeometry(outer, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 4, curveSegments: 14 });
  geo.rotateX(-Math.PI / 2);
  return geo;
}

function roundedSlab(w: number, d: number, r: number, depth: number): THREE.ExtrudeGeometry {
  const s = roundedShape(w, d, r);
  const geo = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: true, bevelThickness: 0.12, bevelSize: 0.12, bevelSegments: 3, curveSegments: 10 });
  geo.rotateX(-Math.PI / 2);
  return geo;
}

interface Flicker { light: THREE.PointLight; base: number; phase: number; amount: number }

/** The table's base: four turned legs, each with a square block under the apron, and the apron boards between them. */
function tableBase(size: TableSize, top: number, floorY: number): THREE.BufferGeometry {
  const hw = size.w / 2, hd = size.d / 2;
  const parts: THREE.BufferGeometry[] = [];
  const h = top - floorY;
  const lx = hw - 2.5, lz = hd - 2.5;
  const profile: [number, number][] = [[0, 0], [0.75, 0], [0.8, 0.25], [0.62, 0.55], [0.5, 0.9], [0.62, 1.4], [0.42, 2.1], [0.36, h * 0.45], [0.5, h * 0.55], [0.38, h * 0.62], [0.44, h - 2.35], [0.56, h - 2.2], [0.56, h - 2.05], [0, h - 2.05]];
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
    const leg = new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), 14);
    leg.translate(sx * lx, floorY, sz * lz);
    parts.push(leg.toNonIndexed());
    const block = new THREE.BoxGeometry(1.2, 2.1, 1.2).toNonIndexed();
    block.translate(sx * lx, top - 1.05, sz * lz);
    parts.push(block);
  }
  for (const [w, d, x, z] of [[lx * 2, 0.3, 0, -lz], [lx * 2, 0.3, 0, lz], [0.3, lz * 2, -lx, 0], [0.3, lz * 2, lx, 0]] as const) {
    const apron = new THREE.BoxGeometry(w, 1.6, d).toNonIndexed();
    apron.translate(x, top - 0.8, z);
    parts.push(apron);
  }
  for (const g of parts) for (const name of Object.keys(g.attributes)) if (name !== "position" && name !== "normal") g.deleteAttribute(name);
  const merged = mergeGeometries(parts, false)!;
  for (const g of parts) g.dispose();
  return merged;
}

/**
 * `spots`: where the table's props may stand (table3d/framing.ts propSpots: the two ends of the aisle, which the seat
 * view frames whole, props and all), left then right; without them, the table's far corners.
 */
export function buildEnvironment(p: PlaneTheme, size: TableSize, quality: "low" | "medium" | "high", spots?: [number, number][]): Environment {
  const e = p.env;
  const group = new THREE.Group();
  const disposables: { dispose(): void }[] = [];
  const track = <T extends { dispose(): void }>(x: T): T => (disposables.push(x), x);
  const rand = rng(p.id.length * 7919);
  const tableY = 0;
  const floorY = -9;
  const halfW = size.w / 2;
  const halfD = size.d / 2;

  // ---- lights
  // fill stays low: the key light, the pool and the environment reflections give the shape
  const hemi = new THREE.HemisphereLight(e.ambient, e.surfaceGrain, e.ambientIntensity * 1.8);
  group.add(hemi);
  const key = new THREE.DirectionalLight(e.key, e.keyIntensity * 2.2);
  key.position.set(-7, 28, 12);
  key.target.position.set(0, 0, 0);
  if (quality !== "low") {
    key.castShadow = true;
    key.shadow.mapSize.set(quality === "high" ? 2048 : 1024, quality === "high" ? 2048 : 1024);
    // the shadow camera covers the table top only, so cards get crisp contact shadows
    const r = Math.max(halfW, halfD) + 0.5;
    Object.assign(key.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 10, far: 60 });
    key.shadow.bias = -0.0002;
    key.shadow.normalBias = 0.01;
  }
  group.add(key, key.target);
  // a warm pool of light over the play area, in the plane's glow colour
  const pool = new THREE.PointLight(e.glow, 75 * e.glowIntensity, Math.max(halfW, halfD) * 2.2, 1.6);
  pool.position.set(0, 14, 2);
  group.add(pool);
  const rim = new THREE.DirectionalLight(e.rim, e.rimIntensity * 1.5);
  rim.position.set(10, 12, -26);
  group.add(rim);

  // ---- the table
  // satin, not gloss: the table must recede behind the cards
  const roughness = e.surface === "marble" || e.surface === "lacquer" ? 0.45 : e.surface === "oilmetal" ? 0.38 : 0.86;
  const surf = surfaceMaps(e.surface, e.surfaceBase, e.surfaceGrain, roughness, p.id.charCodeAt(0));
  for (const t of [surf.map, surf.normalMap, surf.roughnessMap]) {
    track(t);
    t.wrapS = t.wrapT = THREE.MirroredRepeatWrapping;
    t.repeat.set(1 / 18, 1 / 18);
  }
  const topMat = track(new THREE.MeshStandardMaterial({
    map: surf.map,
    normalMap: surf.normalMap,
    normalScale: new THREE.Vector2(0.35, 0.35),
    roughnessMap: surf.roughnessMap,
    roughness: 1,
    envMapIntensity: 0.45,
    metalness: e.surface === "oilmetal" ? 0.6 : 0.02,
  }));
  const railMat = track(new THREE.MeshStandardMaterial({ color: e.rail, roughness: 0.6, metalness: e.surface === "oilmetal" ? 0.7 : 0.1 }));
  const slab = new THREE.Mesh(track(roundedSlab(size.w, size.d, 1.6, TABLE_THICK)), [topMat, railMat]);
  slab.position.y = tableY - TABLE_THICK - 0.12;
  slab.receiveShadow = true;
  group.add(slab);
  // a padded leather rail around the edge, like a card-room table, outside every zone
  const leather = track(new THREE.MeshStandardMaterial({ color: new THREE.Color(e.rail).lerp(new THREE.Color("#3b2416"), 0.35), roughness: 0.48, metalness: 0, envMapIntensity: 0.9 }));
  const rail = new THREE.Mesh(track(roundedRing(size.w + 0.1, size.d + 0.1, 1.65, 0.62, 0.16, 0.09)), leather);
  rail.position.y = tableY + 0.09;
  rail.castShadow = rail.receiveShadow = quality !== "low";
  group.add(rail);
  // a brass inlay strip just inside the rail
  const brass = track(new THREE.MeshStandardMaterial({ color: e.inlay, roughness: 0.32, metalness: 1, envMapIntensity: 1.2 }));
  const inlay = new THREE.Mesh(track(roundedRing(size.w - 1.35, size.d - 1.35, 1.0, 0.06, 0.006, 0)), brass);
  inlay.position.y = tableY + 0.001;
  inlay.receiveShadow = quality !== "low";
  group.add(inlay);
  // ---- the table's base: turned legs and an apron under the slab's edge (one mesh)
  const base = tableBase(size, tableY - TABLE_THICK - 0.24, floorY);
  const legs = new THREE.Mesh(base, railMat);
  legs.castShadow = quality === "high";
  group.add(legs);

  // ---- the room's light, the table's props, the set
  const room = new RoomLight(new THREE.Color(e.fog).multiplyScalar(0.22), e.flicker);
  room.cut.value.set(Math.max(halfW, halfD) + 0.5, 3, 1.5);
  const spec = SETS[p.id] ?? SETS.dominaria;
  const flames = new Flames(quality === "low" ? 16 : 96, room.uniforms.uTime, room.cut);
  group.add(flames.mesh);
  const propBatch = new Batch();
  const ctxProps: SetCtx = { set: propBatch, glow: propBatch, flames, room, rand, floorY: tableY, rich: quality === "high" };
  const flickers: Flicker[] = [];
  const corners: [number, number][] = spots && spots.length >= 2 ? spots.slice(0, 2) : [[-halfW + 0.9, -halfD + 0.9], [halfW - 0.9, -halfD + 0.9]];
  spec.props.forEach((kind, i) => {
    const [cx, cz] = corners[i]!;
    for (const l of buildTableProp(ctxProps, new Put(ctxProps).at(cx, tableY, cz), kind, e.glow)) {
      if (quality === "low" && flickers.length >= 2) continue;
      const light = new THREE.PointLight(l.color, l.intensity * e.glowIntensity, l.distance, 2);
      light.position.copy(l.pos);
      group.add(light);
      flickers.push({ light, base: light.intensity, phase: rand() * 10, amount: e.flicker });
      room.add(l.pos, l.color, 0.5 * e.glowIntensity, 9, "candle", rand() * 10);
    }
  });
  // soft contact shadows under the props (one mesh): each sits on the table, not over it
  {
    const soft = document.createElement("canvas");
    soft.width = soft.height = 64;
    const sg = soft.getContext("2d")!;
    const grad = sg.createRadialGradient(32, 32, 2, 32, 32, 32);
    grad.addColorStop(0, "rgba(255,255,255,0.9)");
    grad.addColorStop(0.5, "rgba(255,255,255,0.45)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    sg.fillStyle = grad;
    sg.fillRect(0, 0, 64, 64);
    const quads = corners.slice(0, spec.props.length).map(([cx, cz]) => {
      const q = new THREE.PlaneGeometry(1.5, 1.9);
      q.rotateX(-Math.PI / 2);
      q.translate(cx + 0.08, tableY + 0.004, cz - 0.06);
      return q;
    });
    const geo = mergeGeometries(quads, false)!;
    for (const q of quads) q.dispose();
    const mat = new THREE.MeshBasicMaterial({ color: "#000", map: track(new THREE.CanvasTexture(soft)), transparent: true, opacity: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2 });
    const contact = new THREE.Mesh(geo, mat);
    contact.renderOrder = -1;
    group.add(contact);
  }
  const atlas = atlasMaps();
  track(atlas.map);
  track(atlas.normalMap);
  const propGeo = propBatch.build();
  if (propGeo) {
    const propMat = track(decorate(new THREE.MeshStandardMaterial({ map: atlas.map, normalMap: atlas.normalMap, normalScale: new THREE.Vector2(0.6, 0.6), vertexColors: true, roughness: 1, metalness: 1, envMapIntensity: 0.8 }), room, { key: "props", surf: true, practical: 0.6, fade: false }));
    const props = new THREE.Mesh(propGeo, propMat);
    props.castShadow = quality !== "low";
    props.receiveShadow = quality !== "low";
    group.add(props);
  }

  if (quality === "low") {
    // today's minimal room: a plain floor in the dark, the table on a soft shadow of its own
    const floor = new THREE.Mesh(track(new THREE.CircleGeometry(600, 48)), track(new THREE.MeshStandardMaterial({ color: new THREE.Color(e.surfaceGrain).multiplyScalar(0.35), roughness: 1 })));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = floorY;
    group.add(floor);
    const soft = document.createElement("canvas");
    soft.width = soft.height = 128;
    const pg = soft.getContext("2d")!;
    const grad = pg.createRadialGradient(64, 64, 8, 64, 64, 64);
    grad.addColorStop(0, "rgba(0,0,0,0.85)");
    grad.addColorStop(0.55, "rgba(0,0,0,0.55)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    pg.fillStyle = grad;
    pg.fillRect(0, 0, 128, 128);
    const under = new THREE.Mesh(track(new THREE.PlaneGeometry(size.w * 1.35 + 4, size.d * 1.35 + 4)),
      track(new THREE.MeshBasicMaterial({ map: track(new THREE.CanvasTexture(soft)), transparent: true, depthWrite: false, color: "#000" })));
    under.rotation.x = -Math.PI / 2;
    under.position.set(1.2, floorY + 0.02, -1.6);
    group.add(under);
  } else {
    // ---- the set: walls, furniture, fire, windows (one mesh), the floor and the piece under the table
    const r = roomFor(size, floorY);
    room.setFade(Math.max(halfW, halfD) + spec.fade[0], Math.max(halfW, halfD) + spec.fade[1], spec.fade[2]);
    const setBatch = new Batch();
    const ctx: SetCtx = { set: setBatch, glow: setBatch, flames, room, rand, floorY, rich: quality === "high" };
    spec.build(ctx, r);
    const setGeo = setBatch.build();
    if (setGeo) {
      const setMat = track(decorate(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 1, envMapIntensity: 0.5 }), room, { key: `set-${p.id}`, surf: true, macro: 0.1, macroScale: 3, practical: 1, direct: 0.3, indirect: 0.55, cutaway: true }));
      group.add(new THREE.Mesh(setGeo, setMat));
    }
    const shadow = { x: 1.0, z: -1.2, hw: halfW + 0.2, hd: halfD + 0.2, soft: 3.2, dark: 0.8 };
    const fm = floorMaps(spec.floor, spec.floorColors[0], spec.floorColors[1]);
    track(fm.map);
    track(fm.normalMap);
    for (const t of [fm.map, fm.normalMap]) t.repeat.set(240 / spec.floorTile, 240 / spec.floorTile);
    const floorMat = track(decorate(new THREE.MeshStandardMaterial({ map: fm.map, normalMap: fm.normalMap, normalScale: new THREE.Vector2(0.8, 0.8), roughness: e.surface === "marble" || e.surface === "oilmetal" ? 0.42 : 0.88, envMapIntensity: 0.3 }), room, { key: `floor-${p.id}`, macro: 0.16, macroScale: 7, practical: 0.9, direct: 0.32, indirect: 0.45, under: shadow }));
    const floor = new THREE.Mesh(track(new THREE.PlaneGeometry(240, 240)), floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = floorY;
    group.add(floor);
    if (spec.centre !== "none" && spec.centre !== "stones") {
      const cm = centreMaps(spec.centre, p.ui.accent);
      track(cm.map);
      track(cm.normalMap);
      const cw = size.w + spec.centreMargin[0] * 2, cd = size.d + spec.centreMargin[1] * 2;
      const centreMat = track(decorate(new THREE.MeshStandardMaterial({ map: cm.map, normalMap: cm.normalMap, alphaTest: 0.4, roughness: 0.95, envMapIntensity: 0.2 }), room, { key: `centre-${p.id}`, practical: 0.85, direct: 0.3, indirect: 0.5, under: shadow }));
      const centre = new THREE.Mesh(track(new THREE.PlaneGeometry(1, 1)), centreMat);
      centre.rotation.x = -Math.PI / 2;
      // the rug lies lengthwise along the table's long side
      const long = cw >= cd;
      centre.rotation.z = long ? 0 : Math.PI / 2;
      centre.scale.set(long ? cw : cd, long ? cd : cw, 1);
      centre.position.y = floorY + 0.03;
      group.add(centre);
    }
    const beams = buildBeams(room, floorY, quality === "high" ? 0.04 : 0.032, [halfW + 1, halfD + 1]);
    if (beams) group.add(beams);
    // ---- particles, on by default
    for (const ps of spec.particles) {
      const n = Math.round(ps.count * (quality === "high" ? 1 : 0.6));
      const box = ps.where === "room" ? { min: [r.left + 1, floorY, r.back + 1], max: [r.right - 1, floorY + 24, r.front - 1] }
        : ps.where === "air" ? { min: [r.left + 1, floorY + 4, r.back + 1], max: [r.right - 1, 22, r.front - 1] }
        : ps.where(r);
      const pts = buildParticles(room, { kind: ps.kind, color: ps.color, count: n, min: new THREE.Vector3(...box.min), max: new THREE.Vector3(...box.max), size: ps.size, opacity: ps.opacity, base: ps.base, beam: ps.beam, additive: ps.additive, seed: rand, keepOut: [halfW + 1.5, halfD + 1.5, 60] });
      if (pts) group.add(pts);
    }
  }
  room.update(0);

  group.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh || (o as THREE.Points).isPoints) {
      if (m.geometry) disposables.push(m.geometry);
      const mats = Array.isArray(m.material) ? m.material : [m.material];
      for (const mm of mats) if (mm) disposables.push(mm);
    }
  });

  return {
    group,
    tableY,
    update(time: number) {
      // the candles' lights on the table flutter with their flames; the room's practicals, flames, beams and
      // particles follow the room's clock (on the GPU)
      for (const f of flickers) f.light.intensity = f.base * flicker(time, f.phase, f.amount);
      room.update(time);
    },
    dispose() {
      const seen = new Set<unknown>();
      for (const d of disposables) {
        if (seen.has(d)) continue;
        seen.add(d);
        d.dispose();
      }
    },
  };
}
