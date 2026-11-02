/**
 * 3D dice and coins (game/dice.ts feeds them). Each roll is thrown for real: table3d/physics.ts (cannon-es)
 * simulates the dice from the roller's edge of the table, across their mat and into the aisle, bouncing off the
 * table, its edges and the decks, knocking together and rolling to rest. The simulation is seeded by the roll, so every screen sees the same throw. The number
 * the server rolled is then printed on whichever face came to rest on top (on a d4, at the top point), and
 * floats above the die as well, readable from every seat, until the dice fade.
 */
import * as THREE from "three";
import { DICE_HOLD_MS, DICE_SHOWN, keptRolls, rollSummary, type DiceShow } from "../game/dice";
import { FRAMES_PER_SECOND, poseAt, seeded, simulate, trackSeconds, type BodyInit, type Obstacle, type Track } from "./physics";

const SIZE = 0.56;
const FADE_MS = 600;
const INK = "#1c1610";

/** A ten-sided die: kites around two apexes (a pentagonal trapezohedron, kites kept planar). */
function trapezohedron(r: number): THREE.BufferGeometry {
  const z0 = r * 0.105;
  const c36 = Math.cos(Math.PI / 5);
  const h = (z0 * (1 + c36)) / (1 - c36); // the apex height that keeps every kite flat
  const ring = (k: number, up: boolean) => {
    const a = ((k + (up ? 0 : 0.5)) / 5) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(a) * r, up ? z0 : -z0, Math.sin(a) * r);
  };
  const top = new THREE.Vector3(0, h, 0);
  const bottom = new THREE.Vector3(0, -h, 0);
  const tris: THREE.Vector3[] = [];
  const tri = (p: THREE.Vector3, q: THREE.Vector3, r: THREE.Vector3) => {
    // wound counter-clockwise seen from outside, so no face is culled
    const n = q.clone().sub(p).cross(r.clone().sub(p));
    if (n.dot(p.clone().add(q).add(r)) < 0) tris.push(p, r, q);
    else tris.push(p, q, r);
  };
  for (let k = 0; k < 5; k++) {
    const u0 = ring(k, true), u1 = ring(k + 1, true), l0 = ring(k, false), lPrev = ring(k - 1, false);
    tri(top, u0, l0); tri(top, l0, u1); // upper kite: apex, u(k), l(k), u(k+1)
    tri(bottom, lPrev, u0); tri(bottom, u0, l0); // lower kite: apex, l(k-1), u(k), l(k)
  }
  const g = new THREE.BufferGeometry().setFromPoints(tris);
  g.computeVertexNormals();
  return g;
}

interface Face { normal: THREE.Vector3; center: THREE.Vector3; corners: { vertex: number; a: number; b: number }[] }
interface Shape { geometry: THREE.BufferGeometry; faces: Face[]; polygons: number[][]; hull: THREE.Vector3[]; radius: number; cols: number; rows: number }
const shapes = new Map<string, Shape>();

/** The die's mesh, with its faces found (coplanar triangles), each mapped to its own cell of a number atlas. */
function shapeFor(sides: number): Shape {
  const key = String(sides);
  const known = shapes.get(key);
  if (known) return known;
  let g: THREE.BufferGeometry;
  if (sides === 4) g = new THREE.TetrahedronGeometry(SIZE * 0.8);
  else if (sides === 6) g = new THREE.BoxGeometry(SIZE, SIZE, SIZE).toNonIndexed();
  else if (sides === 8) g = new THREE.OctahedronGeometry(SIZE * 0.66);
  else if (sides === 10 || sides === 100) g = trapezohedron(SIZE * 0.62);
  else if (sides === 12) g = new THREE.DodecahedronGeometry(SIZE * 0.62);
  else g = new THREE.IcosahedronGeometry(SIZE * 0.66); // d20, and any other die
  g.deleteAttribute("uv");
  const pos = g.getAttribute("position") as THREE.BufferAttribute;
  // unique hull points (the physics only needs these)
  const hull: THREE.Vector3[] = [];
  const indexOf = (p: THREE.Vector3) => {
    const i = hull.findIndex((h) => h.distanceToSquared(p) < 1e-8);
    if (i >= 0) return i;
    hull.push(p.clone());
    return hull.length - 1;
  };
  // group triangles into faces by their outward normal
  const faces: (Face & { tris: number[] })[] = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let t = 0; t < pos.count / 3; t++) {
    a.fromBufferAttribute(pos, t * 3); b.fromBufferAttribute(pos, t * 3 + 1); c.fromBufferAttribute(pos, t * 3 + 2);
    const n = b.clone().sub(a).cross(c.clone().sub(a)).normalize();
    if (n.dot(a.clone().add(b).add(c)) < 0) n.negate();
    let f = faces.find((x) => x.normal.dot(n) > 0.999);
    if (!f) faces.push((f = { normal: n, center: new THREE.Vector3(), corners: [], tris: [] }));
    f.tris.push(t);
    for (const p of [a, b, c]) {
      const v = indexOf(p);
      if (!f.corners.some((x) => x.vertex === v)) f.corners.push({ vertex: v, a: 0, b: 0 });
    }
  }
  const cols = Math.ceil(Math.sqrt(faces.length));
  const rows = Math.ceil(faces.length / cols);
  const uv = new Float32Array(pos.count * 2);
  faces.forEach((f, fi) => {
    for (const k of f.corners) f.center.add(hull[k.vertex]!);
    f.center.divideScalar(f.corners.length);
    const u = new THREE.Vector3().crossVectors(f.normal, Math.abs(f.normal.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0)).normalize();
    const v = new THREE.Vector3().crossVectors(f.normal, u);
    const reach = Math.max(...f.corners.map((k) => hull[k.vertex]!.distanceTo(f.center))) * 2;
    const local = (p: THREE.Vector3) => [p.clone().sub(f.center).dot(u) / reach, p.clone().sub(f.center).dot(v) / reach] as const;
    for (const k of f.corners) [k.a, k.b] = local(hull[k.vertex]!);
    const col = fi % cols, row = Math.floor(fi / cols);
    for (const t of f.tris) {
      for (let j = 0; j < 3; j++) {
        const [la, lb] = local(a.fromBufferAttribute(pos, t * 3 + j));
        uv[(t * 3 + j) * 2] = (col + 0.5 + la * 0.96) / cols;
        uv[(t * 3 + j) * 2 + 1] = 1 - (row + 0.5 - lb * 0.96) / rows;
      }
    }
  });
  g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  const radius = Math.max(...hull.map((p) => p.length()));
  // the physics wants each face as its corners in order, counter-clockwise seen from outside: (u, v, normal) is
  // right-handed (u × v = normal), so sorting the corners by angle in (u, v) does it
  const polygons = faces.map((f) => [...f.corners].sort((p, q) => Math.atan2(p.b, p.a) - Math.atan2(q.b, q.a)).map((k) => k.vertex));
  const shape: Shape = { geometry: g, faces, polygons, hull, radius, cols, rows };
  shapes.set(key, shape);
  return shape;
}

/** For tests: a die's faces and hull. */
export const dieShape = (sides: number) => { const s = shapeFor(sides); return { faces: s.faces.length, polygons: s.polygons, hull: s.hull, radius: s.radius, normals: s.faces.map((f) => f.normal) }; };

/** The numbers on a die's faces (cells), with `top` showing the roll. A d4 numbers its points instead. */
function atlas(shape: Shape, sides: number, labels: string[], color: string, cornerLabels?: string[]): THREE.CanvasTexture {
  const cell = 160;
  const c = document.createElement("canvas");
  c.width = shape.cols * cell;
  c.height = shape.rows * cell;
  const g = c.getContext("2d")!;
  g.fillStyle = `#${new THREE.Color(color).lerp(new THREE.Color(0xf4ead6), 0.28).getHexString()}`;
  g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = INK;
  g.textAlign = "center";
  g.textBaseline = "middle";
  const small = sides === 20 || sides === 8 || sides === 4 || sides === 10 || sides === 100;
  shape.faces.forEach((f, fi) => {
    const cx = (fi % shape.cols + 0.5) * cell, cy = (Math.floor(fi / shape.cols) + 0.5) * cell;
    const at = (a: number, b: number) => [cx + a * 0.96 * cell, cy - b * 0.96 * cell] as const;
    const draw = (text: string, x: number, y: number, angle: number, px: number) => {
      g.save();
      g.translate(x, y);
      g.rotate(angle);
      g.font = `700 ${px}px Cinzel, Georgia, serif`;
      g.fillText(text, 0, 0);
      if (text === "6" || text === "9") g.fillRect(-px * 0.28, px * 0.42, px * 0.56, px * 0.08); // 6 and 9 underlined
      g.restore();
    };
    if (cornerLabels) {
      // d4: each point's number near that point on all three of its faces, its top toward the point
      for (const k of f.corners) {
        const [x, y] = at(k.a * 0.62, k.b * 0.62);
        draw(cornerLabels[k.vertex]!, x, y, Math.atan2(x - cx, cy - y), cell * 0.2);
      }
    } else {
      const text = labels[fi] ?? "";
      draw(text, cx, cy, 0, cell * (text.length > 2 ? 0.2 : small ? 0.3 : 0.42));
    }
  });
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

function labelTexture(text: string, color: string, wide = false): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = wide ? 320 : 128;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(20, 17, 14, 0.92)";
  g.strokeStyle = color;
  g.lineWidth = 7;
  g.beginPath();
  if (wide) g.roundRect(6, 14, c.width - 12, 100, 18);
  else g.arc(64, 64, 54, 0, Math.PI * 2);
  g.fill();
  g.stroke();
  g.fillStyle = "#f4ead6";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `700 ${wide ? 54 : text.length > 3 ? 34 : text.length > 2 ? 44 : 62}px Cinzel, Georgia, serif`;
  g.fillText(text, c.width / 2, 68);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

let shadowTex: THREE.Texture | null = null;
function blobShadow(): THREE.Texture {
  if (shadowTex) return shadowTex;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0, "rgba(0,0,0,0.55)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return (shadowTex = new THREE.CanvasTexture(c));
}

interface Die { mesh: THREE.Mesh; shadow: THREE.Mesh; label: THREE.Sprite; track: Track; ends: number }
interface Throw { started: number; dice: Die[]; total: THREE.Sprite | null; solids: THREE.Material[]; fades: THREE.Material[]; textures: THREE.Texture[]; geometries: THREE.BufferGeometry[]; last: number }

/** Where a throw starts and aims (world), and the table-top it stays on. TableScene works these out from the seat. */
export interface ThrowPath { from: THREE.Vector3; land: (i: number, n: number) => THREE.Vector3; bounds: { minX: number; maxX: number; minZ: number; maxZ: number }; obstacles?: Obstacle[] }

const COIN_R = 0.3;
const COIN_H = 0.05;
const coinHull = (() => {
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * COIN_R, COIN_H / 2, Math.sin(a) * COIN_R), new THREE.Vector3(Math.cos(a) * COIN_R, -COIN_H / 2, Math.sin(a) * COIN_R));
  }
  return pts;
})();

export class DiceTray {
  readonly group = new THREE.Group();
  private throws: Throw[] = [];

  throw(show: DiceShow, color: string, path: ThrowPath, now: number): void {
    const results = show.results.slice(0, DICE_SHOWN);
    const rnd = seeded(show.key);
    const shape = show.coin ? null : shapeFor(show.sides);
    // the throw: from the roller's hand toward the aisle, spinning hard
    // dice leave the hand side by side, never overlapping (overlapping solids would burst apart)
    const radius = show.coin ? COIN_R : shape!.radius;
    const aim = path.land(0, 1).sub(path.from).setY(0).normalize();
    const across = new THREE.Vector3(-aim.z, 0, aim.x);
    const perRow = 4;
    const bodies: BodyInit[] = results.map((_, i) => {
      const target = path.land(i, results.length);
      const row = Math.floor(i / perRow);
      const inRow = Math.min(perRow, results.length - row * perRow);
      const pos = path.from.clone()
        .addScaledVector(across, ((i % perRow) - (inRow - 1) / 2) * (radius * 2 + 0.15))
        .addScaledVector(aim, -row * (radius * 2 + 0.15) + (rnd() - 0.5) * 0.1)
        .setY(1.0 + rnd() * 0.4);
      const flat = target.clone().sub(pos).setY(0);
      const vel = flat.multiplyScalar(0.95 + rnd() * 0.15).setY(1.5 + rnd() * 1.5);
      const spin = new THREE.Vector3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize().multiplyScalar(show.coin ? 26 : 14 + rnd() * 10);
      const rot = new THREE.Quaternion().setFromEuler(new THREE.Euler(rnd() * 6.3, rnd() * 6.3, rnd() * 6.3));
      return show.coin
        ? { verts: coinHull, cylinder: { radius: COIN_R, height: COIN_H }, radius: COIN_R, pos, vel, spin, rot }
        : { verts: shape!.hull, faces: shape!.polygons, radius: shape!.radius, pos, vel, spin, rot };
    });
    const tracks = simulate(bodies, { bounds: path.bounds, obstacles: path.obstacles });
    const t: Throw = { started: now, dice: [], total: null, solids: [], fades: [], textures: [], geometries: [], last: 0 };
    const end = new THREE.Vector3();
    const endQ = new THREE.Quaternion();
    results.forEach((value, i) => {
      const track = tracks[i]!;
      poseAt(track, track.count - 1, end, endQ);
      let mesh: THREE.Mesh;
      if (show.coin) {
        // the face that came up shows the server's call
        const up = new THREE.Vector3(0, 1, 0).applyQuaternion(endQ).y > 0;
        const capUp = labelCap(value ? "H" : "T"), capDown = labelCap(value ? "T" : "H");
        const side = new THREE.MeshStandardMaterial({ color: 0x8a6a3f, metalness: 0.8, roughness: 0.4, transparent: true });
        const top = new THREE.MeshStandardMaterial({ map: up ? capUp : capDown, metalness: 0.6, roughness: 0.4, transparent: true });
        const bottom = new THREE.MeshStandardMaterial({ map: up ? capDown : capUp, metalness: 0.6, roughness: 0.4, transparent: true });
        const geo = new THREE.CylinderGeometry(COIN_R, COIN_R, COIN_H, 32);
        mesh = new THREE.Mesh(geo, [side, top, bottom]);
        t.fades.push(side, top, bottom);
        t.solids.push(side, top, bottom);
        t.textures.push(capUp, capDown);
        t.geometries.push(geo);
      } else {
        const s = shape!;
        // which face (or, on a d4, which point) ended up on top
        const heights = s.faces.map((f) => f.normal.clone().applyQuaternion(endQ).y);
        const topFace = heights.indexOf(Math.max(...heights));
        let map: THREE.CanvasTexture;
        if (show.sides === 4) {
          const ys = s.hull.map((p) => p.clone().applyQuaternion(endQ).y);
          const topPoint = ys.indexOf(Math.max(...ys));
          const others = [1, 2, 3, 4].filter((n) => n !== value);
          const corner = s.hull.map((_, k) => String(k === topPoint ? value : others.shift() ?? value));
          map = atlas(s, 4, [], color, corner);
        } else {
          const pool = Array.from({ length: Math.max(show.sides, s.faces.length) }, (_, k) => (k % show.sides) + 1).filter((n) => n !== value);
          const labels = s.faces.map((_, fi) => String(fi === topFace ? value : pool.splice(Math.floor(rnd() * pool.length), 1)[0] ?? value));
          map = atlas(s, show.sides, labels, color);
        }
        const mat = new THREE.MeshStandardMaterial({ map, roughness: 0.4, metalness: 0.04, flatShading: true, transparent: true });
        mesh = new THREE.Mesh(s.geometry, mat);
        t.fades.push(mat);
        t.solids.push(mat);
        t.textures.push(map);
      }
      const shadowMat = new THREE.MeshBasicMaterial({ map: blobShadow(), transparent: true, depthWrite: false, opacity: 0 });
      const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), shadowMat);
      t.geometries.push(shadow.geometry);
      t.fades.push(shadowMat);
      const text = show.coin ? (value ? "H" : "T") : String(value);
      const lmap = labelTexture(text, color);
      const lmat = new THREE.SpriteMaterial({ map: lmap, transparent: true, depthTest: false, opacity: 0 });
      const label = new THREE.Sprite(lmat);
      label.scale.setScalar(0.5);
      label.renderOrder = 10;
      label.position.copy(end).setY(0.95);
      t.fades.push(lmat);
      t.textures.push(lmap);
      poseAt(track, 0, mesh.position, mesh.quaternion);
      this.group.add(shadow, mesh, label);
      const ends = trackSeconds(track) * 1000;
      t.last = Math.max(t.last, ends);
      t.dice.push({ mesh, shadow, label, track, ends });
    });
    if (show.results.length > 1) {
      const map = labelTexture(show.coin ? rollSummary(show) : `= ${keptRolls(show).reduce((a, b) => a + b, 0)}`, color, true);
      const mat = new THREE.SpriteMaterial({ map, transparent: true, depthTest: false, opacity: 0 });
      const total = new THREE.Sprite(mat);
      total.scale.set(1.25, 0.5, 1);
      total.renderOrder = 11;
      const mid = t.dice.reduce((v, d) => v.add(d.label.position), new THREE.Vector3()).divideScalar(t.dice.length);
      total.position.copy(mid).setY(2.0);
      this.group.add(total);
      t.total = total;
      t.fades.push(mat);
      t.textures.push(map);
    }
    this.throws.push(t);
  }

  update(now: number, reduced: boolean, speed: number): void {
    const rate = Math.max(0.25, speed);
    for (const t of [...this.throws]) {
      const age = (now - t.started) * rate; // ms of simulated time played
      const done = reduced ? 0 : t.last;
      const fade = age > done + DICE_HOLD_MS * rate ? 1 - Math.min(1, (age - done - DICE_HOLD_MS * rate) / FADE_MS) : 1;
      for (const d of t.dice) {
        const frame = reduced ? d.track.count - 1 : Math.floor((age / 1000) * FRAMES_PER_SECOND);
        poseAt(d.track, frame, d.mesh.position, d.mesh.quaternion);
        const lift = Math.max(0, d.mesh.position.y);
        d.shadow.position.set(d.mesh.position.x + 0.04, 0.004, d.mesh.position.z + 0.06);
        d.shadow.scale.setScalar(0.75 + lift * 0.5);
        (d.shadow.material as THREE.MeshBasicMaterial).opacity = fade / (1 + lift * 1.5);
        const shown = reduced ? 1 : Math.max(0, Math.min(1, (age - d.ends) / 250));
        (d.label.material as THREE.SpriteMaterial).opacity = shown * fade;
      }
      if (t.total) (t.total.material as THREE.SpriteMaterial).opacity = (reduced ? 1 : Math.max(0, Math.min(1, (age - t.last) / 300))) * fade;
      for (const m of t.solids) m.opacity = fade;
      if (fade <= 0) this.remove(t);
    }
  }

  private remove(t: Throw): void {
    for (const d of t.dice) this.group.remove(d.mesh, d.shadow, d.label);
    if (t.total) this.group.remove(t.total);
    for (const m of t.fades) m.dispose();
    for (const x of t.textures) x.dispose();
    for (const g of t.geometries) g.dispose();
    this.throws = this.throws.filter((x) => x !== t);
  }

  /** Where the dice on the table are now (tests and diagnostics). */
  positions(): THREE.Vector3[] {
    return this.throws.flatMap((t) => t.dice.map((d) => d.mesh.position.clone()));
  }

  dispose(): void {
    for (const t of [...this.throws]) this.remove(t);
  }
}

/** A coin face: brass with the letter struck in. */
function labelCap(letter: string): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(46, 40, 6, 64, 64, 64);
  grad.addColorStop(0, "#f1d58e");
  grad.addColorStop(0.6, "#b39458");
  grad.addColorStop(1, "#6e5630");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  g.fillStyle = "#3a2c14";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = "700 64px Cinzel, Georgia, serif";
  g.fillText(letter, 64, 70);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
