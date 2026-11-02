/**
 * The dice & toys tray in 3D (game/TableToys.tsx): a small felt tray on its own canvas, thrown with the live table's
 * own dice (table3d/dice.ts DiceTray, simulated by table3d/physics.ts with cannon-es). It is only loaded when the tray
 * opens with the 3D table available; without WebGL, on the low graphics setting or if anything here fails, the tray is
 * the 2D throw instead. Local only: the numbers come from game/toys.ts, nothing reaches the server or the live table.
 *
 * DiceTray throws one kind of die at a time, so each kind gets its own lane across the tray; kinds thrown first rest
 * as solid blocks for the later ones, so dice never come to rest inside each other. Nothing renders once the dice
 * have settled (no always-on loop), and closing disposes the renderer, its WebGL context, the tray's geometries,
 * materials and textures (the physics world lives only inside each simulate() call).
 */
import * as THREE from "three";
import { DICE_SHOWN, type DiceShow } from "../game/dice";
import { DiceTray, dieShape } from "./dice";
import type { Obstacle } from "./physics";

/** One kind of die in a throw. */
export interface TrayGroup { key: string; sides: number; coin: boolean; results: number[] }
export interface TrayLane { from: THREE.Vector3; land: (i: number, n: number) => THREE.Vector3; radius: number }
export interface TrayPlan { width: number; depth: number; bounds: { minX: number; maxX: number; minZ: number; maxZ: number }; lanes: TrayLane[] }

const DEPTH = 5;
const MIN_WIDTH = 9.6;
const ELEVATION = THREE.MathUtils.degToRad(55);
const GAP = 0.35;
const PER_ROW = 4; // DiceTray leaves the hand four abreast
const COIN_R = 0.3;
const RIM_H = 0.32;
const RIM_T = 0.28;

const radiusOf = (g: Pick<TrayGroup, "sides" | "coin">) => (g.coin ? COIN_R : dieShape(g.sides).radius);

/**
 * Lanes side by side across the tray, each as wide as its kind leaves the hand, thrown from the near edge toward the
 * far one. The tray widens for a big pool so no lane overlaps another as the dice leave the hand.
 */
export function planTray(groups: Pick<TrayGroup, "sides" | "coin" | "results">[]): TrayPlan {
  const spans = groups.map((g) => {
    const r = radiusOf(g);
    const step = r * 2 + 0.15;
    const n = Math.max(1, g.results.length);
    return { r, step, w: Math.min(PER_ROW, n) * step, rows: Math.ceil(n / PER_ROW) };
  });
  const need = spans.reduce((a, s) => a + s.w, 0) + GAP * Math.max(0, spans.length - 1);
  const width = Math.max(MIN_WIDTH, need + 1.2);
  const bounds = { minX: -width / 2, maxX: width / 2, minZ: -DEPTH / 2, maxZ: DEPTH / 2 };
  let x = -need / 2;
  const lanes = spans.map((s) => {
    const cx = x + s.w / 2;
    x += s.w + GAP;
    // the last row leaves the hand just inside the near rim
    const fromZ = bounds.maxZ - 0.2 - s.r - (s.rows - 1) * s.step;
    const land = (i: number, n: number) => {
      const perRow = Math.min(n, PER_ROW);
      const row = Math.floor(i / perRow);
      const inRow = Math.min(perRow, n - row * perRow);
      return new THREE.Vector3(cx + (i % perRow - (inRow - 1) / 2) * s.step, 0, bounds.minZ + 1.1 + row * s.step * 0.8);
    };
    return { from: new THREE.Vector3(cx, 0, fromZ), land, radius: s.r };
  });
  return { width, depth: DEPTH, bounds, lanes };
}

export interface TrayOptions { reduced: boolean; speed: number; color: string }

export class ToyTrayScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(34, 2, 0.1, 100);
  private dice = new DiceTray();
  private tray = new THREE.Group();
  private trayWidth = 0;
  private owned: { dispose(): void }[] = [];
  private raf = 0;
  private started = 0;
  private stableSince = 0;
  private lastSig = "";
  private opts: TrayOptions = { reduced: false, speed: 1, color: "#d7ae63" };
  private resize: ResizeObserver | null = null;
  /** Called once the dice of a throw have come to rest. */
  onSettled: (() => void) | null = null;

  constructor(private canvas: HTMLCanvasElement, quality: "medium" | "high" = "high") {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === "high" ? 2 : 1.25));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.setClearColor(0x000000, 0);
    const hemi = new THREE.HemisphereLight(0xfff1dc, 0x1a120c, 1.15);
    const key = new THREE.DirectionalLight(0xffe8c8, 2.1);
    key.position.set(2.5, 8, 5);
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
    this.dice.dispose();
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
      this.dice.throw(show, opts.color, { from: lane.from, land: lane.land, bounds: plan.bounds, obstacles: [...resting] }, now);
      // where this kind comes to rest (update with `reduced` poses every die at the end of its throw); the kinds
      // thrown after it bounce off those spots instead of resting inside them
      this.dice.update(now, true, 1);
      const all = this.dice.positions();
      for (const p of all.slice(all.length - Math.min(g.results.length, DICE_SHOWN))) {
        resting.push({ x: p.x, z: p.z, w: lane.radius * 1.5, d: lane.radius * 1.5, h: lane.radius * 1.3 });
      }
    });
    this.started = now;
    this.stableSince = now;
    this.lastSig = "";
    this.loop();
  }

  private loop(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    const tick = () => {
      this.raf = 0;
      const now = performance.now();
      const { reduced, speed } = this.opts;
      const rate = Math.max(0.25, speed);
      this.dice.update(now, reduced, speed);
      this.render();
      const sig = this.dice.positions().map((p) => `${p.x.toFixed(3)},${p.y.toFixed(3)},${p.z.toFixed(3)}`).join(";");
      if (sig !== this.lastSig) {
        this.lastSig = sig;
        this.stableSince = now;
      }
      // at rest (and the numbers above them faded in): stop drawing until the next throw. A throw lasts four
      // simulated seconds at most; the dice would start to fade (DICE_HOLD_MS) well after this.
      const settle = Math.max(400, 400 / rate);
      if (reduced || now - this.stableSince > settle || now - this.started > 4000 / rate + settle + 500) {
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
    // the tray seen from above at an angle: its depth is foreshortened; the numbers float a little above the dice
    const dist = Math.max((this.trayWidth / 2 + RIM_T + 0.2) / (half * this.camera.aspect), ((DEPTH * Math.sin(ELEVATION)) / 2 + 0.8) / half);
    this.camera.position.set(0, 0.3 + Math.sin(ELEVATION) * dist, Math.cos(ELEVATION) * dist);
    this.camera.lookAt(0, 0.3, 0);
    this.camera.updateProjectionMatrix();
  }

  /** The felt and its wooden rim (rebuilt when a big pool widens the tray). */
  private buildTray(width: number): void {
    this.disposeTray();
    this.trayWidth = width;
    const felt = new THREE.MeshStandardMaterial({ color: 0x1d3c44, roughness: 0.96, metalness: 0 });
    const wood = new THREE.MeshStandardMaterial({ color: 0x3b2117, roughness: 0.62, metalness: 0.05 });
    const bed = new THREE.PlaneGeometry(width, DEPTH).rotateX(-Math.PI / 2);
    const long = new THREE.BoxGeometry(width + RIM_T * 2, RIM_H, RIM_T);
    const short = new THREE.BoxGeometry(RIM_T, RIM_H, DEPTH);
    this.owned.push(felt, wood, bed, long, short);
    this.tray.add(new THREE.Mesh(bed, felt));
    for (const [geo, x, z] of [[long, 0, -DEPTH / 2 - RIM_T / 2], [long, 0, DEPTH / 2 + RIM_T / 2], [short, -width / 2 - RIM_T / 2, 0], [short, width / 2 + RIM_T / 2, 0]] as const) {
      const m = new THREE.Mesh(geo, wood);
      m.position.set(x, RIM_H / 2, z);
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
    this.dice.dispose(); // the throws' materials, textures and geometries (the dice shapes are shared with the table)
    this.disposeTray();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}
