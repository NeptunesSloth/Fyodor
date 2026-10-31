import { tapGesture } from "../game/rules/intents";
/**
 * The 3D table (M19): a three.js scene driven entirely by the server's per-viewer view.
 *
 * The scene is a renderer, not a second source of truth: every frame it eases card objects
 * toward where the view says they are. Gestures go through the same actions as the 2D table
 * (dropCards, tapCards, cardMenu…), so rules intents, the manual override and hidden
 * information all behave identically. Hidden cards arrive without identity and are drawn as
 * backs; the scene never has anything more to hide.
 */
import * as THREE from "three";
import { openMenu } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { imageUrl } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, type CardStats, type GameCard, type GameView, type LibraryView, type ZoneName } from "../types/game";
import { counterShort, isKeyword } from "../game/counters";
import { draw, tapCards, targetsFor } from "../game/actions";
import { cardMenu } from "../game/cardMenu";
import { tableMenu } from "../game/selection";
import { zonePileTops } from "../game/piles";
import type { DropResult } from "../game/dnd";
import type { PingTarget } from "../services/night";
import { dropCards } from "../game/drop";
import { pickClick } from "../game/Overlays";
import { answerByClick, legalClass } from "../game/rules/RulesHud";
import { libraryMenu, pileMenu, PILE_LABEL } from "../game/ZonePile";
import type { PlaneTheme } from "../theme/planes";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { buildEnvironment, type Environment } from "./environment";
import { arrowTime, makeArrow, type GroundBox } from "./arrows";
import { angleDelta, ease, liftFor } from "./motion";
import { createPost, type Post } from "./post";
import { DiceTray } from "./dice";
import type { DiceShow } from "../game/dice";
import {
  AISLE, CARD_H, CARD_W, MAT_D, MAT_W, PILES, PLAQUE_AT, localToVirtual, onBattlefield, pileAt, seats, tableSize, toLocal, toWorld,
  virtualToLocal, type PileZone, type Seat,
} from "./layout";
import { backCanvas, canvasTexture, cardOverlayCanvas, contactShadowTexture, type CardOverlay, matTexture, setMaxAnisotropy, slotTexture, textCardCanvas } from "./textures";

/** How long a refused action's card stays marked. */
export const ERROR_MS = 1800;

export type Quality = "low" | "medium" | "high";
export type CameraPreset = "seat" | "overview" | { focus: string } | { card: string };

const THICK = 0.016;
/** Cards drawn per pile at most (taller piles space them out). */
const PILE_LAYERS = 48;
const LIFT = 0.55;

export interface ScreenRect { id: string; left: number; top: number; right: number; bottom: number }

interface CardObj {
  id: string;
  group: THREE.Group;
  face: THREE.Mesh;
  glow: THREE.Mesh;
  /** P/T plate, damage, keyword badges and counters drawn on the card (null when there is nothing). */
  overlay: THREE.Mesh | null;
  overlayKey: string;
  faceKey: string;
  target: THREE.Vector3;
  rot: number;
  tilt: number;
  /** Target size (stack cards stand larger); eased like position. */
  scale: number;
  seen: boolean;
}

interface PileObj {
  /** Invisible hit box for clicks and drops (sized to the pile). */
  block: THREE.Mesh;
  slot: THREE.Mesh;
  /** The pile itself: real card bodies stacked with a little hand-squared jitter. */
  layers: THREE.InstancedMesh;
  /** The library's top card back. */
  top: THREE.Mesh | null;
  count: number;
}

function roundedRect(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2);
  s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r);
  s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2);
  s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r);
  s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

/** A flat rounded rectangle lying on the table, UVs 0..1, top edge toward local −z. */
function flatCardGeometry(w: number, h: number, r: number): THREE.ShapeGeometry {
  const geo = new THREE.ShapeGeometry(roundedRect(w, h, r), 6);
  const pos = geo.getAttribute("position") as THREE.BufferAttribute;
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) + w / 2) / w, (pos.getY(i) + h / 2) / h);
  geo.rotateX(-Math.PI / 2);
  return geo;
}

/** How tall a pile of n cards stands (real card thickness, gently compressed for big piles). */
function pileHeight(n: number): number {
  return n <= 0 ? 0 : Math.min(n, 40) * THICK * 0.9 + Math.max(0, n - 40) * THICK * 0.35;
}

/** Deterministic per-layer jitter so a pile looks squared by hand, not machine-stacked. */
function jitter(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return x - Math.floor(x) - 0.5;
}

/**
 * What a battlefield card's badges say. P/T shows only when it differs from the printed card or the
 * creature is damaged or carries badges, so an unmodified board costs no extra draw calls.
 */
function overlayFor(card: GameCard, stats: CardStats | undefined): CardOverlay | null {
  const counters = Object.entries(card.counters ?? {}).filter(([, n]) => n > 0);
  const plus = card.counters?.["+1/+1"] ?? 0;
  const minus = card.counters?.["-1/-1"] ?? 0;
  const keywords: { kind: string; n: number }[] = counters.filter(([k]) => isKeyword(k)).map(([kind, n]) => ({ kind, n }));
  for (const k of stats?.gained ?? []) if (isKeyword(k) && !keywords.some((x) => x.kind === k.toLowerCase())) keywords.push({ kind: k.toLowerCase(), n: 1 });
  const others = counters.filter(([k]) => !isKeyword(k) && k !== "+1/+1" && k !== "-1/-1").map(([k, n]) => ({ label: k === "loyalty" ? "◆" : counterShort(k), n }));
  const damage = card.damage ?? 0;
  let pt: CardOverlay["pt"];
  if (stats?.pt) {
    const bp = Number(stats.base?.[0]);
    const bt = Number(stats.base?.[1]);
    const d = Number.isFinite(bp) && Number.isFinite(bt) ? stats.pt[0] - bp + (stats.pt[1] - bt) : plus - minus;
    const dir = d > 0 ? 1 : d < 0 ? -1 : 0;
    if (dir || damage || keywords.length || plus || minus) pt = { text: `${stats.pt[0]}/${stats.pt[1]}`, dir };
  } else if (plus !== minus) {
    const net = plus - minus;
    pt = { text: net > 0 ? `+${net}/+${net}` : `${net}/${net}`, dir: net > 0 ? 1 : -1 };
  }
  if (!pt && !damage && !keywords.length && !others.length) return null;
  return { ...(pt ? { pt } : {}), ...(damage ? { damage } : {}), keywords, counters: others };
}

const UP = new THREE.Vector3(0, 1, 0);
/** One red for every attack beam (DESIGN.md: attack-beam). */
const ATTACK_RED = "#ff5a2a";
const liftTarget = new THREE.Vector3();
const shadowPos = new THREE.Vector3();
const shadowQ = new THREE.Quaternion();
const shadowScale = new THREE.Vector3();
const shadowM = new THREE.Matrix4();
const shadowColor = new THREE.Color();

function angleLerp(a: number, b: number, t: number): number {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

/** frameMs: average CPU time per frame (scene update + render submit), logged, never asserted. */
export interface SceneStats { fps: number; calls: number; triangles: number; cards: number; arrows?: number; frameMs?: number }

export class TableScene {
  readonly canvas: HTMLCanvasElement;
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
  private env: Environment | null = null;
  private world = new THREE.Group();
  private cards = new Map<string, CardObj>();
  private piles = new Map<string, PileObj>();
  private mats = new Map<string, THREE.Mesh>();
  private handFans = new Map<string, THREE.Group>();
  private seatList: Seat[] = [];
  private seatKey = "";
  private plane: PlaneTheme;
  private quality: Quality;
  private view: GameView | null = null;
  private me = "";
  private raf = 0;
  private clock = new THREE.Clock();
  private ray = new THREE.Raycaster();
  private tablePlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private camPos = new THREE.Vector3(0, 30, 30);
  private camLook = new THREE.Vector3();
  private camGoalPos = new THREE.Vector3(0, 30, 30);
  private camGoalLook = new THREE.Vector3();
  private preset: CameraPreset = "seat";
  private zoom = 1;
  private yaw = 0;
  private drag: { ids: string[]; anchor: string; start: [number, number]; grab: THREE.Vector3; offsets: Map<string, THREE.Vector3>; active: boolean } | null = null;
  private orbit: { x: number; yaw: number } | null = null;
  /** Box selection: dragging on the bare table draws a rectangle (as on the 2D table). */
  private marquee: { x0: number; y0: number; add: boolean; el: HTMLDivElement } | null = null;
  private hovered: string | null = null;
  /** The store's selection, for the selected-card lift. */
  private selectedIds = new Set<string>();
  private lastClick = { id: "", at: 0 };
  private frames = 0;
  private fpsAt = 0;
  private frameTime = 0;
  stats: SceneStats = { fps: 0, calls: 0, triangles: 0, cards: 0 };
  /** Called once per frame after rendering: DOM overlays that follow the table hook in here, so the
   * three.js loop stays the only animation loop. */
  onFrame: (() => void) | null = null;

  private cardFaceGeo = flatCardGeometry(CARD_W, CARD_H, 0.05);
  private cardBodyGeo: THREE.ExtrudeGeometry;
  private glowGeo = flatCardGeometry(CARD_W + 0.12, CARD_H + 0.12, 0.09);
  /** Card stock: the pale core you see on a card's edge. */
  private bodyMat = new THREE.MeshStandardMaterial({ color: "#cdc6b8", roughness: 0.78 });
  private hitMat = new THREE.MeshBasicMaterial({ visible: false });
  private textures = new Map<string, THREE.Texture>();
  private materials = new Map<string, THREE.MeshStandardMaterial>();
  private loader = new THREE.TextureLoader();
  private failed = new Set<string>();
  private unsubs: (() => void)[] = [];
  /** Every card's body (its thickness and shadow) in one draw call. */
  private bodies: THREE.InstancedMesh;
  private arrows = new THREE.Group();
  private dice = new DiceTray();
  /** A soft contact shadow under every card (one draw call), spreading as the card lifts. */
  private shadows: THREE.InstancedMesh;
  private shadowTex = contactShadowTexture();
  private arrowKey = "";
  /** Where the stack's standing cards are (beams route around it), and each stack card's beam anchor. */
  private stackBox: GroundBox | null = null;
  private stackAnchors = new Map<string, { far: THREE.Vector3; near: THREE.Vector3 }>();
  /** Soft studio reflections for metal, lacquer and card gloss (a prefiltered room, no download). */
  private envMap: THREE.Texture;
  private post: Post | null = null;

  constructor(container: HTMLElement, plane: PlaneTheme, quality: Quality) {
    this.plane = plane;
    this.quality = quality;
    this.renderer = new THREE.WebGLRenderer({ antialias: quality !== "low", powerPreference: "high-performance", preserveDrawingBuffer: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === "high" ? 2 : quality === "medium" ? 1.5 : 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.shadowMap.enabled = quality !== "low";
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.canvas = this.renderer.domElement;
    this.canvas.className = "table3d-canvas";
    this.canvas.dataset.drop3d = "";
    container.appendChild(this.canvas);
    this.renderer.info.autoReset = false; // count every pass of a frame, not just the last
    setMaxAnisotropy(this.renderer.capabilities.getMaxAnisotropy());
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const room = new RoomEnvironment();
    this.envMap = pmrem.fromScene(room, 0.04).texture;
    room.dispose();
    pmrem.dispose();
    this.scene.environment = this.envMap;
    this.scene.environmentIntensity = 0.3;
    if (quality === "high") this.post = createPost(this.renderer, this.scene, this.camera);
    // a card body with a hair of bevel so its edge catches the light
    const bevel = 0.004;
    const body = new THREE.ExtrudeGeometry(roundedRect(CARD_W - bevel * 2, CARD_H - bevel * 2, 0.045), {
      depth: THICK - bevel * 2, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 6,
    });
    body.rotateX(-Math.PI / 2);
    body.translate(0, bevel, 0);
    this.cardBodyGeo = body;
    this.bodies = new THREE.InstancedMesh(body, this.bodyMat, 1024);
    this.bodies.castShadow = quality !== "low";
    this.bodies.receiveShadow = quality !== "low";
    this.bodies.count = 0;
    this.bodies.frustumCulled = false;
    const shadowGeo = new THREE.PlaneGeometry(CARD_W * 1.55, CARD_H * 1.45);
    shadowGeo.rotateX(-Math.PI / 2);
    // per-instance strength rides in instanceColor.r (the shadow itself is always black)
    const shadowMat = new THREE.MeshBasicMaterial({ color: "#fff", alphaMap: this.shadowTex, transparent: true, opacity: 0.9, depthWrite: false });
    shadowMat.onBeforeCompile = (sh) => {
      sh.fragmentShader = sh.fragmentShader.replace("#include <alphamap_fragment>", "#include <alphamap_fragment>\n diffuseColor.a *= diffuseColor.r;\n diffuseColor.rgb = vec3(0.0);");
    };
    shadowMat.customProgramCacheKey = () => "card-contact-shadow";
    this.shadows = new THREE.InstancedMesh(shadowGeo, shadowMat, 1024);
    this.shadows.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(1024 * 3).fill(1), 3);
    this.shadows.count = 0;
    this.shadows.frustumCulled = false;
    this.shadows.renderOrder = -1;
    this.world.add(this.bodies, this.shadows, this.arrows, this.dice.group);
    this.scene.add(this.world);
    this.applyFog();
    this.bindInput();
    this.loop();
  }

  // ------------------------------------------------------------------ public API

  setPlane(plane: PlaneTheme): void {
    if (plane.id === this.plane.id) return;
    this.plane = plane;
    this.applyFog();
    this.rebuildTable();
  }

  setCamera(preset: CameraPreset): void {
    this.preset = preset;
    this.yaw = 0;
    this.zoom = 1;
    this.updateCameraGoal();
  }

  resize(w: number, h: number): void {
    this.renderer.setSize(w, h, false);
    this.post?.setSize(w, h);
    this.camera.aspect = w / Math.max(1, h);
    // frame the table above the hand: render the lower part of a taller frame, which lifts what the
    // camera looks at by half the hand band (picking and projection use the same matrices)
    const band = Math.round(h * 0.16);
    this.camera.setViewOffset(w, h + band, 0, band, w, h);
    this.camera.updateProjectionMatrix();
    this.updateCameraGoal();
  }

  update(view: GameView, me: string): void {
    this.view = view;
    this.me = me;
    const key = `${view.seat_order.join(",")}|${me}`;
    if (key !== this.seatKey) {
      this.seatKey = key;
      this.seatList = seats(view.seat_order, me);
      this.rebuildTable();
      this.updateCameraGoal();
    }
    this.syncCards();
  }

  /**
   * A roll everyone sees (game/dice.ts): the dice leave the roller's near edge, cross their mat and land in a
   * row in the aisle in front of it, by their plaque.
   */
  throwDice(show: DiceShow): void {
    const seat = this.seatList.find((s) => s.player === show.actor) ?? this.seatList.find((s) => s.player === this.me);
    if (!seat) return;
    const color = this.view?.players.find((p) => p.id === seat.player)?.color ?? "#d7ae63";
    const [fx, fz] = toWorld(seat, 2.2, MAT_D / 2 + 0.6);
    const land = (i: number, n: number) => {
      // aimed side by side (as they leave the hand: table3d/dice.ts), so they don't converge mid-air
      const perRow = Math.min(n, 4);
      const row = Math.floor(i / perRow);
      const inRow = Math.min(perRow, n - row * perRow);
      const lx = 1.4 + (i % perRow - (inRow - 1) / 2) * 1.1;
      const [wx, wz] = toWorld(seat, lx, -MAT_D / 2 - AISLE * 0.42 - row * 1.1);
      return new THREE.Vector3(wx, 0, wz);
    };
    const size = tableSize(this.seatList);
    const bounds = { minX: -size.w / 2 + 0.6, maxX: size.w / 2 - 0.6, minZ: -size.d / 2 + 0.6, maxZ: size.d / 2 - 0.6 };
    // every seat's piles are solid: a die that reaches a deck glances off it
    const obstacles = this.seatList.flatMap((s) => (["library", "graveyard", "exile"] as const).flatMap((zone) => {
      const n = this.piles.get(`${s.player}:${zone}`)?.count ?? 0;
      if (!n) return [];
      const [x, z] = toWorld(s, ...PILES[zone]);
      return [{ x, z, w: CARD_W, d: CARD_H, h: pileHeight(n) + THICK }];
    }));
    this.dice.throw(show, color, { from: new THREE.Vector3(fx, 0, fz), land, bounds, obstacles }, performance.now());
  }

  /** The dice on the table, in screen coordinates (tests and diagnostics). */
  diceOnScreen(): { x: number; y: number }[] {
    return this.dice.positions().map((p) => this.project(p));
  }

  /** Where a seat's player plate should be drawn on screen (for the DOM overlay). */
  seatScreen(player: string, width: number, height: number): { x: number; y: number; visible: boolean } | null {
    const seat = this.seatList.find((s) => s.player === player);
    if (!seat) return null;
    const [wx, wz] = toWorld(seat, ...PLAQUE_AT);
    const v = new THREE.Vector3(wx, 0.3, wz).project(this.camera);
    return { x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height, visible: v.z < 1 }; // off to the side: the overlay clamps it to the screen edge
  }

  /**
   * Screen boxes (CSS px, relative to the canvas) of the cards on the battlefields and of the piles
   * beside them (ids are card ids or "player:zone"), so DOM overlays
   * (seat plaques) can step out from over them.
   */
  battlefieldRects(width: number, height: number): ScreenRect[] {
    const out: ScreenRect[] = [];
    if (!this.view) return out;
    for (const c of this.cards.values()) {
      if (!this.view.cards[c.id]?.zone.endsWith(":battlefield")) continue;
      const r = this.cardRect(c.id, width, height);
      if (r) out.push(r);
    }
    // the piles beside each mat (library, graveyard, exile, command zone) count too
    for (const [key, p] of this.piles) out.push(this.rectOf(key, p.slot, width, height));
    return out;
  }

  /** One card's screen box (CSS px, relative to the canvas). */
  cardRect(id: string, width: number, height: number): ScreenRect | null {
    const c = this.cards.get(id);
    return c ? this.rectOf(id, c.face, width, height) : null;
  }

  private rectOf(id: string, obj: THREE.Object3D, width: number, height: number): ScreenRect {
    const box = this.tmpBox.setFromObject(obj);
    const v = this.tmpV;
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    for (let i = 0; i < 8; i++) {
      v.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).project(this.camera);
      const x = ((v.x + 1) / 2) * width;
      const y = ((1 - v.y) / 2) * height;
      left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
    }
    return { id, left, top, right, bottom };
  }
  private tmpBox = new THREE.Box3();
  private tmpV = new THREE.Vector3();

  /** Screen position (CSS px, relative to the canvas) of a card, or of a battlefield point of a seat. */
  screenOfCard(id: string): { x: number; y: number } | null {
    const c = this.cards.get(id);
    return c ? this.project(c.group.position) : null;
  }

  screenOfBattlefield(player: string, vx: number, vy: number): { x: number; y: number } | null {
    const seat = this.seatList.find((s) => s.player === player);
    if (!seat) return null;
    const [lx, lz] = virtualToLocal(vx, vy);
    const [wx, wz] = toWorld(seat, lx, lz);
    return this.project(new THREE.Vector3(wx, 0, wz));
  }

  private project(p: THREE.Vector3): { x: number; y: number } {
    const v = p.clone().project(this.camera);
    const r = this.canvas.getBoundingClientRect();
    return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height };
  }

  /** What a ping at this point points at: the card under the pointer, else the battlefield spot (game/ping.ts). */
  pingTargetAt(clientX: number, clientY: number): PingTarget | null {
    const hit = this.pick(clientX, clientY);
    if (hit?.card) return { card: hit.card };
    const drop = this.resolveDrop(clientX, clientY);
    if (drop?.zone.endsWith(":battlefield") && drop.x !== undefined && drop.y !== undefined) {
      return { player: drop.zone.split(":")[0]!, x: drop.x, y: drop.y };
    }
    return null;
  }

  /** Drop resolution for DOM drags (from the hand) over the canvas. */
  resolveDrop(clientX: number, clientY: number, offset?: THREE.Vector3): DropResult | null {
    const p = this.tablePoint(clientX, clientY);
    if (!p || !this.view) return null;
    if (offset) p.sub(offset);
    for (const seat of this.seatList) {
      const [lx, lz] = toLocal(seat, p.x, p.z);
      if (onBattlefield(lx, lz)) {
        const [x, y] = localToVirtual(lx, lz);
        return { zone: `${seat.player}:battlefield`, x, y };
      }
      const pile = pileAt(lx, lz);
      if (pile) return { zone: `${seat.player}:${pile}`, position: "top" };
    }
    // the stack: the middle of the aisle between the rows
    if (Math.abs(p.z) < AISLE + 0.3 && Math.abs(p.x) < 2.2 && this.stackCenterFree()) return { zone: "stack" };
    return null;
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    for (const u of this.unsubs) u();
    this.dice.dispose();
    this.clearTable();
    for (const c of this.cards.values()) this.disposeCard(c);
    this.cards.clear();
    for (const t of this.textures.values()) t.dispose();
    for (const m of this.materials.values()) m.dispose();
    this.bodies.dispose();
    this.shadows.geometry.dispose();
    (this.shadows.material as THREE.Material).dispose();
    this.shadows.dispose();
    this.shadowTex.dispose();
    this.cardFaceGeo.dispose();
    this.cardBodyGeo.dispose();
    this.glowGeo.dispose();
    this.bodyMat.dispose();
    this.post?.dispose();
    this.envMap.dispose();
    this.renderer.dispose();
    this.canvas.remove();
  }

  // ------------------------------------------------------------------ table & environment

  private applyFog(): void {
    const e = this.plane.env;
    // the room falls away into near-darkness so the lit table reads first
    const fog = new THREE.Color(e.fog).multiplyScalar(0.3);
    this.scene.fog = new THREE.Fog(fog, 30, 95 - e.fogDensity * 600);
    this.scene.background = new THREE.Color(e.skyBottom).multiplyScalar(0.35);
  }

  private clearTable(): void {
    if (this.env) {
      this.world.remove(this.env.group);
      this.env.dispose();
      this.env = null;
    }
    for (const m of this.mats.values()) {
      this.world.remove(m);
      m.geometry.dispose();
      (m.material as THREE.MeshBasicMaterial).map?.dispose();
      (m.material as THREE.Material).dispose();
    }
    this.mats.clear();
    for (const p of this.piles.values()) {
      this.world.remove(p.block, p.slot, p.layers);
      if (p.top) this.world.remove(p.top);
      p.layers.dispose();
      p.block.geometry.dispose();
      p.slot.geometry.dispose();
      (p.slot.material as THREE.MeshBasicMaterial).map?.dispose();
      (p.slot.material as THREE.Material).dispose();
    }
    this.piles.clear();
    for (const f of this.handFans.values()) this.world.remove(f);
    this.handFans.clear();
  }

  private rebuildTable(): void {
    if (!this.seatList.length) return;
    this.clearTable();
    const size = tableSize(this.seatList);
    this.env = buildEnvironment(this.plane, size, this.quality);
    this.world.add(this.env.group);
    const e = this.plane.env;
    for (const seat of this.seatList) {
      const color = this.view?.players.find((p) => p.id === seat.player)?.color ?? "#888";
      const mat = new THREE.Mesh(new THREE.PlaneGeometry(MAT_W + 0.5, MAT_D + 0.5), new THREE.MeshStandardMaterial({ map: matTexture(e.felt, e.feltNap, color), transparent: true, depthWrite: false, roughness: 1, envMapIntensity: 0.15, emissive: this.plane.ui.accent, emissiveIntensity: 0 }));
      mat.rotation.x = -Math.PI / 2;
      mat.rotation.z = seat.rot;
      const [mx, mz] = toWorld(seat, 0, 0);
      mat.position.set(mx, 0.002, mz);
      mat.receiveShadow = true;
      mat.userData = { mat: seat.player };
      this.world.add(mat);
      this.mats.set(seat.player, mat);
      for (const zone of Object.keys(PILES) as PileZone[]) {
        const [lx, lz] = PILES[zone];
        const [wx, wz] = toWorld(seat, lx, lz);
        const slot = new THREE.Mesh(new THREE.PlaneGeometry(CARD_W * 1.05, CARD_H * 1.05), new THREE.MeshBasicMaterial({ map: slotTexture(PILE_LABEL[zone as ZoneName] ?? zone, this.plane.ui.accent), transparent: true, depthWrite: false }));
        slot.rotation.x = -Math.PI / 2;
        slot.rotation.z = seat.rot;
        slot.position.set(wx, 0.003, wz);
        slot.userData = { pile: zone, player: seat.player };
        const block = new THREE.Mesh(new THREE.BoxGeometry(CARD_W, 1, CARD_H), this.hitMat);
        block.rotation.y = seat.rot;
        block.position.set(wx, 0, wz);
        block.visible = false;
        block.userData = { pile: zone, player: seat.player };
        const layers = new THREE.InstancedMesh(this.cardBodyGeo, this.bodyMat, PILE_LAYERS);
        layers.count = 0;
        layers.castShadow = layers.receiveShadow = this.quality !== "low";
        layers.userData = { pile: zone, player: seat.player };
        let top: THREE.Mesh | null = null;
        if (zone === "library") {
          top = new THREE.Mesh(this.cardFaceGeo, this.backMaterial(seat.player));
          top.receiveShadow = this.quality !== "low";
          top.visible = false;
          top.userData = { pile: zone, player: seat.player };
          this.world.add(top);
        }
        this.world.add(slot, block, layers);
        this.piles.set(`${seat.player}:${zone}`, { block, slot, layers, top, count: -1 });
      }
    }
  }

  // ------------------------------------------------------------------ textures & materials

  private backMaterial(owner: string): THREE.MeshStandardMaterial {
    const player = this.view?.players.find((p) => p.id === owner);
    const sleeve = player?.sleeve ? this.view?.game.assets?.[player.sleeve]?.url : undefined;
    const key = `back:${owner}:${sleeve ?? ""}:${player?.color ?? ""}`;
    let m = this.materials.get(key);
    if (!m) {
      const tex = sleeve ? this.loadTexture(sleeve, () => canvasTexture(backCanvas(player?.color ?? "#888"))) : canvasTexture(backCanvas(player?.color ?? "#888"));
      m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55 });
      this.materials.set(key, m);
    }
    return m;
  }

  private loadTexture(url: string, fallback: () => THREE.Texture): THREE.Texture {
    const cached = this.textures.get(url);
    if (cached) return cached;
    if (this.failed.has(url)) return fallback();
    const tex = this.loader.load(url, undefined, undefined, () => {
      this.failed.add(url);
      this.textures.delete(url);
      // swap every material using it for the fallback
      for (const [k, m] of this.materials) if (m.map === tex) { m.map = fallback(); m.needsUpdate = true; void k; }
    });
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    this.textures.set(url, tex);
    return tex;
  }

  private faceKeyFor(card: GameCard): string {
    if (!isVisible(card) || card.face_down) return `back:${card.owner}`;
    const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
    return `front:${card.card_id ?? card.name}:${card.face}:${data ? (data.has_image ? "img" : "txt") : "pending"}`;
  }

  private faceMaterial(card: GameCard, key: string): THREE.MeshStandardMaterial {
    if (key.startsWith("back:")) return this.backMaterial(card.owner);
    let m = this.materials.get(key);
    if (m) return m;
    const vis = card as Extract<GameCard, { hidden?: undefined }>;
    const data = vis.card_id ? useCardCache.getState().cards[vis.card_id] : undefined;
    const text = () => canvasTexture(textCardCanvas(data, vis.face ?? 0, vis.name));
    let tex: THREE.Texture;
    if (data?.has_image) {
      const imgFace = data.double_faced ? Math.min(vis.face ?? 0, data.image_faces - 1) : 0;
      tex = this.loadTexture(imageUrl(data.id, imgFace, this.quality === "low" ? "small" : "normal"), text);
    } else tex = text();
    // printed card stock with a faint satin sheen from the room reflections
    // matte card stock: a glossy face catches the overhead light and washes the art out
    m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0, envMapIntensity: 0.12 });
    this.materials.set(key, m);
    return m;
  }

  // ------------------------------------------------------------------ cards

  private makeCard(id: string): CardObj {
    const group = new THREE.Group();
    const face = new THREE.Mesh(this.cardFaceGeo, this.bodyMat);
    face.position.y = THICK + 0.0008;
    face.userData = { card: id };
    face.receiveShadow = this.quality !== "low";
    const glow = new THREE.Mesh(this.glowGeo, new THREE.MeshBasicMaterial({ color: "#fff", transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    glow.position.y = -0.001;
    group.add(glow, face);
    this.world.add(group);
    const obj: CardObj = { id, group, face, glow, overlay: null, overlayKey: "", faceKey: "", target: new THREE.Vector3(), rot: 0, tilt: 0, scale: 1, seen: true };
    this.cards.set(id, obj);
    return obj;
  }

  private disposeCard(c: CardObj): void {
    this.world.remove(c.group);
    (c.glow.material as THREE.Material).dispose();
    this.clearOverlay(c);
  }

  private clearOverlay(c: CardObj): void {
    if (!c.overlay) return;
    c.group.remove(c.overlay);
    const m = c.overlay.material as THREE.MeshBasicMaterial;
    m.map?.dispose();
    m.dispose();
    c.overlay = null;
  }

  /** Arena-style badges on the card face; rebuilt only when what they say changes. */
  private setOverlay(c: CardObj, o: CardOverlay | null): void {
    const key = o ? JSON.stringify(o) : "";
    if (c.overlayKey === key) return;
    c.overlayKey = key;
    this.clearOverlay(c);
    if (!o) return;
    const mat = new THREE.MeshBasicMaterial({
      map: canvasTexture(cardOverlayCanvas(o)), transparent: true, depthWrite: false, toneMapped: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    });
    const m = new THREE.Mesh(this.cardFaceGeo, mat);
    m.position.y = THICK + 0.0014;
    m.renderOrder = 2;
    c.group.add(m);
    c.overlay = m;
  }

  private place(c: CardObj, seat: Seat | undefined, lx: number, lz: number, y: number, extraRot = 0): void {
    c.scale = 1;
    if (seat) {
      const [wx, wz] = toWorld(seat, lx, lz);
      c.target.set(wx, y, wz);
      c.rot = seat.rot + extraRot;
    } else {
      c.target.set(lx, y, lz);
      c.rot = extraRot;
    }
  }

  private syncCards(): void {
    const view = this.view;
    if (!view) return;
    for (const c of this.cards.values()) c.seen = false;
    const seatOf = new Map(this.seatList.map((s) => [s.player, s]));
    const store = useGame.getState();
    const selection = new Set(store.selection);
    this.selectedIds = selection;
    const pending = store.pendingPositions;
    const need: string[] = [];
    const show = (id: string): CardObj | null => {
      const card = view.cards[id];
      if (!card) return null;
      const c = this.cards.get(id) ?? this.makeCard(id);
      c.seen = true;
      if (isVisible(card) && card.card_id && !useCardCache.getState().cards[card.card_id]) need.push(card.card_id);
      const key = this.faceKeyFor(card);
      if (key !== c.faceKey) {
        c.faceKey = key;
        c.face.material = this.faceMaterial(card, key);
      }
      return c;
    };

    for (const seat of this.seatList) {
      const pid = seat.player;
      // battlefield
      const bf = (view.zones[`${pid}:battlefield`] as string[] | undefined) ?? [];
      const piles = zonePileTops(view, `${pid}:battlefield`);
      bf.forEach((id, i) => {
        const card = view.cards[id];
        const c = show(id);
        if (!card || !c) return;
        const pos = pending[id] ?? [card.x ?? 20 + (i % 10) * 90, card.y ?? 20 + Math.floor(i / 10) * 130];
        const [lx, lz] = virtualToLocal(pos[0], pos[1]);
        const tapped = (card.tapped ? -Math.PI / 2 : 0) + (card.flipped ? Math.PI : 0) - ((card.rotation ?? 0) * Math.PI) / 180;
        this.place(c, seat, lx, lz, 0.004 + i * 0.0035, tapped);
        c.tilt = 0;
        const overlay = overlayFor(card, view.rules?.stats?.[id]);
        const pile = piles.get(id);
        const ownerP = card.owner !== card.controller ? view.players.find((p) => p.id === card.owner) : undefined;
        const owner = ownerP ? { initial: ownerP.name.slice(0, 1).toUpperCase(), color: ownerP.color } : undefined;
        this.setOverlay(c, pile || owner ? { ...(overlay ?? { keywords: [], counters: [] }), ...(pile ? { pile } : {}), ...(owner ? { owner } : {}) } : overlay);
        this.setGlow(c, selection.has(id) ? this.plane.ui.frameHi : this.legalColor(view, id), selection.has(id) ? 0.9 : 0.55); // brass: the selected card's edge (DESIGN.md); ice means priority
      });
      // piles
      for (const zone of ["library", "graveyard", "exile"] as const) {
        const z = view.zones[`${pid}:${zone}`];
        const count = Array.isArray(z) ? z.length : (z as LibraryView | undefined)?.count ?? 0;
        const pile = this.piles.get(`${pid}:${zone}`);
        if (pile && pile.count !== count) {
          pile.count = count;
          // graveyard and exile draw their top card for real, so the stack below has one fewer
          this.stackPile(seat, zone, pile, zone === "library" ? count : Math.max(0, count - 1));
        }
        if (zone !== "library" && Array.isArray(z) && z.length) {
          const top = z[z.length - 1]!;
          const c = show(top);
          if (c && seat) {
            const [lx, lz] = PILES[zone];
            this.place(c, seat, lx, lz, pileHeight(z.length - 1) + 0.002, 0);
            this.setOverlay(c, null);
            this.setGlow(c, selection.has(top) ? this.plane.ui.select : null, 0.9);
          }
        }
      }
      // command zone
      const cmd = (view.zones[`${pid}:command`] as string[] | undefined) ?? [];
      cmd.forEach((id, i) => {
        const c = show(id);
        if (!c) return;
        const [lx, lz] = PILES.command;
        this.place(c, seat, lx - i * (CARD_W + 0.12), lz, 0.004, 0);
        this.setOverlay(c, null);
        this.setGlow(c, selection.has(id) ? this.plane.ui.frameHi : this.legalColor(view, id), 0.6);
      });
      // other players' hands: a fan of backs at their edge (count only)
      if (pid !== this.me) this.syncHandFan(seat, ((view.zones[`${pid}:hand`] as string[] | undefined) ?? []).length);
    }

    // the stack: cards hover above the centre of the table, most recent on top
    // the stack: large cards standing at the table centre, fanned left to right in cast order (the
    // chain), facing me; the top one stands biggest and highest and says it resolves next
    const n = view.stack.length;
    const myRot = seatOf.get(this.me)?.rot ?? 0;
    const step = Math.min(1.8, 8 / Math.max(1, n));
    this.stackBox = null;
    this.stackAnchors.clear();
    const grow = (x: number, z: number, r: number) => {
      const b = this.stackBox ?? { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity };
      this.stackBox = { minX: Math.min(b.minX, x - r), maxX: Math.max(b.maxX, x + r), minZ: Math.min(b.minZ, z - r), maxZ: Math.max(b.maxZ, z + r) };
    };
    // toward my side of the centre, so the standing cards don't hide the far player's front row
    const nearMe = 1.6;
    view.stack.forEach((id, i) => {
      const c = show(id);
      if (!c) return;
      const top = i === n - 1;
      const x = (i - (n - 1) / 2) * step;
      const z = nearMe + (top ? 0.15 : 0);
      const wx = x * Math.cos(myRot) + z * Math.sin(myRot);
      const wz = -x * Math.sin(myRot) + z * Math.cos(myRot);
      const scale = top ? 2.25 : 1.85;
      const tilt = 0.75; // far edge up: the face turns toward my seat
      const y = (top ? 1.45 : 1.3) + i * 0.02;
      this.place(c, undefined, wx, wz, y, myRot);
      c.scale = scale;
      grow(wx, wz, (CARD_H / 2) * scale + 0.45);
      // beams to or from a stack card leave from its raised top edge, never from inside it
      const half = (CARD_H / 2) * scale;
      const along = half * Math.cos(tilt);
      const rise = half * Math.sin(tilt);
      this.stackAnchors.set(id, {
        far: new THREE.Vector3(wx - Math.sin(myRot) * along, y + rise + 0.08, wz - Math.cos(myRot) * along),
        near: new THREE.Vector3(wx + Math.sin(myRot) * along, Math.max(0.1, y - rise - 0.05), wz + Math.cos(myRot) * along),
      });
      c.tilt = tilt;
      this.setOverlay(c, { keywords: [], counters: [], chain: { no: i + 1, next: top } });
      this.setGlow(c, selection.has(id) ? this.plane.ui.select : top ? this.plane.ui.accent : null, top ? 0.6 : 0.5);
    });

    for (const [id, c] of this.cards) {
      if (!c.seen) {
        this.disposeCard(c);
        this.cards.delete(id);
      }
    }
    if (need.length) requestCards(need);
    this.stats.cards = this.cards.size;
    // a refused action's card glows red for a moment (static: no motion to reduce)
    const err = store.errorCard;
    const errObj = err && Date.now() - err.at < ERROR_MS ? this.cards.get(err.id) : undefined;
    if (errObj) this.setGlow(errObj, "#ff5a4a", 1);
    this.layoutCombat(view);
    this.syncArrows(view);
  }

  /**
   * Combat as a formation (presentation only; stored positions never change): each attacker marches
   * out into the open wood beyond its mat, side by side with the others attacking the same player
   * and facing them; each blocker steps up directly in front of the attacker it blocks.
   */
  private layoutCombat(view: GameView): void {
    const seatOf = (pid: string | undefined) => this.seatList.find((s) => s.player === pid);
    const groups = new Map<string, { a: Seat; d: Seat; ids: string[] }>();
    for (const card of Object.values(view.cards)) {
      if (!card.attacking || !card.zone.endsWith(":battlefield")) continue;
      const a = seatOf(card.controller);
      const d = seatOf(card.attacking.kind === "player" ? card.attacking.id : view.cards[card.attacking.id]?.controller);
      if (!a || !d || a === d) continue;
      const key = `${a.player}>${d.player}`;
      const g = groups.get(key) ?? { a, d, ids: [] };
      g.ids.push(card.id);
      groups.set(key, g);
    }
    const blockers = Object.values(view.cards).filter((b) => b.blocking && b.zone.endsWith(":battlefield"));
    for (const { a, d, ids } of groups.values()) {
      const dx = d.x - a.x;
      const dz = d.z - a.z;
      const len = Math.hypot(dx, dz) || 1;
      const [ux, uz] = [dx / len, dz / len];
      const [px, pz] = [-uz, ux];
      const out = MAT_D / 2 + 1.4; // just past the attacker's mat edge, into the open wood
      ids.forEach((id, i) => {
        const c = this.cards.get(id);
        if (!c) return;
        const off = (i - (ids.length - 1) / 2) * CARD_H * 1.15; // tapped attackers lie sideways
        const x = a.x + ux * out + px * off;
        const z = a.z + uz * out + pz * off;
        c.target.set(x, c.target.y + 0.04, z);
        blockers.filter((b) => b.blocking === id).forEach((b, j, all) => {
          const bc = this.cards.get(b.id);
          if (!bc) return;
          const side = (j - (all.length - 1) / 2) * CARD_W * 1.1;
          bc.target.set(x + ux * CARD_H * 1.3 + px * side, bc.target.y + 0.04, z + uz * CARD_H * 1.3 + pz * side);
          bc.rot = d.rot + (b.tapped ? -Math.PI / 2 : 0);
        });
      });
    }
  }

  /**
   * Attack, block and targeting arrows: a lit shaft arcing over the table with a dark outline (so
   * it reads over pale cards) and a broad arrowhead. Rebuilt only when an arrow changes.
   */
  private syncArrows(view: GameView): void {
    const at = (id: string, from?: THREE.Vector3): THREE.Vector3 | null => {
      const c = this.cards.get(id);
      if (c) return c.target.clone().setY(c.target.y + 0.05);
      const seat = this.seatList.find((s) => s.player === id);
      if (!seat) return null;
      // a player: their plaque (as Arena lands on the avatar), spread a little so several
      // attackers' crystals sit side by side
      const spread = from ? Math.max(-0.7, Math.min(0.7, toLocal(seat, from.x, from.z)[0] * 0.12)) : 0;
      const [wx, wz] = toWorld(seat, PLAQUE_AT[0] + spread, PLAQUE_AT[1]);
      const p = new THREE.Vector3(wx, 0.3, wz);
      // stop short of the plaque so the crystal stays clear of its Turn / Priority flags
      if (from) p.add(from.clone().setY(0.3).sub(p).setLength(Math.min(1.1, from.distanceTo(p) * 0.3)));
      return p;
    };
    const wanted: [THREE.Vector3, THREE.Vector3, string][] = [];
    // a stack card's beam leaves from the edge that faces its other end, so it never crosses the face
    const edge = (id: string, toward: THREE.Vector3): THREE.Vector3 | null => {
      const e = this.stackAnchors.get(id);
      if (!e) return null;
      const d = (p: THREE.Vector3) => Math.hypot(p.x - toward.x, p.z - toward.z);
      return (d(e.near) < d(e.far) ? e.near : e.far).clone();
    };
    const add = (from: string, to: string, color: string, low = false) => {
      const a0 = at(from);
      const b0 = a0 && at(to, a0);
      if (!a0 || !b0) return;
      const a = edge(from, b0) ?? a0;
      const b = edge(to, a) ?? b0;
      if (a.distanceTo(b) >= 0.3) wanted.push([a, b, low ? `${color}|low` : color]);
    };
    for (const c of Object.values(view.cards)) {
      if (c.attacking && c.attacking.kind !== "player") add(c.id, c.attacking.id, ATTACK_RED, true);
      if (c.blocking) for (const t of [c.blocking, ...(c.blocking_more ?? [])]) add(c.id, t, "#5fa8ff", true);
    }
    for (const ar of view.arrows ?? []) {
      const color = ar.kind === "attack" ? ATTACK_RED : ar.kind === "block" ? "#5fa8ff" : ar.kind === "target" ? this.plane.ui.select : this.plane.ui.accent;
      for (const t of ar.targets) add(ar.source, t, color);
    }
    // the stack's layout is part of the key: casting a spell reroutes beams that cross the centre
    const key = `${view.stack.join(",")}#` + wanted.map(([a, b, c]) => `${a.x.toFixed(2)},${a.y.toFixed(2)},${a.z.toFixed(2)}>${b.x.toFixed(2)},${b.z.toFixed(2)}${c}`).join("|");
    this.stats.arrows = wanted.length;
    if (key === this.arrowKey) return;
    this.arrowKey = key;
    for (const child of [...this.arrows.children]) {
      this.arrows.remove(child);
      (child.userData.dispose as () => void)();
    }
    const flow = !document.body.classList.contains("reduced-motion");
    for (const [a, b, c] of wanted) {
      const [color, low] = c.split("|");
      this.arrows.add(makeArrow(a, b, { color: color!, flow, low: !!low }, this.stackBox));
    }
  }

  private syncHandFan(seat: Seat, count: number): void {
    let fan = this.handFans.get(seat.player);
    if (fan && fan.userData.count === count) return;
    if (fan) this.world.remove(fan);
    fan = new THREE.Group();
    fan.userData.count = count;
    const shown = Math.min(count, 12);
    const mat = this.backMaterial(seat.player);
    for (let i = 0; i < shown; i++) {
      const m = new THREE.Mesh(this.cardFaceGeo, mat);
      const t = shown === 1 ? 0 : i / (shown - 1) - 0.5;
      m.position.set(t * Math.min(3.2, shown * 0.35), 0.02 + i * 0.004, Math.abs(t) * 0.3);
      m.rotation.y = -t * 0.5;
      fan.add(m);
    }
    const [wx, wz] = toWorld(seat, 0, MAT_D / 2 + 1.25);
    fan.position.set(wx, 0, wz);
    fan.rotation.y = seat.rot + Math.PI;
    this.world.add(fan);
    this.handFans.set(seat.player, fan);
  }

  /** Lay out a pile's card bodies (and the library's top back) for n cards. */
  private stackPile(seat: Seat, zone: PileZone, pile: PileObj, n: number): void {
    const [lx, lz] = PILES[zone];
    const [wx, wz] = toWorld(seat, lx, lz);
    const h = pileHeight(n);
    const shown = Math.min(n, PILE_LAYERS);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const one = new THREE.Vector3(1, 1, 1);
    const salt = zone.length + seat.rot;
    for (let i = 0; i < shown; i++) {
      const y = shown <= 1 ? 0 : (i / shown) * h;
      q.setFromAxisAngle(up, seat.rot + jitter(i, salt) * 0.035);
      m.compose(new THREE.Vector3(wx + jitter(i, salt + 1) * 0.02, y, wz + jitter(i, salt + 2) * 0.02), q, one);
      pile.layers.setMatrixAt(i, m);
    }
    pile.layers.count = shown;
    pile.layers.instanceMatrix.needsUpdate = true;
    pile.layers.computeBoundingSphere();
    pile.block.scale.y = Math.max(0.06, h + THICK);
    pile.block.position.y = pile.block.scale.y / 2;
    if (pile.top) {
      pile.top.visible = n > 0;
      pile.top.position.set(wx, (shown <= 1 ? 0 : ((shown - 1) / shown) * h) + THICK + 0.0008, wz);
      pile.top.rotation.y = seat.rot;
    }
  }

  private legalColor(view: GameView, id: string): string | null {
    const cls = legalClass(view, id, this.me);
    if (cls === "rules-target") return this.plane.ui.select;
    if (cls === "rules-playable" || cls === "rules-activatable") return this.plane.ui.accent;
    return null;
  }

  private setGlow(c: CardObj, color: string | null, opacity: number): void {
    const m = c.glow.material as THREE.MeshBasicMaterial;
    c.glow.visible = !!color;
    if (color) {
      m.color.set(color);
      m.opacity = opacity;
    }
  }

  private stackCenterFree(): boolean {
    return true;
  }

  // ------------------------------------------------------------------ camera

  private updateCameraGoal(): void {
    const mine = this.seatList.find((s) => s.player === this.me) ?? this.seatList[0];
    if (!mine) return;
    const size = tableSize(this.seatList);
    const aspect = this.camera.aspect || 16 / 9;
    const span = Math.max(size.w / Math.max(aspect, 1), size.d);
    const preset = this.preset;
    let pos: THREE.Vector3;
    let look: THREE.Vector3;
    if (preset === "overview") {
      // straight down the table, as the scripted tables' overhead camera: every mat whole, with room for
      // the top bar and the hand
      look = new THREE.Vector3(0, 0, 0.3);
      pos = new THREE.Vector3(0, span * 1.74, span * 0.3);
    } else if (typeof preset === "object" && "card" in preset) {
      // close up on one card, seen from my side of the table
      const c = this.cards.get(preset.card);
      look = c ? c.target.clone().setY(0) : new THREE.Vector3();
      const [dx, dz] = toWorld({ ...mine, x: 0, z: 0 }, 0, 1);
      pos = look.clone().add(new THREE.Vector3(dx * 2.6, 5.2, dz * 2.6));
    } else if (typeof preset === "object") {
      const seat = this.seatList.find((s) => s.player === preset.focus) ?? mine;
      const [lx, lz] = toWorld(seat, 0, -0.3);
      const [px, pz] = toWorld(seat, 0, MAT_D / 2 + 5.2);
      look = new THREE.Vector3(lx, 0, lz);
      pos = new THREE.Vector3(px, 8.5, pz);
    } else {
      // behind my seat, looking across the aisle (the main view): my mat large, the far row whole. The
      // camera leans toward the table's middle when my seat is off-centre, as you would at a long table.
      const reach = Math.max((size.w / aspect) * 1.45, size.d);
      look = new THREE.Vector3(mine.x * 0.25, 0, -AISLE - 1.2);
      pos = new THREE.Vector3(mine.x * 0.35, reach * 0.66, mine.z + MAT_D / 2 + reach * 0.26);
    }
    const off = pos.clone().sub(look).multiplyScalar(this.zoom);
    off.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw);
    this.camGoalPos.copy(look).add(off);
    this.camGoalLook.copy(look);
  }

  // ------------------------------------------------------------------ input

  private pointer(clientX: number, clientY: number): THREE.Vector2 {
    const r = this.canvas.getBoundingClientRect();
    return new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
  }

  private tablePoint(clientX: number, clientY: number): THREE.Vector3 | null {
    this.ray.setFromCamera(this.pointer(clientX, clientY), this.camera);
    const out = new THREE.Vector3();
    return this.ray.ray.intersectPlane(this.tablePlane, out);
  }

  private pick(clientX: number, clientY: number): { card?: string; pile?: PileZone; player?: string } | null {
    this.ray.setFromCamera(this.pointer(clientX, clientY), this.camera);
    const targets: THREE.Object3D[] = [];
    for (const c of this.cards.values()) if (!this.drag?.ids.includes(c.id)) targets.push(c.face);
    for (const p of this.piles.values()) targets.push(p.block, p.slot, ...(p.top?.visible ? [p.top] : []));
    const hits = this.ray.intersectObjects(targets, false);
    const hit = hits[0];
    if (!hit) return null;
    const d = hit.object.userData as { card?: string; pile?: PileZone; player?: string };
    return d;
  }

  private bindInput(): void {
    const cv = this.canvas;
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (e: HTMLElementEventMap[K]) => void, opts?: AddEventListenerOptions) => {
      cv.addEventListener(type, fn as EventListener, opts);
      this.unsubs.push(() => cv.removeEventListener(type, fn as EventListener));
    };
    on("pointerdown", (e) => this.onDown(e));
    on("pointermove", (e) => this.onMove(e));
    on("pointerup", (e) => this.onUp(e));
    on("pointerleave", () => this.setHover(null));
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !this.drag?.active) return;
      // Esc puts dragged cards back where they were; nothing is sent
      e.stopPropagation();
      this.drag = null;
      document.body.classList.remove("dragging");
      this.syncCards();
    };
    window.addEventListener("keydown", onKey, true);
    this.unsubs.push(() => window.removeEventListener("keydown", onKey, true));
    on("contextmenu", (e) => this.onContext(e));
    on("wheel", (e) => {
      e.preventDefault();
      this.zoom = Math.max(0.45, Math.min(1.8, this.zoom * (e.deltaY > 0 ? 1.08 : 1 / 1.08)));
      this.updateCameraGoal();
    }, { passive: false });
  }

  private setHover(id: string | null): void {
    if (this.hovered === id) return;
    this.hovered = id;
    const s = useGame.getState();
    if (id) s.setHover(id);
    else if (s.hover && this.cards.has(s.hover)) s.setHover(null);
    this.canvas.style.cursor = id ? "pointer" : "";
  }

  private onDown(e: PointerEvent): void {
    if (e.button === 1) {
      e.preventDefault();
      this.orbit = { x: e.clientX, yaw: this.yaw };
      this.canvas.setPointerCapture(e.pointerId);
      return;
    }
    if (e.button !== 0) return;
    const hit = this.pick(e.clientX, e.clientY);
    const store = useGame.getState();
    if (!hit?.card) {
      if (!hit && !e.shiftKey) store.clearSelection();
      if (hit?.pile && hit.player) this.clickPile(hit.player, hit.pile, e);
      if (!hit && !store.pick) {
        const el = document.createElement("div");
        el.className = "marquee";
        el.hidden = true;
        this.canvas.parentElement?.append(el);
        this.marquee = { x0: e.clientX, y0: e.clientY, add: e.shiftKey, el };
        this.canvas.setPointerCapture(e.pointerId);
      }
      return;
    }
    const id = hit.card;
    if (store.pick) {
      pickClick(id);
      return;
    }
    if (legalClass(store.view, id, this.me) === "rules-target" && answerByClick(store.view, id, this.me)) return;
    const now = performance.now();
    if (this.lastClick.id === id && now - this.lastClick.at < 320) {
      this.lastClick = { id: "", at: 0 };
      const card = store.view?.cards[id];
      if (card?.zone.endsWith(":battlefield")) tapGesture(targetsFor(id), (x) => void tapCards(x));
      return;
    }
    this.lastClick = { id, at: now };
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      store.select([id], "toggle");
      return;
    }
    if (!store.selection.includes(id)) store.select([id]);
    const ids = targetsFor(id);
    const grab = this.tablePoint(e.clientX, e.clientY) ?? new THREE.Vector3();
    const offsets = new Map<string, THREE.Vector3>();
    for (const cid of ids) {
      const c = this.cards.get(cid);
      if (c) offsets.set(cid, c.group.position.clone().setY(0).sub(grab));
    }
    this.drag = { ids, anchor: id, start: [e.clientX, e.clientY], grab, offsets, active: false };
    this.canvas.setPointerCapture(e.pointerId);
  }

  private onMove(e: PointerEvent): void {
    if (this.orbit) {
      this.yaw = this.orbit.yaw - (e.clientX - this.orbit.x) * 0.006;
      this.updateCameraGoal();
      return;
    }
    const m = this.marquee;
    if (m) {
      const r = this.canvas.getBoundingClientRect();
      Object.assign(m.el.style, {
        left: `${Math.min(m.x0, e.clientX) - r.left}px`, top: `${Math.min(m.y0, e.clientY) - r.top}px`,
        width: `${Math.abs(e.clientX - m.x0)}px`, height: `${Math.abs(e.clientY - m.y0)}px`,
      });
      m.el.hidden = false;
      return;
    }
    const d = this.drag;
    if (d) {
      if (!d.active && Math.hypot(e.clientX - d.start[0], e.clientY - d.start[1]) < 5) return;
      d.active = true;
      document.body.classList.add("dragging");
      const p = this.tablePoint(e.clientX, e.clientY);
      if (!p) return;
      for (const cid of d.ids) {
        const c = this.cards.get(cid);
        const off = d.offsets.get(cid);
        if (c && off) c.target.set(p.x + off.x, LIFT, p.z + off.z);
      }
      return;
    }
    const hit = this.pick(e.clientX, e.clientY);
    this.setHover(hit?.card ?? null);
  }

  private onUp(e: PointerEvent): void {
    if (this.orbit) {
      this.orbit = null;
      return;
    }
    const m = this.marquee;
    if (m) {
      this.marquee = null;
      m.el.remove();
      const r = this.canvas.getBoundingClientRect();
      const [x0, x1] = [Math.min(m.x0, e.clientX) - r.left, Math.max(m.x0, e.clientX) - r.left];
      const [y0, y1] = [Math.min(m.y0, e.clientY) - r.top, Math.max(m.y0, e.clientY) - r.top];
      if (x1 - x0 < 4 && y1 - y0 < 4) return;
      const ids = this.battlefieldRects(r.width, r.height).filter((b) => this.cards.has(b.id) && b.left < x1 && b.right > x0 && b.top < y1 && b.bottom > y0).map((b) => b.id);
      useGame.getState().select(ids, m.add ? "add" : "replace");
      return;
    }
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    document.body.classList.remove("dragging");
    if (!d.active) return;
    const anchorOff = d.offsets.get(d.anchor);
    const target = this.resolveDrop(e.clientX, e.clientY, anchorOff ? anchorOff.clone().negate() : undefined);
    if (target) dropCards(d.ids, d.anchor, { ...target, manual: e.altKey });
    else toast("Dropped off the table: nothing changed", "info");
    this.syncCards(); // snap back (or to the pending position) until the server answers
  }

  private clickPile(player: string, pile: PileZone, e: PointerEvent): void {
    const store = useGame.getState();
    const view = store.view;
    if (!view) return;
    if (pile === "library") {
      const now = performance.now();
      if (this.lastClick.id === `lib:${player}` && now - this.lastClick.at < 320 && player === this.me) {
        void draw(this.me, 1);
        this.lastClick = { id: "", at: 0 };
      } else this.lastClick = { id: `lib:${player}`, at: now };
      void e;
      return;
    }
    store.openBrowser({ zone: `${player}:${pile}`, title: PILE_LABEL[pile as ZoneName] ?? pile });
  }

  private onContext(e: MouseEvent): void {
    e.preventDefault();
    const hit = this.pick(e.clientX, e.clientY);
    const store = useGame.getState();
    const view = store.view;
    if (!view) return;
    const fake = { clientX: e.clientX, clientY: e.clientY, preventDefault() {}, stopPropagation() {} } as unknown as React.MouseEvent;
    if (!hit) {
      openMenu(fake, tableMenu(), "Table"); // the table's own actions, as in Tabletop Simulator
      return;
    }
    if (hit.card) {
      const card = view.cards[hit.card];
      if (!card) return;
      if (!store.selection.includes(hit.card)) store.select([hit.card]);
      const { title, items } = cardMenu(card, view, this.me);
      openMenu(fake, items, title);
      return;
    }
    if (hit.pile && hit.player) {
      const name = view.players.find((p) => p.id === hit.player)?.name ?? "";
      if (hit.pile === "library") openMenu(fake, libraryMenu(hit.player, this.me, name), `${name}'s library`);
      else if (hit.pile !== "command") {
        const ids = (view.zones[`${hit.player}:${hit.pile}`] as string[] | undefined) ?? [];
        openMenu(fake, pileMenu(hit.player, hit.pile as ZoneName, ids), PILE_LABEL[hit.pile as ZoneName] ?? hit.pile);
      }
    }
  }

  // ------------------------------------------------------------------ frame loop

  private loop = (): void => {
    this.raf = requestAnimationFrame(this.loop);
    const started = performance.now();
    const dt = Math.min(0.5, this.clock.getDelta()); // real time: slow devices still settle quickly
    const t = this.clock.elapsedTime;
    const reduced = document.body.classList.contains("reduced-motion");
    // empty pile outlines stay faint until a drag needs them as drop targets
    const anyDrag = document.body.classList.contains("dragging");
    for (const p of this.piles.values()) {
      const m = p.slot.material as THREE.MeshBasicMaterial;
      m.opacity = p.count > 0 || anyDrag ? 1 : 0.35;
    }
    // while a card is dragged, the battlefields (where it can land) light up
    // (with the rules engine on, only your own: the engine refuses the others)
    const rulesOn = !!this.view?.rules;
    for (const [pid, mat] of this.mats) {
      const m = mat.material as THREE.MeshStandardMaterial;
      m.emissiveIntensity = anyDrag && (!rulesOn || pid === this.me) ? 0.18 : 0;
    }
    // the player's animation speed (Settings) scales every 3D motion
    const speed = usePrefs.getState().animationSpeed || 1;
    const k = ease(dt, 14 * speed, reduced);
    const dragging = !!this.drag?.active;
    let n = 0;
    for (const c of this.cards.values()) {
      // hovered and selected cards ride a little higher, and a tap lifts the card as it turns
      const lift = liftFor({ hovered: c.id === this.hovered && !dragging, selected: this.selectedIds.has(c.id), turning: reduced ? 0 : angleDelta(c.group.rotation.y, c.rot) });
      liftTarget.copy(c.target);
      liftTarget.y += lift;
      c.group.position.lerp(liftTarget, k);
      c.group.rotation.y = angleLerp(c.group.rotation.y, c.rot, k);
      c.group.rotation.x += (c.tilt - c.group.rotation.x) * k;
      const sc = c.group.scale.x + (c.scale - c.group.scale.x) * k;
      c.group.scale.setScalar(sc);
      if (n < 1024) {
        c.group.updateMatrix();
        this.bodies.setMatrixAt(n, c.group.matrix);
        // the shadow sits on the table, offset away from the key light and softer as the card rises
        const lift = Math.max(0, c.group.position.y);
        const spread = (1 + Math.min(lift, 1.2) * 0.55) * c.group.scale.x;
        shadowPos.set(c.group.position.x + 0.05 + lift * 0.2, 0.0025, c.group.position.z + 0.08 + lift * 0.3);
        shadowQ.setFromAxisAngle(UP, c.group.rotation.y);
        shadowScale.set(spread, 1, spread);
        shadowM.compose(shadowPos, shadowQ, shadowScale);
        this.shadows.setMatrixAt(n, shadowM);
        const strength = 1 / (1 + lift * 2.5);
        shadowColor.setRGB(strength, strength, strength);
        this.shadows.setColorAt(n++, shadowColor);
      }
    }
    this.bodies.count = n;
    this.bodies.instanceMatrix.needsUpdate = true;
    this.shadows.count = n;
    this.shadows.instanceMatrix.needsUpdate = true;
    if (this.shadows.instanceColor) this.shadows.instanceColor.needsUpdate = true;
    this.dice.update(performance.now(), reduced, speed);
    const kc = ease(dt, 5 * speed, reduced);
    this.camPos.lerp(this.camGoalPos, kc);
    this.camLook.lerp(this.camGoalLook, kc);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camLook);
    if (!reduced) {
      // candle flicker, drifting dust and flowing beams only when motion is welcome
      this.env?.update(t);
      arrowTime.value = t;
    }
    this.renderer.info.reset();
    if (this.post) this.post.render();
    else this.renderer.render(this.scene, this.camera);
    this.onFrame?.();
    this.frameTime += performance.now() - started;
    this.frames++;
    if (t - this.fpsAt >= 1) {
      this.stats = { ...this.stats, fps: Math.round(this.frames / (t - this.fpsAt)), calls: this.renderer.info.render.calls, triangles: this.renderer.info.render.triangles, cards: this.cards.size, frameMs: Math.round((this.frameTime / Math.max(1, this.frames)) * 100) / 100 };
      this.frames = 0;
      this.frameTime = 0;
      this.fpsAt = t;
    }
  };
}
