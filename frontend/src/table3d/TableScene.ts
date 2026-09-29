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
import { imageUrl } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { isVisible, type GameCard, type GameView, type LibraryView, type ZoneName } from "../types/game";
import { draw, tapCards, targetsFor } from "../game/actions";
import { cardMenu } from "../game/cardMenu";
import type { DropResult } from "../game/dnd";
import { dropCards } from "../game/drop";
import { pickClick } from "../game/Overlays";
import { answerByClick, legalClass } from "../game/rules/RulesHud";
import { libraryMenu, pileMenu, PILE_LABEL } from "../game/ZonePile";
import type { PlaneTheme } from "../theme/planes";
import { buildEnvironment, type Environment } from "./environment";
import {
  CARD_H, CARD_W, MAT_D, MAT_W, PILES, STRIP_X, localToVirtual, onBattlefield, pileAt, seats, tableSize, toLocal, toWorld,
  virtualToLocal, type PileZone, type Seat,
} from "./layout";
import { backCanvas, canvasTexture, labelCanvas, matTexture, slotTexture, textCardCanvas } from "./textures";

export type Quality = "low" | "medium" | "high";
export type CameraPreset = "seat" | "overview" | { focus: string };

const THICK = 0.014;
const LIFT = 0.55;

interface CardObj {
  id: string;
  group: THREE.Group;
  face: THREE.Mesh;
  glow: THREE.Mesh;
  badge: THREE.Sprite | null;
  badgeText: string;
  faceKey: string;
  target: THREE.Vector3;
  rot: number;
  tilt: number;
  seen: boolean;
}

interface PileObj {
  block: THREE.Mesh;
  slot: THREE.Mesh;
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

function angleLerp(a: number, b: number, t: number): number {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

export interface SceneStats { fps: number; calls: number; triangles: number; cards: number; arrows?: number }

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
  private hovered: string | null = null;
  private lastClick = { id: "", at: 0 };
  private frames = 0;
  private fpsAt = 0;
  stats: SceneStats = { fps: 0, calls: 0, triangles: 0, cards: 0 };

  private cardFaceGeo = flatCardGeometry(CARD_W, CARD_H, 0.05);
  private cardBodyGeo: THREE.ExtrudeGeometry;
  private glowGeo = flatCardGeometry(CARD_W + 0.12, CARD_H + 0.12, 0.09);
  private bodyMat = new THREE.MeshStandardMaterial({ color: "#111", roughness: 0.6 });
  private textures = new Map<string, THREE.Texture>();
  private materials = new Map<string, THREE.MeshStandardMaterial>();
  private loader = new THREE.TextureLoader();
  private failed = new Set<string>();
  private unsubs: (() => void)[] = [];
  /** Every card's body (its thickness and shadow) in one draw call. */
  private bodies: THREE.InstancedMesh;
  private arrows = new THREE.Group();

  constructor(container: HTMLElement, plane: PlaneTheme, quality: Quality) {
    this.plane = plane;
    this.quality = quality;
    this.renderer = new THREE.WebGLRenderer({ antialias: quality !== "low", powerPreference: "high-performance", preserveDrawingBuffer: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === "high" ? 2 : quality === "medium" ? 1.5 : 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.35;
    this.renderer.shadowMap.enabled = quality !== "low";
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.canvas = this.renderer.domElement;
    this.canvas.className = "table3d-canvas";
    this.canvas.dataset.drop3d = "";
    container.appendChild(this.canvas);
    const body = new THREE.ExtrudeGeometry(roundedRect(CARD_W, CARD_H, 0.05), { depth: THICK, bevelEnabled: false, curveSegments: 6 });
    body.rotateX(-Math.PI / 2);
    this.cardBodyGeo = body;
    this.bodies = new THREE.InstancedMesh(body, this.bodyMat, 1024);
    this.bodies.castShadow = quality !== "low";
    this.bodies.count = 0;
    this.bodies.frustumCulled = false;
    this.world.add(this.bodies, this.arrows);
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
    this.camera.aspect = w / Math.max(1, h);
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

  /** Where a seat's player plate should be drawn on screen (for the DOM overlay). */
  seatScreen(player: string, width: number, height: number): { x: number; y: number; visible: boolean } | null {
    const seat = this.seatList.find((s) => s.player === player);
    if (!seat) return null;
    const [wx, wz] = toWorld(seat, -STRIP_X, -0.6);
    const v = new THREE.Vector3(wx, 0.3, wz).project(this.camera);
    return { x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height, visible: v.z < 1 && Math.abs(v.x) < 1.3 && Math.abs(v.y) < 1.3 };
  }

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

  /** Drop resolution for DOM drags (from the hand) over the canvas. */
  resolveDrop(clientX: number, clientY: number, offset?: THREE.Vector3): DropResult | null {
    const p = this.tablePoint(clientX, clientY);
    if (!p || !this.view) return null;
    if (offset) p.sub(offset);
    if (Math.hypot(p.x, p.z) < 1.8 && this.stackCenterFree()) return { zone: "stack" };
    for (const seat of this.seatList) {
      const [lx, lz] = toLocal(seat, p.x, p.z);
      if (onBattlefield(lx, lz)) {
        const [x, y] = localToVirtual(lx, lz);
        return { zone: `${seat.player}:battlefield`, x, y };
      }
      const pile = pileAt(lx, lz);
      if (pile) return { zone: `${seat.player}:${pile}`, position: "top" };
    }
    return null;
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    for (const u of this.unsubs) u();
    this.clearTable();
    for (const c of this.cards.values()) this.disposeCard(c);
    this.cards.clear();
    for (const t of this.textures.values()) t.dispose();
    for (const m of this.materials.values()) m.dispose();
    this.bodies.dispose();
    this.cardFaceGeo.dispose();
    this.cardBodyGeo.dispose();
    this.glowGeo.dispose();
    this.bodyMat.dispose();
    this.renderer.dispose();
    this.canvas.remove();
  }

  // ------------------------------------------------------------------ table & environment

  private applyFog(): void {
    const e = this.plane.env;
    this.scene.fog = new THREE.Fog(e.fog, 34, 110 - e.fogDensity * 600);
    this.scene.background = new THREE.Color(e.skyBottom);
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
      this.world.remove(p.block, p.slot);
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
      const mat = new THREE.Mesh(new THREE.PlaneGeometry(MAT_W + 0.5, MAT_D + 0.5), new THREE.MeshBasicMaterial({ map: matTexture(e.inlay, this.plane.ui.accent, color), transparent: true, depthWrite: false }));
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
        const block = new THREE.Mesh(new THREE.BoxGeometry(CARD_W, 1, CARD_H), [this.bodyMat, this.bodyMat, this.backMaterial(seat.player), this.bodyMat, this.bodyMat, this.bodyMat]);
        block.rotation.y = seat.rot;
        block.position.set(wx, 0, wz);
        block.visible = false;
        block.castShadow = this.quality !== "low";
        block.userData = { pile: zone, player: seat.player };
        this.world.add(slot, block);
        this.piles.set(`${seat.player}:${zone}`, { block, slot, count: -1 });
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
    tex.anisotropy = 8;
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
    m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.5, metalness: 0 });
    this.materials.set(key, m);
    return m;
  }

  // ------------------------------------------------------------------ cards

  private makeCard(id: string): CardObj {
    const group = new THREE.Group();
    const face = new THREE.Mesh(this.cardFaceGeo, this.bodyMat);
    face.position.y = THICK + 0.0008;
    face.userData = { card: id };
    const glow = new THREE.Mesh(this.glowGeo, new THREE.MeshBasicMaterial({ color: "#fff", transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    glow.position.y = -0.001;
    group.add(glow, face);
    this.world.add(group);
    const obj: CardObj = { id, group, face, glow, badge: null, badgeText: "", faceKey: "", target: new THREE.Vector3(), rot: 0, tilt: 0, seen: true };
    this.cards.set(id, obj);
    return obj;
  }

  private disposeCard(c: CardObj): void {
    this.world.remove(c.group);
    (c.glow.material as THREE.Material).dispose();
    if (c.badge) {
      (c.badge.material as THREE.SpriteMaterial).map?.dispose();
      c.badge.material.dispose();
    }
  }

  private setBadge(c: CardObj, text: string, color: string): void {
    if (c.badgeText === text) return;
    c.badgeText = text;
    if (c.badge) {
      c.group.remove(c.badge);
      (c.badge.material as THREE.SpriteMaterial).map?.dispose();
      c.badge.material.dispose();
      c.badge = null;
    }
    if (!text) return;
    const cv = labelCanvas(text, color);
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: canvasTexture(cv), depthTest: false, transparent: true }));
    const h = 0.26;
    s.scale.set((h * cv.width) / cv.height, h, 1);
    s.position.set(0, 0.25, CARD_H * 0.28);
    s.renderOrder = 10;
    c.group.add(s);
    c.badge = s;
  }

  private place(c: CardObj, seat: Seat | undefined, lx: number, lz: number, y: number, extraRot = 0): void {
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
      bf.forEach((id, i) => {
        const card = view.cards[id];
        const c = show(id);
        if (!card || !c) return;
        const pos = pending[id] ?? [card.x ?? 20 + (i % 10) * 90, card.y ?? 20 + Math.floor(i / 10) * 130];
        const [lx, lz] = virtualToLocal(pos[0], pos[1]);
        const tapped = (card.tapped ? -Math.PI / 2 : 0) + (card.flipped ? Math.PI : 0) - ((card.rotation ?? 0) * Math.PI) / 180;
        const lift = card.attacking ? 0.18 : 0;
        this.place(c, seat, lx, lz, 0.004 + i * 0.0035 + lift, tapped);
        c.tilt = card.attacking ? -0.12 : 0;
        const counters = card.counters ? Object.entries(card.counters).filter(([, n]) => n) : [];
        const stats = view.rules?.stats?.[id];
        const pt = stats?.pt ? `${stats.pt[0]}/${stats.pt[1]}` : "";
        const label = [card.damage ? `${card.damage} dmg` : counters.length ? counters.map(([k, n]) => (k === "+1/+1" ? `+${n}/+${n}` : k === "-1/-1" ? `-${n}/-${n}` : `${k} ${n}`)).join(" · ") : "", pt]
          .filter(Boolean).join(" · ");
        this.setBadge(c, label, card.damage ? "#9b2f27" : "#2c3a5a");
        this.setGlow(c, selection.has(id) ? this.plane.ui.select : this.legalColor(view, id), selection.has(id) ? 0.9 : 0.55);
      });
      // piles
      for (const zone of ["library", "graveyard", "exile"] as const) {
        const z = view.zones[`${pid}:${zone}`];
        const count = Array.isArray(z) ? z.length : (z as LibraryView | undefined)?.count ?? 0;
        const pile = this.piles.get(`${pid}:${zone}`);
        if (pile && pile.count !== count) {
          pile.count = count;
          const h = Math.max(0.001, count * 0.012);
          pile.block.visible = count > 0 && (zone === "library" || count > 1);
          pile.block.scale.y = zone === "library" ? h : Math.max(0.001, (count - 1) * 0.012);
          pile.block.position.y = pile.block.scale.y / 2;
        }
        if (zone !== "library" && Array.isArray(z) && z.length) {
          const top = z[z.length - 1]!;
          const c = show(top);
          if (c && seat) {
            const [lx, lz] = PILES[zone];
            this.place(c, seat, lx, lz, (z.length - 1) * 0.012 + 0.004, 0);
            this.setBadge(c, "", "");
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
        this.setBadge(c, "", "");
        this.setGlow(c, selection.has(id) ? this.plane.ui.select : this.legalColor(view, id), 0.6);
      });
      // other players' hands: a fan of backs at their edge (count only)
      if (pid !== this.me) this.syncHandFan(seat, ((view.zones[`${pid}:hand`] as string[] | undefined) ?? []).length);
    }

    // the stack: cards hover above the centre of the table, most recent on top
    view.stack.forEach((id, i) => {
      const c = show(id);
      if (!c) return;
      const n = view.stack.length;
      const x = (i - (n - 1) / 2) * 0.5;
      const me = seatOf.get(this.me);
      this.place(c, undefined, x, -i * 0.12, 0.9 + i * 0.06, me?.rot ?? 0);
      c.tilt = -0.35;
      this.setBadge(c, "", "");
      this.setGlow(c, selection.has(id) ? this.plane.ui.select : this.plane.ui.accent, 0.5);
    });

    for (const [id, c] of this.cards) {
      if (!c.seen) {
        this.disposeCard(c);
        this.cards.delete(id);
      }
    }
    if (need.length) requestCards(need);
    this.stats.cards = this.cards.size;
    this.syncArrows(view);
  }

  /** Attack, block and targeting arrows: arcs over the table from source to target. */
  private syncArrows(view: GameView): void {
    for (const child of [...this.arrows.children]) {
      this.arrows.remove(child);
      const m = child as THREE.Mesh;
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    }
    const at = (id: string): THREE.Vector3 | null => {
      const c = this.cards.get(id);
      if (c) return c.target.clone().setY(c.target.y + 0.05);
      const seat = this.seatList.find((s) => s.player === id);
      if (!seat) return null;
      const [wx, wz] = toWorld(seat, 0, MAT_D / 2 + 0.6);
      return new THREE.Vector3(wx, 0.1, wz);
    };
    const add = (from: string, to: string, color: string) => {
      const a = at(from);
      const b = at(to);
      if (!a || !b || a.distanceTo(b) < 0.3) return;
      const mid = a.clone().lerp(b, 0.5);
      mid.y += 1.2 + a.distanceTo(b) * 0.12;
      const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
      const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, depthWrite: false });
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 28, 0.035, 6), mat);
      tube.renderOrder = 5;
      const head = new THREE.Mesh(new THREE.ConeGeometry(0.14, 0.36, 10), mat.clone());
      const end = curve.getPoint(1);
      const dir = curve.getTangent(1).normalize();
      head.position.copy(end).addScaledVector(dir, -0.12);
      head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      this.arrows.add(tube, head);
    };
    for (const c of Object.values(view.cards)) {
      if (c.attacking) add(c.id, c.attacking.id, "#e0463c");
      if (c.blocking) add(c.id, c.blocking, "#5fa8ff");
    }
    for (const ar of view.arrows ?? []) {
      const color = ar.kind === "attack" ? "#e0463c" : ar.kind === "block" ? "#5fa8ff" : ar.kind === "target" ? this.plane.ui.select : this.plane.ui.accent;
      for (const t of ar.targets) add(ar.source, t, color);
    }
    this.stats.arrows = this.arrows.children.length / 2;
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
      look = new THREE.Vector3(0, 0, 0.5);
      pos = new THREE.Vector3(0, span * 1.45, span * 0.28);
    } else if (typeof preset === "object") {
      const seat = this.seatList.find((s) => s.player === preset.focus) ?? mine;
      const [lx, lz] = toWorld(seat, 0, -0.3);
      const [px, pz] = toWorld(seat, 0, MAT_D / 2 + 5.2);
      look = new THREE.Vector3(lx, 0, lz);
      pos = new THREE.Vector3(px, 8.5, pz);
    } else {
      // behind my seat, looking across the table (the main view): my mat large, every opponent visible
      const [lx, lz] = toWorld(mine, 0, -MAT_D / 2 - 2.8);
      const [px, pz] = toWorld(mine, 0, MAT_D / 2 + span * 0.4);
      look = new THREE.Vector3(lx, 0, lz);
      pos = new THREE.Vector3(px, span * 0.7, pz);
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
    for (const p of this.piles.values()) targets.push(p.block, p.slot);
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
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    document.body.classList.remove("dragging");
    if (!d.active) return;
    const anchorOff = d.offsets.get(d.anchor);
    const target = this.resolveDrop(e.clientX, e.clientY, anchorOff ? anchorOff.clone().negate() : undefined);
    if (target) dropCards(d.ids, d.anchor, { ...target, manual: e.altKey });
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
    if (!hit || !view) return;
    const fake = { clientX: e.clientX, clientY: e.clientY, preventDefault() {}, stopPropagation() {} } as unknown as React.MouseEvent;
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
    const dt = Math.min(0.5, this.clock.getDelta()); // real time: slow devices still settle quickly
    const t = this.clock.elapsedTime;
    const k = 1 - Math.exp(-dt * 14);
    let n = 0;
    for (const c of this.cards.values()) {
      c.group.position.lerp(c.target, k);
      c.group.rotation.y = angleLerp(c.group.rotation.y, c.rot, k);
      c.group.rotation.x += (c.tilt - c.group.rotation.x) * k;
      if (n < 1024) {
        c.group.updateMatrix();
        this.bodies.setMatrixAt(n++, c.group.matrix);
      }
    }
    this.bodies.count = n;
    this.bodies.instanceMatrix.needsUpdate = true;
    const kc = 1 - Math.exp(-dt * 5);
    this.camPos.lerp(this.camGoalPos, kc);
    this.camLook.lerp(this.camGoalLook, kc);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camLook);
    this.env?.update(t);
    this.renderer.render(this.scene, this.camera);
    this.frames++;
    if (t - this.fpsAt >= 1) {
      this.stats = { ...this.stats, fps: Math.round(this.frames / (t - this.fpsAt)), calls: this.renderer.info.render.calls, triangles: this.renderer.info.render.triangles, cards: this.cards.size };
      this.frames = 0;
      this.fpsAt = t;
    }
  };
}
