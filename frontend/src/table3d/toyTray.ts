/**
 * The dice & toys tray in 3D (game/TableToys.tsx): a small felt tray on its own canvas, thrown with the live table's
 * own dice (table3d/dice.ts DiceTray, simulated by table3d/diceThrow.ts with cannon-es). It is only loaded when the
 * tray opens with the 3D table available; without WebGL, on the low graphics setting or if anything here fails, the
 * tray is the 2D throw instead. Local only: the numbers come from game/toys.ts, nothing reaches the server or the
 * live table.
 *
 * Each kind of die gets its own lane across the tray, thrown from the near rim toward the far one; kinds thrown first
 * rest as solid blocks for the later ones, so dice never come to rest inside each other. Nothing renders once the
 * dice have settled (no always-on loop), and closing disposes the renderer, its WebGL context and the tray's
 * geometries, materials and textures (the physics world lives only inside each throw).
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { DICE_SHOWN, type DiceShow } from "../game/dice";
import type { DiceLook } from "./diceLook";
import { COIN_RADIUS, dieSolid, kindsFor } from "./diceGeometry";
import { DiceTray } from "./dice";
import type { ThrowEnv } from "./diceThrow";
import type { Obstacle } from "./physics";

/** One kind of die in a throw. */
export interface TrayGroup { key: string; sides: number; coin: boolean; results: number[] }
/** A lane: its centre across the tray and its width. */
export interface TrayLane { x: number; width: number; radius: number }
export interface TrayPlan { width: number; depth: number; bounds: { minX: number; maxX: number; minZ: number; maxZ: number }; lanes: TrayLane[] }

const DEPTH = 5.4;
const MIN_WIDTH = 9.6;
const ELEVATION = THREE.MathUtils.degToRad(56);
const GAP = 0.3;
const RIM_H = 0.34;
const RIM_T = 0.3;

const radiusOf = (g: Pick<TrayGroup, "sides" | "coin">) => {
  const k = kindsFor(g.sides, g.coin)[0]!;
  return k === "coin" ? COIN_RADIUS : dieSolid(k).radius;
};
const countOf = (g: Pick<TrayGroup, "sides" | "coin" | "results">) => Math.min(DICE_SHOWN, g.results.length * (g.sides === 100 && !g.coin ? 2 : 1));

/** Lanes side by side across the tray, each wide enough for its dice; the tray widens for a big pool. */
export function planTray(groups: Pick<TrayGroup, "sides" | "coin" | "results">[]): TrayPlan {
  const spans = groups.map((g) => {
    const r = radiusOf(g);
    const n = Math.max(1, countOf(g));
    return { r, w: Math.max(2.2, Math.min(4, n) * r * 2.3) };
  });
  const need = spans.reduce((a, s) => a + s.w, 0) + GAP * Math.max(0, spans.length - 1);
  const width = Math.max(MIN_WIDTH, need + 1.2);
  const bounds = { minX: -width / 2, maxX: width / 2, minZ: -DEPTH / 2, maxZ: DEPTH / 2 };
  let x = -need / 2;
  const lanes = spans.map((s) => {
    const lane = { x: x + s.w / 2, width: s.w, radius: s.r };
    x += s.w + GAP;
    return lane;
  });
  return { width, depth: DEPTH, bounds, lanes };
}

/** A lane's throw, in its own frame (x across from the lane's centre, z toward the near rim). */
export function laneEnv(plan: TrayPlan, lane: TrayLane, obstacles: Obstacle[]): ThrowEnv {
  const b = plan.bounds;
  const half = lane.width / 2;
  return {
    bounds: { minX: b.minX - lane.x, maxX: b.maxX - lane.x, minZ: b.minZ, maxZ: b.maxZ },
    obstacles: obstacles.map((o) => ({ ...o, x: o.x - lane.x })),
    hand: new THREE.Vector3(0, 1.0, b.maxZ - 0.35 - lane.radius),
    land: { minX: -half * 0.6, maxX: half * 0.6, minZ: b.minZ + 0.9, maxZ: b.minZ + 2.2 },
    keep: { minX: b.minX - lane.x + 0.05, maxX: b.maxX - lane.x - 0.05, minZ: b.minZ + 0.05, maxZ: b.maxZ - 0.05 },
  };
}

export interface TrayOptions { reduced: boolean; speed: number; color: string; look?: DiceLook }

export class ToyTrayScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(34, 2, 0.1, 100);
  private dice: DiceTray;
  private tray = new THREE.Group();
  private trayWidth = 0;
  private owned: { dispose(): void }[] = [];
  private env: THREE.Texture | null = null;
  private raf = 0;
  private started = 0;
  private opts: TrayOptions = { reduced: false, speed: 1, color: "#d7ae63" };
  private resize: ResizeObserver | null = null;
  /** Called once the dice of a throw have come to rest. */
  onSettled: (() => void) | null = null;

  constructor(private canvas: HTMLCanvasElement, quality: "medium" | "high" = "high", look: DiceLook = "resin") {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === "high" ? 2 : 1.25));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.setClearColor(0x000000, 0);
    if (this.renderer.shadowMap) {
      this.renderer.shadowMap.enabled = quality === "high";
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    try {
      // soft studio reflections for the glossy dice (no download)
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      const room = new RoomEnvironment();
      this.env = pmrem.fromScene(room, 0.04).texture;
      room.dispose();
      pmrem.dispose();
    } catch {
      this.env = null;
    }
    this.dice = new DiceTray({ look, envMap: this.env, shadows: quality === "high", transmission: quality === "high", envIntensity: 0.6 });
    const hemi = new THREE.HemisphereLight(0xfff1dc, 0x1a120c, 1.0);
    const key = new THREE.DirectionalLight(0xffe8c8, 2.2);
    key.position.set(-3, 9, 5);
    key.castShadow = quality === "high";
    key.shadow.mapSize.set(1024, 1024);
    Object.assign(key.shadow.camera, { left: -8, right: 8, top: 5, bottom: -5, near: 1, far: 30 });
    key.shadow.bias = -0.0004;
    this.scene.add(hemi, key, this.tray, this.dice.group);
    this.buildTray(MIN_WIDTH);
    this.fit();
    if (typeof ResizeObserver !== "undefined") {
      this.resize = new ResizeObserver(() => {
        this.fit();
        if (!this.raf) this.render();
      });
      this.resize.observe(canvas);
    }
    this.render();
  }

  /** Throw the roll's dice into the tray (the earlier throw is cleared away). */
  throw(groups: TrayGroup[], opts: TrayOptions): void {
    this.opts = opts;
    if (opts.look) this.dice.setLook(opts.look);
    this.dice.clear(undefined, -1e9); // gone at once, not sinking
    this.dice.update(performance.now(), false, 1);
    const plan = planTray(groups);
    if (Math.abs(plan.width - this.trayWidth) > 1e-6) {
      this.buildTray(plan.width);
      this.fit();
    }
    const now = performance.now();
    const resting: Obstacle[] = [];
    groups.forEach((g, i) => {
      const lane = plan.lanes[i]!;
      const show: DiceShow = { key: g.key, actor: null, sides: g.sides, results: g.results, coin: g.coin };
      this.dice.throw(show, opts.color, "", { x: lane.x, z: 0, rotY: 0 }, laneEnv(plan, lane, resting), now);
      // where this kind comes to rest: the kinds thrown after it bounce off those spots instead of resting inside them
      for (const p of this.dice.restPositions(g.key)) resting.push({ x: p.x, z: p.z, w: lane.radius * 1.5, d: lane.radius * 1.5, h: lane.radius * 1.3 });
    });
    this.started = now;
    this.loop();
  }

  private loop(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    const tick = () => {
      this.raf = 0;
      const now = performance.now();
      const { reduced, speed } = this.opts;
      const moving = this.dice.update(now, reduced, speed);
      this.render();
      // at rest: stop drawing until the next throw (a throw lasts a few simulated seconds at most)
      if (reduced || !moving || now - this.started > 6000 / Math.max(0.25, speed)) {
        this.onSettled?.();
        return;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private render(): void {
    this.renderer.render(this.scene, this.camera);
  }

  /** Frame the whole tray in the canvas. */
  private fit(): void {
    const w = Math.max(1, this.canvas.clientWidth);
    const h = Math.max(1, this.canvas.clientHeight);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    const half = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    // the tray seen from above at an angle: its depth is foreshortened
    const dist = Math.max((this.trayWidth / 2 + RIM_T + 0.2) / (half * this.camera.aspect), ((DEPTH * Math.sin(ELEVATION)) / 2 + 0.6) / half);
    this.camera.position.set(0, 0.2 + Math.sin(ELEVATION) * dist, Math.cos(ELEVATION) * dist);
    this.camera.lookAt(0, 0.2, 0);
    this.camera.updateProjectionMatrix();
  }

  /** The felt and its wooden rim (rebuilt when a big pool widens the tray). */
  private buildTray(width: number): void {
    this.disposeTray();
    this.trayWidth = width;
    const felt = new THREE.MeshStandardMaterial({ color: 0x1d3c44, roughness: 0.96, metalness: 0 });
    const wood = new THREE.MeshStandardMaterial({ color: 0x3b2117, roughness: 0.55, metalness: 0.05 });
    const bed = new THREE.PlaneGeometry(width, DEPTH).rotateX(-Math.PI / 2);
    const long = new THREE.BoxGeometry(width + RIM_T * 2, RIM_H, RIM_T);
    const short = new THREE.BoxGeometry(RIM_T, RIM_H, DEPTH);
    this.owned.push(felt, wood, bed, long, short);
    const floor = new THREE.Mesh(bed, felt);
    floor.receiveShadow = true;
    this.tray.add(floor);
    for (const [geo, x, z] of [[long, 0, -DEPTH / 2 - RIM_T / 2], [long, 0, DEPTH / 2 + RIM_T / 2], [short, -width / 2 - RIM_T / 2, 0], [short, width / 2 + RIM_T / 2, 0]] as const) {
      const m = new THREE.Mesh(geo, wood);
      m.position.set(x, RIM_H / 2, z);
      m.castShadow = m.receiveShadow = true;
      this.tray.add(m);
    }
  }

  private disposeTray(): void {
    this.tray.clear();
    for (const x of this.owned) x.dispose();
    this.owned = [];
  }

  /** Where the dice are now (tests and diagnostics). */
  positions(): THREE.Vector3[] {
    return this.dice.positions();
  }

  dispose(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.onSettled = null;
    this.resize?.disconnect();
    this.dice.dispose(); // the throws' materials (and the shared dice meshes and atlases, when nothing else uses them)
    this.disposeTray();
    this.env?.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}
