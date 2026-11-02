/**
 * The 3D dice over the 2D table (game/DiceLayer.tsx): a transparent canvas over the page with its own small renderer,
 * lights matching the 3D table's key light and a shadow catcher, so the same dice as the 3D table (table3d/dice.ts)
 * land on the roller's mat with real shadows. World units are CSS pixels, seen from straight above (a slight
 * perspective as dice leave the table); each throw runs in its roller's mat frame, scaled to that mat on screen, so it
 * is the very throw every other screen sees. It draws only while dice move (or the page moves under them), and
 * disposing frees the renderer, its WebGL context and everything the dice used.
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { DiceShow } from "../game/dice";
import { usePrefs } from "../state/prefs";
import { DiceTray } from "./dice";
import { DiceHud } from "./diceHud";
import type { DiceLook } from "./diceLook";
import { tableEnv } from "./diceThrow";
import { MAT_D, MAT_W } from "./layout";

/** Where a roller's mat is on screen, and which edge they sit at. */
export interface MatSpot { rect: DOMRect; near: boolean }

interface Live { key: string; mat: () => MatSpot | null; last: string }

const FOV = 20;

export class DiceOverlay {
  private renderer: THREE.WebGLRenderer;
  readonly canvas: HTMLCanvasElement;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(FOV, 1, 1, 10000);
  private tray: DiceTray;
  private hud: DiceHud;
  private key: THREE.DirectionalLight;
  private catcher: THREE.Mesh;
  private env: THREE.Texture | null = null;
  private live: Live[] = [];
  private raf = 0;
  private w = 0;
  private h = 0;
  private poll = 0;
  private onResize = () => this.kick();

  constructor(quality: "medium" | "high", look: DiceLook) {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "dice-overlay";
    this.canvas.setAttribute("aria-hidden", "true");
    document.body.append(this.canvas);
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, alpha: true, antialias: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === "high" ? 2 : 1.25));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    try {
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      const room = new RoomEnvironment();
      this.env = pmrem.fromScene(room, 0.04).texture;
      room.dispose();
      pmrem.dispose();
    } catch {
      this.env = null;
    }
    this.tray = new DiceTray({ look, envMap: this.env, shadows: true, transmission: quality === "high", envIntensity: 0.55 });
    this.hud = new DiceHud(document.body, (k) => this.dismiss(k), true);
    // the 3D table's light: a warm key from the top left and behind the viewer, a soft fill from the room
    const hemi = new THREE.HemisphereLight(0xfff1dc, 0x2a1d14, 0.75);
    this.key = new THREE.DirectionalLight(0xffe8c8, 2.1);
    this.key.castShadow = true;
    this.key.shadow.mapSize.set(2048, 2048);
    this.key.shadow.bias = -0.0005;
    this.key.shadow.normalBias = 0.5;
    this.catcher = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), new THREE.ShadowMaterial({ opacity: 0.38 }));
    this.catcher.receiveShadow = true;
    this.scene.add(hemi, this.key, this.key.target, this.catcher, this.tray.group);
    this.camera.up.set(0, 0, -1);
    window.addEventListener("resize", this.onResize);
    window.addEventListener("scroll", this.onResize, true);
    window.addEventListener("fyodor:dice-clock", this.onResize);
    this.fit();
  }

  /** Fit the camera to the viewport: 1 world unit = 1 CSS pixel on the table plane. */
  private fit(): void {
    const w = window.innerWidth;
    const h = window.innerHeight;
    if (w === this.w && h === this.h) return;
    this.w = w;
    this.h = h;
    this.renderer.setSize(w, h, false);
    const dist = h / 2 / Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    this.camera.aspect = w / h;
    this.camera.near = dist * 0.4;
    this.camera.far = dist * 1.6;
    this.camera.position.set(w / 2, dist, h / 2);
    this.camera.lookAt(w / 2, 0, h / 2);
    this.camera.updateProjectionMatrix();
    this.catcher.scale.set(w * 1.2, 1, h * 1.2);
    this.catcher.position.set(w / 2, 0, h / 2);
    // light from the top left, as on the 3D table (a slant that throws shadows down and right)
    const r = Math.max(w, h);
    this.key.position.set(w / 2 - 0.35 * r, 1.4 * r, h / 2 - 0.45 * r);
    this.key.target.position.set(w / 2, 0, h / 2);
    Object.assign(this.key.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 1, far: 4 * r });
    this.key.shadow.camera.updateProjectionMatrix();
  }

  /** A mat's frame in the overlay: its centre, turned so its roller sits at their edge, scaled to its size. */
  private frame(spot: MatSpot) {
    const ppu = Math.max(30, Math.min(spot.rect.width / MAT_W, spot.rect.height / MAT_D * 1.15));
    return { x: spot.rect.left + spot.rect.width / 2, z: spot.rect.top + spot.rect.height / 2, rotY: spot.near ? 0 : Math.PI, scale: Math.min(ppu, 74) };
  }

  throw(show: DiceShow, color: string, name: string, mat: () => MatSpot | null): void {
    const spot = mat();
    if (!spot) return;
    this.tray.clear(show.actor);
    this.tray.throw(show, color, name, this.frame(spot), tableEnv(), performance.now());
    this.live.push({ key: show.key, mat, last: "" });
    this.kick();
    // the page can move under the dice (a scroll, a focused seat): follow the mats while there are dice
    if (!this.poll) this.poll = window.setInterval(() => this.follow(), 400);
  }

  private follow(): void {
    let moved = false;
    for (const l of this.live) {
      const spot = l.mat();
      if (!spot) continue;
      const sig = `${Math.round(spot.rect.left)},${Math.round(spot.rect.top)},${Math.round(spot.rect.width)},${Math.round(spot.rect.height)},${spot.near}`;
      if (sig === l.last) continue;
      l.last = sig;
      this.tray.setFrame(l.key, this.frame(spot));
      moved = true;
    }
    if (moved) this.kick();
  }

  dismiss(key: string): void {
    this.tray.dismiss(key);
    this.kick();
  }

  /** Clear a player's dice, or everyone's. */
  clear(actor?: string | null): void {
    this.tray.clear(actor);
    this.kick();
  }

  setLook(look: DiceLook): void {
    this.tray.setLook(look);
    this.kick();
  }

  /** Draw until the dice are still. */
  kick(): void {
    if (this.raf) return;
    const tick = () => {
      this.raf = 0;
      this.fit();
      const reduced = document.body.classList.contains("reduced-motion");
      const moving = this.tray.update(performance.now(), reduced, usePrefs.getState().animationSpeed || 1);
      this.renderer.render(this.scene, this.camera);
      this.hud.render(this.tray.hud((p) => {
        const v = p.clone().project(this.camera);
        return { x: ((v.x + 1) / 2) * this.w, y: ((1 - v.y) / 2) * this.h, visible: v.z < 1 };
      }));
      this.live = this.live.filter((l) => this.tray.restPositions(l.key).length);
      if (!this.live.length && this.poll) {
        window.clearInterval(this.poll);
        this.poll = 0;
      }
      if (moving) this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  /** The dice on screen, in CSS pixels (tests and diagnostics). */
  positions(): { x: number; y: number }[] {
    return this.tray.positions().map((p) => {
      const v = p.project(this.camera);
      return { x: ((v.x + 1) / 2) * this.w, y: ((1 - v.y) / 2) * this.h };
    });
  }

  describe(): ReturnType<DiceTray["describe"]> {
    return this.tray.describe();
  }

  dispose(): void {
    if (this.raf) cancelAnimationFrame(this.raf);
    if (this.poll) window.clearInterval(this.poll);
    window.removeEventListener("resize", this.onResize);
    window.removeEventListener("scroll", this.onResize, true);
    window.removeEventListener("fyodor:dice-clock", this.onResize);
    this.tray.dispose();
    this.hud.dispose();
    this.catcher.geometry.dispose();
    (this.catcher.material as THREE.Material).dispose();
    this.env?.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.canvas.remove();
  }
}
