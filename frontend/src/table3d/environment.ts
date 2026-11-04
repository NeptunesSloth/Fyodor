/**
 * The world around the table for a plane: sky, fog, lighting, the table itself, props at the
 * table's corners and in the distance, and a few drifting particles. The play area stays clear;
 * props sit outside the mats and the background is dim and fogged so cards read first.
 */
import * as THREE from "three";
import type { PlaneTheme, Prop, Particles } from "../theme/planes";
import { rng, surfaceMaps } from "./textures";
import type { TableSize } from "./layout";

export interface Environment {
  group: THREE.Group;
  update(time: number): void;
  dispose(): void;
  /** Top of the table (cards lie just above this). */
  tableY: number;
}

const TABLE_THICK = 0.7;

function skyDome(top: string, bottom: string): THREE.Mesh {
  const geo = new THREE.SphereGeometry(140, 32, 16);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: { top: { value: new THREE.Color(top) }, bottom: { value: new THREE.Color(bottom) } },
    vertexShader: "varying vec3 vPos; void main(){ vPos = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform vec3 top; uniform vec3 bottom; varying vec3 vPos; void main(){ float h = clamp(normalize(vPos).y * 1.4 + 0.35, 0.0, 1.0); gl_FragColor = vec4(mix(bottom, top, h) * 0.35, 1.0);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}",
  });
  return new THREE.Mesh(geo, mat);
}

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

function glowSprite(color: string, size: number, opacity = 0.9): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.25, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  const mat = new THREE.SpriteMaterial({ map: tex, color, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending });
  const s = new THREE.Sprite(mat);
  s.scale.setScalar(size);
  return s;
}

interface Flicker { light: THREE.PointLight; base: number; phase: number; amount: number; flame?: THREE.Object3D }
interface Spinner { obj: THREE.Object3D; speed: number; bob: number; phase: number; y: number }

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
  const flickers: Flicker[] = [];
  const spinners: Spinner[] = [];
  const tableY = 0;
  const floorY = -9;
  const halfW = size.w / 2;
  const halfD = size.d / 2;

  group.add(skyDome(e.skyTop, e.skyBottom));

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
  // legs and floor
  const legMat = railMat;
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
    const leg = new THREE.Mesh(track(new THREE.BoxGeometry(1.2, -floorY - 1, 1.2)), legMat);
    leg.position.set(sx * (halfW - 2.5), (floorY + tableY - 1) / 2, sz * (halfD - 2.5));
    group.add(leg);
  }
  const floor = new THREE.Mesh(track(new THREE.CircleGeometry(120, 48)), track(new THREE.MeshStandardMaterial({ color: new THREE.Color(e.surfaceGrain).multiplyScalar(0.35), roughness: 1 })));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = floorY;
  floor.receiveShadow = quality === "high";
  group.add(floor);

  // ---- props
  // the props stand in the table's very corners, past the piles and the mats: nothing decorative in the play space
  const inset = 0.6;
  const far: [number, number][] = [[-halfW + inset, -halfD + inset], [halfW - inset, -halfD + inset]];
  // (corners 0 and 1 hold the props; 2 and 3, by the viewer's hand, stay clear)
  const corners: [number, number][] = [...(spots && spots.length >= 2 ? spots.slice(0, 2) : far), [-halfW + inset, halfD - inset], [halfW - inset, halfD - inset]];
  // framed whole with the table, a prop stands no taller than framing's PROP_TOP
  const short = !!spots;
  const std = (color: string, extra: THREE.MeshStandardMaterialParameters = {}) => track(new THREE.MeshStandardMaterial({ color, roughness: 0.7, ...extra }));
  const addLight = (x: number, y: number, z: number, color: string, intensity: number, distance: number, flame?: THREE.Object3D) => {
    if (quality === "low" && flickers.length >= 2) return;
    const l = new THREE.PointLight(color, intensity, distance, 2);
    l.position.set(x, y, z);
    group.add(l);
    flickers.push({ light: l, base: intensity, phase: rand() * 10, amount: e.flicker, flame });
  };
  const ring = (count: number, r0: number, r1: number, fn: (x: number, z: number, i: number) => void) => {
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2 + rand() * 0.3;
      const r = r0 + rand() * (r1 - r0);
      fn(Math.cos(a) * r, Math.sin(a) * r, i);
    }
  };

  const build: Record<Prop, () => void> = {
    candles: () => {
      corners.forEach(([cx, cz], ci) => {
        if (ci === 2 || ci === 3) return; // keep the near corners clear for the viewer's hand
        for (let i = 0; i < 3; i++) {
          const h = short ? 0.45 + rand() * 0.75 : 0.6 + rand() * 0.9;
          const x = cx + (rand() - 0.5) * 0.5;
          const z = cz + (rand() - 0.5) * 0.5;
          const candle = new THREE.Mesh(track(new THREE.CylinderGeometry(0.13, 0.15, h, 12)), std("#efe3c8", { roughness: 0.9 }));
          candle.position.set(x, tableY + h / 2, z);
          candle.castShadow = quality === "high";
          group.add(candle);
          const flame = glowSprite(e.glow, 0.5);
          flame.position.set(x, tableY + h + 0.12, z);
          group.add(flame);
          if (i === 0) addLight(x, tableY + h + 0.4, z, e.glow, e.glowIntensity * 6, 16, flame);
        }
      });
    },
    books: () => {
      const [cx, cz] = corners[1]!;
      let y = tableY;
      for (let i = 0; i < 3; i++) {
        const h = (0.22 + rand() * 0.12) * (short ? 0.75 : 1);
        // (at an aisle end, in sight the whole game: smaller and darker, so they don't pull the eye from the cards)
        const book = new THREE.Mesh(track(short ? new THREE.BoxGeometry(0.95, h, 0.7) : new THREE.BoxGeometry(1.3, h, 0.95)),
          std((short ? ["#3a1512", "#172438", "#262f17"] : ["#5a1f1a", "#223a5a", "#3a4a22"])[i]!, { roughness: 0.8 }));
        book.position.set(short ? cx + Math.sign(cx) * 0.1 : cx - 0.2, y + h / 2, short ? cz + 0.85 : cz + 0.1); // (at an aisle end: in front of the candles, not under them)
        book.rotation.y = (rand() - 0.5) * 0.5;
        book.castShadow = quality === "high";
        group.add(book);
        y += h;
      }
    },
    crystal: () => {
      const [cx, cz] = corners[0]!;
      const cr = new THREE.Mesh(track(new THREE.OctahedronGeometry(0.4, 0)), std("#8fc6ff", { emissive: "#3a7ad0", emissiveIntensity: 1.2, roughness: 0.2, metalness: 0.1 }));
      cr.scale.set(1, 1.7, 1);
      cr.position.set(cx, tableY + 0.8, cz);
      group.add(cr);
      spinners.push({ obj: cr, speed: 0.4, bob: 0.08, phase: 0, y: cr.position.y });
      addLight(cr.position.x, cr.position.y + 0.4, cr.position.z, "#7fb6ff", 3, 8);
    },
    lanterns: () => {
      corners.forEach(([cx, cz], ci) => {
        if (ci >= 2) return;
        const tall = short ? 1.0 : 2.2;
        const post = new THREE.Mesh(track(new THREE.CylinderGeometry(0.06, 0.08, tall, 8)), std("#1a1a1a", { metalness: 0.6 }));
        post.position.set(cx, tableY + tall / 2, cz);
        group.add(post);
        const cage = new THREE.Mesh(track(new THREE.BoxGeometry(0.5, 0.65, 0.5)), std("#222", { metalness: 0.7, roughness: 0.4, transparent: true, opacity: 0.55 }));
        cage.position.set(cx, tableY + tall + 0.25, cz);
        group.add(cage);
        const core = glowSprite(e.glow, 1.1);
        core.position.copy(cage.position);
        group.add(core);
        addLight(cx, tableY + tall + 0.2, cz, e.glow, e.glowIntensity * 5, 18, core);
      });
    },
    spires: () => {
      ring(22, 55, 80, (x, z) => {
        const h = 18 + rand() * 30;
        const w = 2 + rand() * 4;
        const tower = new THREE.Mesh(track(new THREE.BoxGeometry(w, h, w)), std("#10131c", { roughness: 1 }));
        tower.position.set(x, floorY + h / 2, z);
        group.add(tower);
        const spire = new THREE.Mesh(track(new THREE.ConeGeometry(w * 0.7, h * 0.35, 4)), std("#0c0f16"));
        spire.position.set(x, floorY + h + h * 0.17, z);
        group.add(spire);
        for (let k = 0; k < 4; k++) {
          const win = glowSprite(rand() > 0.5 ? e.glow : e.rim, 1.4, 0.7);
          win.position.set(x + (rand() - 0.5) * w, floorY + rand() * h, z + (rand() - 0.5) * w);
          group.add(win);
        }
      });
    },
    gravestones: () => {
      ring(26, 26, 45, (x, z) => {
        const h = 1.4 + rand() * 1.6;
        const stone = new THREE.Mesh(track(new THREE.BoxGeometry(1.2, h, 0.3)), std("#3a3f47", { roughness: 1 }));
        stone.position.set(x, floorY + h / 2, z);
        stone.rotation.set((rand() - 0.5) * 0.2, Math.atan2(x, z), (rand() - 0.5) * 0.25);
        group.add(stone);
      });
      ring(10, 40, 60, (x, z) => {
        const trunk = new THREE.Mesh(track(new THREE.CylinderGeometry(0.2, 0.5, 14, 6)), std("#15171b"));
        trunk.position.set(x, floorY + 7, z);
        trunk.rotation.z = (rand() - 0.5) * 0.3;
        group.add(trunk);
      });
    },
    moon: () => {
      const moon = new THREE.Mesh(track(new THREE.SphereGeometry(7, 32, 16)), track(new THREE.MeshBasicMaterial({ color: "#e8eef8", fog: false })));
      moon.position.set(-40, 48, -95);
      group.add(moon);
      const halo = glowSprite("#b8c8ff", 48, 0.35);
      (halo.material as THREE.SpriteMaterial).fog = false;
      halo.position.copy(moon.position);
      group.add(halo);
    },
    columns: () => {
      ring(14, 30, 34, (x, z) => {
        const col = new THREE.Mesh(track(new THREE.CylinderGeometry(0.9, 1.0, 22, 16)), std("#d9d3c6", { roughness: 0.45 }));
        col.position.set(x, floorY + 11, z);
        col.castShadow = false;
        group.add(col);
        const cap = new THREE.Mesh(track(new THREE.BoxGeometry(2.4, 0.6, 2.4)), std("#cfc6b3"));
        cap.position.set(x, floorY + 22.3, z);
        group.add(cap);
      });
    },
    stars: () => {
      const n = quality === "low" ? 400 : 1400;
      const pos = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        const v = new THREE.Vector3(rand() - 0.5, rand() * 0.9 + 0.1, rand() - 0.5).normalize().multiplyScalar(130);
        pos.set([v.x, v.y, v.z], i * 3);
      }
      const geo = track(new THREE.BufferGeometry());
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const pts = new THREE.Points(geo, track(new THREE.PointsMaterial({ color: "#f0e8ff", size: 0.6, sizeAttenuation: true, fog: false, transparent: true, opacity: 0.85 })));
      group.add(pts);
    },
    hedrons: () => {
      const mat = std("#6a6456", { roughness: 0.8, emissive: "#1d5a3e", emissiveIntensity: 0.35 });
      ring(16, 22, 46, (x, z) => {
        const h = new THREE.Mesh(track(new THREE.OctahedronGeometry(1, 0)), mat);
        const s = 1 + rand() * 2.5;
        h.scale.set(s * 0.6, s * 2.2, s * 0.6);
        h.position.set(x, 1 + rand() * 7, z);
        h.rotation.set(rand(), rand(), rand() * 0.5);
        group.add(h);
        const edges = new THREE.LineSegments(track(new THREE.EdgesGeometry(h.geometry)), track(new THREE.LineBasicMaterial({ color: e.inlay, transparent: true, opacity: 0.6 })));
        h.add(edges);
        spinners.push({ obj: h, speed: 0.05 + rand() * 0.08, bob: 0.4, phase: rand() * 6, y: h.position.y });
      });
    },
    torii: () => {
      const red = std("#a3261c", { roughness: 0.6 });
      ring(5, 38, 48, (x, z) => {
        const g2 = new THREE.Group();
        for (const sx of [-3, 3]) {
          const post = new THREE.Mesh(track(new THREE.CylinderGeometry(0.35, 0.4, 12, 10)), red);
          post.position.set(sx, 6, 0);
          g2.add(post);
        }
        const beam = new THREE.Mesh(track(new THREE.BoxGeometry(9, 0.7, 0.7)), red);
        beam.position.y = 12.2;
        g2.add(beam);
        const beam2 = new THREE.Mesh(track(new THREE.BoxGeometry(7.4, 0.45, 0.45)), red);
        beam2.position.y = 10.4;
        g2.add(beam2);
        g2.position.set(x, floorY, z);
        g2.lookAt(0, floorY, 0);
        group.add(g2);
      });
    },
    neon: () => {
      ring(16, 50, 70, (x, z) => {
        const color = rand() > 0.5 ? "#ff5fc8" : "#5fe8ff";
        const sign = new THREE.Mesh(track(new THREE.BoxGeometry(0.4, 3 + rand() * 6, 0.4)), track(new THREE.MeshBasicMaterial({ color })));
        sign.position.set(x, floorY + 6 + rand() * 14, z);
        group.add(sign);
      });
    },
    obelisks: () => {
      ring(8, 30, 42, (x, z) => {
        const h = 14 + rand() * 8;
        const ob = new THREE.Mesh(track(new THREE.CylinderGeometry(0.6, 1.3, h, 4)), std("#b08a55", { roughness: 0.9 }));
        ob.position.set(x, floorY + h / 2, z);
        group.add(ob);
        const tip = new THREE.Mesh(track(new THREE.ConeGeometry(0.85, 1.6, 4)), std("#e3b04b", { metalness: 0.8, roughness: 0.3 }));
        tip.position.set(x, floorY + h + 0.8, z);
        group.add(tip);
      });
    },
    pyramids: () => {
      ring(4, 80, 95, (x, z) => {
        const s = 25 + rand() * 20;
        const py = new THREE.Mesh(track(new THREE.ConeGeometry(s, s * 0.9, 4)), std("#9a7648", { roughness: 1 }));
        py.position.set(x, floorY + s * 0.45, z);
        group.add(py);
      });
    },
    vines: () => {
      ring(12, 38, 55, (x, z) => {
        const pts: THREE.Vector3[] = [];
        for (let k = 0; k < 6; k++) pts.push(new THREE.Vector3(x + Math.sin(k) * 1.5, floorY + k * 4, z + Math.cos(k * 1.3)));
        const tube = new THREE.Mesh(track(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.35, 6)), std("#2c4a24", { roughness: 1 }));
        group.add(tube);
      });
    },
    gold: () => {
      const gold = std("#e8b53a", { metalness: 0.9, roughness: 0.25 });
      corners.forEach(([cx, cz], ci) => {
        if (ci >= 2) return;
        for (let i = 0; i < 9; i++) {
          const coin = new THREE.Mesh(track(new THREE.CylinderGeometry(0.16, 0.16, 0.04, 16)), gold);
          coin.position.set(cx + (rand() - 0.5) * 0.9, tableY + 0.02 + i * 0.012, cz + (rand() - 0.5) * 0.9);
          coin.rotation.set((rand() - 0.5) * 0.4, 0, (rand() - 0.5) * 0.4);
          group.add(coin);
        }
      });
    },
    pipes: () => {
      ring(10, 30, 50, (x, z) => {
        const pts = [new THREE.Vector3(x, floorY, z), new THREE.Vector3(x * 0.9, floorY + 10, z * 0.9), new THREE.Vector3(x * 0.8, floorY + 26, z * 1.1)];
        group.add(new THREE.Mesh(track(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 20, 0.8, 8)), std("#2a2e2a", { metalness: 0.8, roughness: 0.35 })));
      });
    },
    spikes: () => {
      ring(24, 28, 50, (x, z) => {
        const h = 6 + rand() * 14;
        const sp = new THREE.Mesh(track(new THREE.ConeGeometry(0.6 + rand(), h, 6)), std("#d8dcd0", { roughness: 0.5 }));
        sp.position.set(x, floorY + h / 2, z);
        sp.rotation.z = (rand() - 0.5) * 0.4;
        group.add(sp);
      });
    },
    mushrooms: () => {
      corners.forEach(([cx, cz], ci) => {
        if (ci >= 2) return;
        for (let i = 0; i < 3; i++) {
          const h = 0.35 + rand() * 0.4;
          const x = cx + (rand() - 0.5);
          const z = cz + (rand() - 0.5);
          const stem = new THREE.Mesh(track(new THREE.CylinderGeometry(0.06, 0.08, h, 8)), std("#e8e0c8"));
          stem.position.set(x, tableY + h / 2, z);
          group.add(stem);
          const cap = new THREE.Mesh(track(new THREE.SphereGeometry(0.22, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2)), std("#b34a6a", { emissive: "#6a2a8a", emissiveIntensity: 0.6 }));
          cap.position.set(x, tableY + h, z);
          group.add(cap);
        }
        addLight(cx, tableY + 1, cz, "#c8a0ff", 2.2, 8);
      });
    },
    willows: () => {
      ring(9, 34, 55, (x, z) => {
        const trunk = new THREE.Mesh(track(new THREE.CylinderGeometry(0.6, 1.1, 12, 8)), std("#3a3024"));
        trunk.position.set(x, floorY + 6, z);
        group.add(trunk);
        for (let k = 0; k < 5; k++) {
          const leaf = new THREE.Mesh(track(new THREE.SphereGeometry(3 + rand() * 2, 10, 8)), std("#4a6a34", { roughness: 1 }));
          leaf.position.set(x + (rand() - 0.5) * 5, floorY + 12 + rand() * 3, z + (rand() - 0.5) * 5);
          leaf.scale.y = 1.4;
          group.add(leaf);
        }
      });
    },
  };
  for (const prop of e.props) build[prop]();

  // ---- particles
  const particles = buildParticles(e.particles, e.particleColor, quality === "low" ? Math.round(e.particleCount / 3) : quality === "medium" ? Math.round(e.particleCount * 0.6) : e.particleCount, size, rand);
  if (particles) {
    group.add(particles.points);
    disposables.push(particles.points.geometry, particles.points.material as THREE.Material);
  }

  group.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) {
      if (m.geometry) disposables.push(m.geometry);
      const mats = Array.isArray(m.material) ? m.material : [m.material];
      for (const mm of mats) if (mm) disposables.push(mm);
    }
    const s = o as THREE.Sprite;
    if (s.isSprite) {
      const mat = s.material as THREE.SpriteMaterial;
      disposables.push(mat);
      if (mat.map) disposables.push(mat.map);
    }
  });

  return {
    group,
    tableY,
    update(time: number) {
      for (const f of flickers) {
        const n = Math.sin(time * 7.3 + f.phase) * 0.5 + Math.sin(time * 13.1 + f.phase * 2) * 0.3 + Math.sin(time * 2.1 + f.phase) * 0.2;
        f.light.intensity = f.base * (1 + n * f.amount);
        if (f.flame) f.flame.scale.setScalar(0.5 * (1 + n * f.amount * 0.6));
      }
      for (const s of spinners) {
        s.obj.rotation.y += s.speed * 0.016;
        s.obj.position.y = s.y + Math.sin(time * 0.6 + s.phase) * s.bob;
      }
      particles?.update(time);
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

function buildParticles(kind: Particles, color: string, count: number, size: TableSize, rand: () => number) {
  if (count <= 0) return null;
  const pos = new Float32Array(count * 3);
  const seed = new Float32Array(count);
  const spanX = size.w * 0.75 + 20;
  const spanZ = size.d * 0.75 + 20;
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (rand() - 0.5) * spanX;
    pos[i * 3 + 1] = rand() * 12;
    pos[i * 3 + 2] = (rand() - 0.5) * spanZ;
    seed[i] = rand() * 100;
  }
  const base = pos.slice();
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 32, 32);
  const tex = new THREE.CanvasTexture(c);
  const big = kind === "fog";
  const mat = new THREE.PointsMaterial({
    color, map: tex, size: big ? 9 : kind === "petals" ? 0.22 : kind === "stars" ? 0.12 : 0.1,
    transparent: true, opacity: big ? 0.07 : kind === "fireflies" ? 0.9 : 0.55,
    depthWrite: false, blending: big ? THREE.NormalBlending : THREE.AdditiveBlending, sizeAttenuation: true,
  });
  const points = new THREE.Points(geo, mat);
  const attr = geo.getAttribute("position") as THREE.BufferAttribute;
  return {
    points,
    update(time: number) {
      for (let i = 0; i < count; i++) {
        const s = seed[i]!;
        let x = base[i * 3]!;
        let y = base[i * 3 + 1]!;
        let z = base[i * 3 + 2]!;
        switch (kind) {
          case "embers": y = ((y + time * (0.4 + (s % 1))) % 12); x += Math.sin(time + s) * 0.3; break;
          case "petals": case "oil": y = 12 - ((12 - y + time * 0.35 * (0.5 + (s % 1))) % 12); x += Math.sin(time * 0.7 + s) * 1.2; z += Math.cos(time * 0.5 + s) * 0.8; break;
          case "sand": x = ((x + time * 2.5 + spanX / 2) % spanX) - spanX / 2; y = y * 0.4 + Math.sin(time + s) * 0.2; break;
          case "fog": y = -2 + (y % 3); x += Math.sin(time * 0.05 + s) * 3; break;
          case "fireflies": x += Math.sin(time * 0.4 + s) * 1.5; y += Math.sin(time * 0.9 + s * 2) * 0.6; z += Math.cos(time * 0.3 + s) * 1.5; break;
          default: x += Math.sin(time * 0.15 + s) * 0.8; y += Math.sin(time * 0.25 + s * 1.7) * 0.5; z += Math.cos(time * 0.12 + s) * 0.8;
        }
        attr.setXYZ(i, x, y, z);
      }
      attr.needsUpdate = true;
      if (kind === "fireflies" || kind === "stars") mat.opacity = 0.6 + Math.sin(time * 2) * 0.25;
    },
  };
}
