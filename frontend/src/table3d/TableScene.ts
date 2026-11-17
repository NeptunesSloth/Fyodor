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
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { openMenu } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { imageUrl } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, type CardStats, type GameCard, type GameView, type LibraryView, type ZoneName } from "../types/game";
import { counterShort, isKeyword } from "../game/counters";
import { changeLife, draw, send, tapCards, targetsFor } from "../game/actions";
import { Batcher, runSeatAction, TypedCount, type SeatActionId } from "../game/seatActions";
import { isOut } from "../game/outOfGame";
import { cardMenu } from "../game/cardMenu";
import { tableMenu } from "../game/selection";
import { countMark, zonePileTops } from "../game/piles";
import type { DropResult } from "../game/dnd";
import type { PingTarget } from "../services/night";
import { dropCards } from "../game/drop";
import { pickClick } from "../game/Overlays";
import { answerByClick, clickAnswer, legalClass } from "../game/rules/RulesHud";
import { targetBeams } from "../game/targeting/beams";
import { useTargeting } from "../game/targeting/store";
import { libraryMenu, pileMenu, PILE_LABEL } from "../game/ZonePile";
import type { PlaneTheme } from "../theme/planes";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { buildEnvironment, type Environment } from "./environment";
import { arrowTime, makeArrow, type GroundBox } from "./arrows";
import { makeTether } from "./tethers";
import { combatCardIds, frameBox, isCloseUp } from "./focus";
import { attachmentLinks, tetherAnchor } from "../game/attachments";
import { commanderDealt, dealtText } from "../game/commanderDamage";
import { angleDelta, ease, liftFor } from "./motion";
import { createPost, type Post } from "./post";
import { adjustCamera, NO_ADJUST, orbitBy, panBy, panKey, zoomAt, type CamAdjust, type CamPose, type PanBounds } from "./cameraControls";
import { DiceTray, prewarmDice } from "./dice";
import { DiceHud } from "./diceHud";
import { CannonRig, fireCannon } from "./cannon3d";
import { rollerEnv } from "./diceEnv";
import { slide, SLIDE_FPS, type SlideCard } from "./cardPhysics";
import { SeatProps } from "./seatProps";
import { CARD_BACK_URL, checkCardBack, onCardBack } from "../cards/cardBack";
import { TableMotion } from "./motion3d";
import { PlanarTable } from "./planar3d";
import { showPlanarText } from "../game/planechase";
import { EndScene3D } from "./endScene3d";
import { onEndScene } from "../game/motion/endScene";
import { onTableEvents } from "../game/motion/tableEvents";
import { onMotionSkip } from "../game/motion/timing";
import type { DiceShow } from "../game/dice";
import {
  aisleOf, CARD_H, CARD_W, commandSlot, COMMAND_SLOTS, HEART, heartSpot, MAT_D, MAT_W, mirrored, PILES, PLATE, pileSpot, localToVirtual, onBattlefield, pileAt, seats,
  tableSize, toLocal, toWorld, virtualToLocal, plateDepth, plateOffset, plateWidth, planarSpot, wellPiece, wellSize, type PileZone, type Seat,
} from "./layout";
import { easeFan, FAN_MAX, type FanCard, fanCorners, fanTag, handFan, refanFrom, showsFan } from "./handFan";
import { whenProxyFontsReady } from "../cards/proxyMeasure";
import { abilityCardTexture, backCanvas, canvasTexture, handCountCanvas, cardCornerMask, cardImageTexture, cardOverlayCanvas, contactShadowTexture, type CardOverlay, matTexture, pileBadgeCanvas, setMaxAnisotropy, textCardTexture } from "./textures";
import { drawWell, WELL_PX, wellCanvasSize, wellStretch, whenWellFontsReady, type WellArt } from "./zoneWells";
import { taxSentence } from "../game/seatIcons";
import { ArrangedBoards, AU, orderFromRest, reorderMat, TILE_SQUASH, tileScale, type Spot } from "./arrange3d";
import { freeCovers, pileBadgeSpot } from "./covers";
import { litCards } from "../game/combatFilter";
import { FLAT_LOOK, nameScreenEm, tileLook, tileOverlayCanvas, tileTexture, TILE_PX, type TileLook } from "./tiles";
import { fitCamera, type FitPoint, FOCUS_ELEVATION, LENS_REACH, ndcBox, nearFarFor, offMat, OVERVIEW_ELEVATION, propSpots, seatElevation, seatPoints, TABLE_FOV, tableLens, tablePoints, tableRect, viewDir } from "./framing";
import { boardOrder, saveBoardOrder } from "../game/arrange";
import { useBoardOrderTick } from "../game/arrangeDrop";
import { tokenArtFace, tokenArtId } from "../game/tokenArt";
import { Cursors3D, type CursorMessage } from "./cursors3d";
import { CursorOutbox, overTable, worldToCursor } from "./cursors";

/** How long a refused action's card stays marked. */
export const ERROR_MS = 1800;

export type Quality = "low" | "medium" | "high";
export type CameraPreset = "seat" | "overview" | { focus: string } | { card: string } | { stack: true } | { combat: true };

const THICK = 0.016;
/**
 * The flat layers on the felt, each at its own height so none fights another for depth at any zoom (with the camera's
 * near plane following its distance: nearFarFor): the mats, the cards' contact shadows, the pile slots, then the cards.
 */
const MAT_Y = 0.002;
const SHADOW_Y = 0.0026;
const SLOT_Y = 0.0034;
/** A zone panel's material: the mat's dark surface, a rounded border in the seat's colour (drawn at the panel's own
 * proportions, so its border is as even as the mat's). */
function zonePanelMaterial(color: string, w: number, h: number): THREE.MeshStandardMaterial {
  const k = 150;
  const c = document.createElement("canvas");
  c.width = Math.max(8, Math.round(w * k));
  c.height = Math.max(8, Math.round(h * k));
  const g = c.getContext("2d")!;
  const r = 26;
  g.beginPath();
  g.roundRect(0, 0, c.width, c.height, r);
  g.fillStyle = "#302a24";
  g.fill();
  g.lineWidth = 6;
  g.strokeStyle = color;
  g.beginPath();
  g.roundRect(6, 6, c.width - 12, c.height - 12, r - 6);
  g.stroke();
  const tex = canvasTexture(c);
  return new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false, roughness: 1, metalness: 0, envMapIntensity: 0.15 });
}
/** Every mat's surface, dark warm grey (the Oops I Baked a Pie table's), so each seat's colour carries its things. */
const MAT_FELT = "#36302a";
const MAT_NAP = "#40392f";
/** A card's face over its body's top, and its badges over the face. */
export const FACE_LIFT = 0.0012;
/** -- token piles -- a ×N badge's least height on screen (CSS px), and its height bounds on the table (world units). */
const PILE_BADGE_PX = 26;
const BADGE_MIN_H = 0.2;
const BADGE_MAX_H = 0.62;
const badgeA = new THREE.Vector3();
const badgeB = new THREE.Vector3();
const badgeDir = new THREE.Vector3();
/** Cards drawn per pile at most (taller piles space them out). */
const PILE_LAYERS = 48;
/** The pale core of a card, glimpsed now and then along a pile's edge. */
const PILE_CORE = new THREE.Color("#bdb4a2");
const LIFT = 0.55;
/** How fast (world units a second) a card must still be moving when you let go for it to slide on (a flick). */
const FLICK_SPEED = 4.5;

export interface ScreenRect { id: string; left: number; top: number; right: number; bottom: number }

/** -- targeting -- the arrow's start when the source is the spell in my hand (on the screen, not the table). */
const MY_HAND = "\u0000my-hand";

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
  /** Table motion (table3d/motion3d.ts): new to the table and not yet placed; a flight drives it; a strike lunge is on it. */
  fresh?: boolean;
  flying?: boolean;
  struck?: boolean;
  /** -- arranged boards -- an art tile on an arranged mat (table3d/arrange3d.ts): the card squashed to `squash` of its depth (eased in `sq`). */
  tile?: boolean;
  squash?: number;
  sq?: number;
  /** -- token piles -- the card it lies wholly under on a battlefield (table3d/covers.ts): while that one sits still over it,
   * it is not drawn, picked or shadowed. */
  cover?: string;
  /** -- token piles -- the ×N badge of a pile's top card (free placement), sized each frame to stay readable (setBadge). */
  badge?: THREE.Mesh | null;
  badgeN?: number;
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
  /** The well's picture (table3d/zoneWells.ts): redrawn when its count changes. */
  art: WellArt;
  canvas: HTMLCanvasElement;
  tex: THREE.CanvasTexture;
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

/**
 * Another player's hand held up at their edge (table3d/handFan.ts): one instanced mesh of backs per seat (one draw call),
 * eased from where its cards were to where the fan puts them when the count changes; a count tag over it past FAN_MAX.
 */
interface HeldFan {
  mesh: THREE.InstancedMesh;
  count: number;
  cur: FanCard[];
  goal: FanCard[];
  moving: boolean;
  tag: THREE.Sprite | null;
  tagCount: number;
}

/** A card that is a back on both sides (another player's held hand: its faces are never drawn), UVs as flatCardGeometry. */
function twoBackGeometry(w: number, h: number, r: number): THREE.BufferGeometry {
  const front = flatCardGeometry(w, h, r);
  // turned over about its own long axis: the other side reads the right way round (not mirrored), top still at −z
  const back = front.clone().rotateZ(Math.PI);
  const geo = mergeGeometries([front, back])!;
  front.dispose();
  back.dispose();
  return geo;
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
function overlayFor(card: GameCard, stats: CardStats | undefined, tile = false): CardOverlay | null {
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
    // a tile prints its P/T: the plate covers it only when the rules' differ (or it has none: an animated land)
    const changed = tile && (!Number.isFinite(bp) || !Number.isFinite(bt) || stats.pt[0] !== bp || stats.pt[1] !== bt);
    if (dir || damage || keywords.length || plus || minus || changed) pt = { text: `${stats.pt[0]}/${stats.pt[1]}`, dir };
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
const fanM = new THREE.Matrix4();
const ONE = new THREE.Vector3(1, 1, 1);
const shadowPos = new THREE.Vector3();
const shadowQ = new THREE.Quaternion();
const shadowScale = new THREE.Vector3();
const shadowM = new THREE.Matrix4();
const shadowColor = new THREE.Color();
/** A body drawn at no size (a fading stand-in card keeps only its shadow). */
const NO_BODY = new THREE.Matrix4().makeScale(0, 0, 0);

/** -- token piles -- whether `a` lies just where `b` does, turned the same and no larger (so `b`, lying over it, hides it). */
function lyingOn(a: THREE.Object3D, b: THREE.Object3D): boolean {
  return Math.abs(a.position.x - b.position.x) < 0.005 && Math.abs(a.position.z - b.position.z) < 0.005
    && Math.abs(angleLerp(0, b.rotation.y - a.rotation.y, 1)) < 0.01 && a.scale.x <= b.scale.x + 0.01 && a.rotation.x === b.rotation.x;
}

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
  private camera = new THREE.PerspectiveCamera(TABLE_FOV, 1, 0.1, 400);
  private env: Environment | null = null;
  private world = new THREE.Group();
  private cards = new Map<string, CardObj>();
  private piles = new Map<string, PileObj>();
  private mats = new Map<string, THREE.Mesh>();
  private handFans = new Map<string, HeldFan>();
  /** -- live cursors -- the other players' pointers, and mine on its way to them (table3d/cursors3d.ts) */
  private cursors = new Cursors3D((id, cx, cy) => this.onCardWorld(id, cx, cy));
  private cursorOut = new CursorOutbox();
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
  /** -- camera -- the lens the camera is going to (wider when orbited below the view's pitch). */
  private camGoalFov = TABLE_FOV;
  private camGoalLook = new THREE.Vector3();
  private preset: CameraPreset = "seat";
  /** -- camera -- the player's move of the view (table3d/cameraControls.ts), and the one kept for each view left behind. */
  private adj: CamAdjust = NO_ADJUST;
  private adjFor = new Map<string, CamAdjust>();
  /** The view's own camera, before the player's move (what the wheel, drags and keys adjust). */
  private camBase: CamPose | null = null;
  private goalCam = new THREE.PerspectiveCamera();
  private drag: { ids: string[]; anchor: string; start: [number, number]; grab: THREE.Vector3; offsets: Map<string, THREE.Vector3>; active: boolean; trail: { t: number; x: number; z: number }[] } | null = null;
  /** A flicked card sliding across its mat (and anything it knocked), played back from table3d/cardPhysics.ts. */
  private sliding: { seat: Seat; start: number; frames: number; tracks: Map<string, Float32Array>; done?: () => void } | null = null;
  /** -- camera -- a right press (an orbit once it moves; a menu if it never does) and a middle-drag pan. */
  private rightPress: { id: number; x: number; y: number; adj: CamAdjust; moved: boolean } | null = null;
  private lastRightUp = 0;
  private panGrab: { id: number; ground: THREE.Vector3 } | null = null;
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
  /** A unit square lying flat: a pile's ×N badge, scaled to its size each frame (sizeBadges). */
  private badgeGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  private fanGeo = twoBackGeometry(CARD_W, CARD_H, 0.05);
  private cardBodyGeo: THREE.ExtrudeGeometry;
  private glowGeo = flatCardGeometry(CARD_W + 0.12, CARD_H + 0.12, 0.09);
  /** Card stock: the pale core you see on a card's edge. */
  private bodyMat = new THREE.MeshStandardMaterial({ color: "#cdc6b8", roughness: 0.78 });
  /** A pile's cards: their edges, near black (a card's border) with each one a little lighter or darker than the next, so a stack
   * reads as so many cards rather than one pale block. Per-card shades come from the instances' colours. */
  private pileMat = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.82 });
  private hitMat = new THREE.MeshBasicMaterial({ visible: false });
  private textures = new Map<string, THREE.Texture>();
  private materials = new Map<string, THREE.MeshStandardMaterial>();
  /** -- targeting -- a face material darkened for a card that isn't a choice (sharing its texture). */
  private dimMats = new Map<THREE.MeshStandardMaterial, THREE.MeshStandardMaterial>();
  private loader = new THREE.TextureLoader();
  private failed = new Set<string>();
  private unsubs: (() => void)[] = [];
  /** Every card's body (its thickness and shadow) in one draw call. */
  private bodies: THREE.InstancedMesh;
  private arrows = new THREE.Group();
  /** Thrown dice (table3d/dice.ts) and their chips (diceHud.ts). */
  private dice: DiceTray;
  private diceHud: DiceHud;
  private diceTurn = -1;
  /** -- table toys -- the dice cannon (table3d/cannon3d.ts), built the first time it is fired. */
  private cannon: CannonRig | null = null;
  /** Life hearts over every seat and my seat's buttons (table3d/seatProps.ts). */
  private props = new SeatProps();
  private propsKey = "";
  private hoveredButton: SeatActionId | null = null;
  private lifeBatch = new Batcher((pid, d) => void changeLife(pid, d), (pid, pending) => {
    const p = this.view?.players.find((x) => x.id === pid);
    if (p) this.props.setLife(pid, p.life, pending);
  });
  private typed = new TypedCount((id, n) => this.props.setTyped(id, n), (id, n) => runSeatAction(id, n, this.me));
  /** A soft contact shadow under every card (one draw call), spreading as the card lifts. */
  private shadows: THREE.InstancedMesh;
  private shadowTex = contactShadowTexture();
  private arrowKey = "";
  /** -- targeting -- the source, hovered and chosen candidates while I choose targets (game/targeting/beams.ts). */
  private beams: ReturnType<typeof targetBeams> = null;
  /** Attachment lines (game/attachments.ts): shown while either end is hovered or selected. */
  private tethers = new THREE.Group();
  private tetherKey = "";
  /** Where the stack's standing cards are (beams route around it), and each stack card's beam anchor. */
  private stackBox: GroundBox | null = null;
  private stackAnchors = new Map<string, { far: THREE.Vector3; near: THREE.Vector3 }>();
  /** Soft studio reflections for metal, lacquer and card gloss (a prefiltered room, no download). */
  private envMap: THREE.Texture;
  private post: Post | null = null;
  /** Card flights, stand-ins, riffles, strikes and numbers (table3d/motion3d.ts), stepped from this loop. */
  private motion: TableMotion;
  /** -- planechase -- the face-up plane lying in the aisle (table3d/planar3d.ts). */
  private planar = new PlanarTable();
  /** The end-of-game table scene (table3d/endScene3d.ts): dim, camera ease, one pulse, a few motes; stepped from this loop. */
  private end: EndScene3D;
  /** -- arranged boards -- each mat in rows (table3d/arrange3d.ts), unless this device chose free placement; each battlefield card's spot. */
  private boards = new ArrangedBoards();
  private placed = new Map<string, Spot>();
  private arranged = true;
  /** -- framing -- the canvas size in CSS px (the camera fits the table to it). */
  private viewW = 1;
  private viewH = 1;
  private fitCam = new THREE.PerspectiveCamera();
  private fogBase: [number, number] = [30, 95];
  private bodyN = 0;
  private pushStandIn = (obj: THREE.Object3D, opacity: number): void => {
    this.bodyN = this.writeBody(obj, this.bodyN, opacity);
  };

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
    this.dice = new DiceTray({ look: usePrefs.getState().diceLook, envMap: this.envMap, shadows: quality !== "low", segments: quality === "low" ? 3 : 4 });
    this.diceHud = new DiceHud(container, (key) => this.dice.dismiss(key));
    this.unsubs.push(usePrefs.subscribe((s) => this.dice.setLook(s.diceLook)), prewarmDice());
    // -- arranged boards -- the board layout setting, and my order for a board (dragged along its row, here or on the 2D table)
    this.arranged = usePrefs.getState().boardLayout !== "free";
    this.unsubs.push(usePrefs.subscribe((s, prev) => {
      if (s.combatFilter !== prev.combatFilter && s.boardLayout === prev.boardLayout) return this.syncCards(); // -- combat filter -- (re-dim once)
      if (s.boardLayout === prev.boardLayout) return;
      this.arranged = s.boardLayout !== "free";
      this.syncCards();
      this.updateCameraGoal();
    }), useBoardOrderTick.subscribe(() => this.syncCards()));
    this.unsubs.push(useTargeting.subscribe(() => this.syncCards())); // a candidate hovered in the tray, or chosen
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
    const shadowMat = new THREE.MeshBasicMaterial({ color: "#fff", alphaMap: this.shadowTex, transparent: true, opacity: 0.62, depthWrite: false });
    shadowMat.onBeforeCompile = (sh) => {
      sh.fragmentShader = sh.fragmentShader.replace("#include <alphamap_fragment>", "#include <alphamap_fragment>\n diffuseColor.a *= diffuseColor.r;\n diffuseColor.rgb = vec3(0.0);");
    };
    shadowMat.customProgramCacheKey = () => "card-contact-shadow";
    this.shadows = new THREE.InstancedMesh(shadowGeo, shadowMat, 1024);
    this.shadows.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(1024 * 3).fill(1), 3);
    this.shadows.count = 0;
    this.shadows.frustumCulled = false;
    this.shadows.renderOrder = -2;
    this.world.add(this.bodies, this.shadows, this.arrows, this.dice.group, this.props.group);
    this.world.add(this.tethers);
    // -- live cursors -- the others' pointers, as the server relays them (never mine: another tab of my seat sends them too)
    this.world.add(this.cursors.group);
    const onCursor = (e: Event) => {
      const msg = (e as CustomEvent<CursorMessage>).detail;
      if (this.view && msg.from !== this.view.viewer) this.cursors.receive(msg, performance.now());
    };
    window.addEventListener("fyodor:cursor", onCursor);
    this.unsubs.push(() => window.removeEventListener("fyodor:cursor", onCursor));
    this.scene.add(this.world);
    this.motion = new TableMotion({
      world: this.world, faceGeo: this.cardFaceGeo, thick: THICK,
      me: () => this.me, view: () => this.view, card: (id) => this.cards.get(id),
      seat: (p) => this.seatList.find((s) => s.player === p),
      pileY: (zone) => {
        const p = this.piles.get(zone);
        return p && p.count > 0 ? pileHeight(p.count) + THICK : 0;
      },
      back: (owner) => this.backMaterial(owner),
      face: (id) => {
        const card = this.view?.cards[id];
        return card ? this.faceMaterial(card, this.faceKeyFor(card)) : this.backMaterial("");
      },
      heart: (p) => this.props.heartWorld(p),
    });
    this.unsubs.push(onTableEvents((events, next, prev) => this.motion.play(events, next, prev)), onMotionSkip(() => this.motion.finish()));
    this.world.add(this.planar.group);
    this.unsubs.push(onMotionSkip(() => this.planar.finish()));
    this.end = new EndScene3D(this.scene, () => tableSize(this.seatList));
    this.unsubs.push(onEndScene((cue) => this.end.play(cue)));
    this.applyFog();
    this.bindInput();
    this.loop();
    // the zone labels and life totals are drawn in the game's fonts: drawn again once those have loaded
    void whenProxyFontsReady().then(() => {
      if (this.disposed) return;
      this.rebuildTable();
      this.propsKey = "";
      if (this.view) this.update(this.view, this.me);
    });
  }
  private disposed = false;

  // ------------------------------------------------------------------ public API

  setPlane(plane: PlaneTheme): void {
    if (plane.id === this.plane.id) return;
    this.plane = plane;
    this.applyFog();
    this.rebuildTable();
  }

  /**
   * Show a view. The camera keeps the place the player moved it to in each view (seat, whole table, a player's board)
   * until that view is reset (Home, 1, 0: resetView); a close-up (C, K, X) always opens as framed.
   */
  setCamera(preset: CameraPreset): void {
    if (!isCloseUp(this.preset)) this.adjFor.set(JSON.stringify(this.preset), this.adj);
    this.preset = preset;
    this.adj = isCloseUp(preset) ? NO_ADJUST : this.adjFor.get(JSON.stringify(preset)) ?? NO_ADJUST;
    this.updateCameraGoal();
  }

  /** Home, 1 and 0: forget the player's move of that view (and if it's the one showing, put the camera back now). */
  resetView(preset: CameraPreset): void {
    const key = JSON.stringify(preset);
    this.adjFor.delete(key);
    if (JSON.stringify(this.preset) === key) {
      this.adj = NO_ADJUST;
      this.updateCameraGoal();
    }
  }

  /** The arrow keys: pan the view a step (Shift: three steps). */
  panView(dir: "left" | "right" | "up" | "down", fast: boolean): void {
    if (!this.camBase) return;
    this.moveView(panKey(this.adj, this.camBase, dir, fast, this.panBounds(), 1 / LENS_REACH));
  }

  /** -- camera -- the player moved the view. */
  private moveView(next: CamAdjust): void {
    this.adj = next;
    this.updateCameraGoal();
  }

  /** How far the view's look point may wander: over the table top. */
  private panBounds(): PanBounds {
    const size = tableSize(this.seatList);
    return { hx: size.w / 2, hz: size.d / 2 };
  }

  /** The point on the table under a pointer, as the camera will see it once it arrives (so drags don't chase the easing). */
  private groundAt(clientX: number, clientY: number): THREE.Vector3 | null {
    const cam = this.goalCam;
    cam.copy(this.camera);
    cam.fov = this.camGoalFov;
    cam.updateProjectionMatrix();
    cam.position.copy(this.camGoalPos);
    cam.lookAt(this.camGoalLook);
    cam.updateMatrixWorld(true);
    this.ray.setFromCamera(this.pointer(clientX, clientY), cam);
    return this.ray.ray.intersectPlane(this.tablePlane, new THREE.Vector3());
  }

  resize(w: number, h: number): void {
    this.viewW = w;
    this.viewH = h;
    this.renderer.setSize(w, h, false);
    this.post?.setSize(w, h);
    // frame the table above the hand: render the lower part of a taller frame, which lifts what the camera looks at by
    // half the hand band (picking and projection use the same matrices); the aspect is that whole frame's
    const fov = this.camGoalFov === TABLE_FOV ? TABLE_FOV : this.camera.fov; // (the lens of an orbit below the view's pitch, kept)
    tableLens(w, h, this.camera);
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
    this.updateCameraGoal();
  }

  update(view: GameView, me: string): void {
    // landed dice stay for the turn they were rolled in (game/dice.ts)
    if (this.diceTurn >= 0 && view.turn.number !== this.diceTurn) this.dice.clear();
    this.diceTurn = view.turn.number;
    this.view = view;
    this.me = me;
    const key = `${view.seat_order.join(",")}|${me}`;
    if (key !== this.seatKey) {
      this.seatKey = key;
      this.seatList = seats(view.seat_order, me);
      this.rebuildTable();
      this.updateCameraGoal();
    }
    const out = isOut(view, me); // -- out of the game -- no seat buttons by the mat of a player who left (game/outOfGame.ts)
    const propsKey = `${key}|${view.players.map((p) => p.color).join(",")}|${out}`;
    if (propsKey !== this.propsKey) {
      this.propsKey = propsKey;
      this.props.rebuild(this.seatList, out ? "" : me, Object.fromEntries(view.players.map((p) => [p.id, p.color])), out);
      this.fitHearts();
    }
    for (const p of view.players) this.props.setLife(p.id, p.life, this.lifeBatch.pending(p.id));
    this.props.setCommanders(this.seatList, Object.fromEntries(view.players.map((p) => [p.id, p.commanders.map((c) => ({ key: c.key, tax: c.tax }))])),
      Object.fromEntries(view.players.map((p) => [p.id, p.color])), this.myRot());
    this.cursors.setTable(this.seatList, Object.fromEntries(view.players.map((p) => [p.id, { color: p.color, name: p.name }])), performance.now());
    this.planar.sync(view.planechase, planarSpot(this.seatList), this.myRot(), performance.now()); // -- planechase --
    this.syncCards();
  }

  /** -- live cursors -- does my pointer go to the others? Only a seated player's, and not at a hot-seat table (one screen). */
  private sendsCursor(): boolean {
    const v = this.view;
    return !!v && v.game.mode !== "local" && v.players.some((p) => p.id === v.viewer);
  }

  /** -- live cursors -- my pointer moved over the canvas: over the table top it goes out (at most ~15 a second). */
  private trackPointer(clientX: number, clientY: number): void {
    if (!this.sendsCursor()) return;
    const p = this.tablePoint(clientX, clientY);
    const spot = p && overTable(tableSize(this.seatList), p.x, p.z) ? worldToCursor(this.seatList, p.x, p.z) : null;
    // over a card (not while carrying one): the point on it, in its own frame, so it lands on that card on every screen
    const c = spot && !this.drag?.active && this.hovered ? this.cards.get(this.hovered) : undefined;
    if (spot && c) {
      this.ray.setFromCamera(this.pointer(clientX, clientY), this.camera);
      const hit = this.ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -c.group.position.y), new THREE.Vector3());
      if (hit) {
        const l = c.group.worldToLocal(hit);
        const r = (v: number) => Math.round(Math.max(-1, Math.min(1, v)) * 1000) / 1000;
        Object.assign(spot, { card: c.id, cx: r(l.x / (CARD_W / 2)), cy: r(l.z / (CARD_H / 2)) });
      }
    }
    this.cursorOut.move(spot);
  }

  /** -- live cursors -- a point on a card (its half-widths) on this screen, while the card is on this table. */
  private onCardWorld(id: string, cx: number, cy: number): [number, number] | null {
    const c = this.cards.get(id);
    if (!c) return null;
    const w = c.group.localToWorld(new THREE.Vector3(cx * CARD_W / 2, 0, cy * CARD_H / 2));
    return [w.x, w.z];
  }

  /** -- live cursors -- where a player's cursor shows on this screen (CSS px in the page), while it does. */
  cursorOnScreen(pid: string): { x: number; y: number } | null {
    const at = this.cursors.worldOf(pid);
    return at && this.cursors.group.visible ? this.project(at) : null;
  }

  /**
   * A roll everyone sees (game/dice.ts): the dice leave the roller's hand over the near edge of their mat, tumble
   * across it and come to rest on its far half (table3d/diceThrow.ts), glancing off the roller's piles. The throw
   * runs in the roller's mat frame, so it is the same throw on every screen. Rolling again clears your last dice.
   */
  throwDice(show: DiceShow): void {
    if (show.cannon) {
      // -- table toys -- fired from the dice cannon: it rolls in only to fire (not on reduced motion or low graphics)
      const rig = !document.body.classList.contains("reduced-motion") && this.quality !== "low";
      if (rig && !this.cannon) {
        this.cannon = new CannonRig(this.envMap, true);
        this.world.add(this.cannon.group);
      }
      fireCannon({ show, tray: this.dice, rig: rig ? this.cannon : null, seats: this.seatList, view: this.view, tableWidth: tableSize(this.seatList).w, still: this.quality === "low", now: performance.now() });
      return;
    }
    const seat = this.seatList.find((s) => s.player === show.actor) ?? this.seatList.find((s) => s.player === this.me);
    if (!seat) return;
    const player = this.view?.players.find((p) => p.id === seat.player);
    this.dice.clear(seat.player);
    // the roller's piles and cards, from the public view as every screen has them (table3d/diceEnv.ts)
    this.dice.throw(show, player?.color ?? "#d7ae63", player?.name ?? "", { x: seat.x, z: seat.z, rotY: seat.rot }, rollerEnv(this.view, seat.player, mirrored(seat)), performance.now());
  }

  /** The thrown dice now on the table (tests and diagnostics). */
  diceState(): ReturnType<DiceTray["describe"]> {
    return this.dice.describe();
  }

  /** -- table toys -- whether the dice cannon is out on the table, and where on screen (tests and diagnostics). */
  cannonState(): { busy: boolean; at: { x: number; y: number } | null } {
    const c = this.cannon;
    return { busy: !!c?.busy, at: c?.busy ? this.project(c.group.children[0]!.getWorldPosition(new THREE.Vector3())) : null };
  }

  /** A seat's life heart (its ▼ or ▲ half, or the middle) and my seat's buttons, on screen (tests and diagnostics). */
  heartOnScreen(player: string, side: -1 | 0 | 1 = 0): { x: number; y: number } | null {
    const p = this.props.heartWorld(player);
    if (!p) return null;
    if (side) {
      // the heart turns to face the camera: its halves lie across the view
      const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0).setY(0).normalize();
      p.addScaledVector(right, side * 0.42);
    }
    return this.project(p);
  }

  taxOnScreen(key: string): { x: number; y: number } | null {
    const p = this.props.taxWorld(key);
    return p ? this.project(p) : null;
  }

  buttonOnScreen(id: SeatActionId): { x: number; y: number } | null {
    const p = this.props.buttonWorld(id);
    return p ? this.project(p) : null;
  }

  /**
   * -- camera -- the lens eases to the goal's with the camera (wider when orbited below the view's pitch,
   * cameraControls.ts fovAt; the goal's distance was brought in to match, so the framing holds on the way).
   */
  private fitLens(k: number): void {
    const cam = this.camera;
    const fov = Math.abs(cam.fov - this.camGoalFov) < 1e-3 ? this.camGoalFov : cam.fov + (this.camGoalFov - cam.fov) * k;
    if (fov === cam.fov) return;
    cam.fov = fov;
    cam.updateProjectionMatrix();
  }

  /** -- flicker -- the near and far planes follow the camera's distance (framing.ts nearFarFor), so depth stays fine. */
  private fitDepth(): void {
    const { near, far } = nearFarFor(this.camera.position.distanceTo(this.camLook), this.camera.position.length());
    const cam = this.camera;
    if (Math.abs(cam.near - near) / near < 0.02 && Math.abs(cam.far - far) / far < 0.02) return;
    cam.near = near;
    cam.far = far;
    cam.updateProjectionMatrix();
  }

  /** Tests and diagnostics: hold the room's own motion (candle flicker, dust, beams' flow) so frames can be compared. */
  setStill(on: boolean): void {
    this.still = on;
  }
  private still = false;

  /** Tests and diagnostics: resolves once the next frame has been drawn. */
  nextFrame(): Promise<void> {
    return new Promise((resolve) => this.afterFrame.push(resolve));
  }
  private afterFrame: (() => void)[] = [];

  /** Tests and diagnostics: the next frame's pixels, read as soon as it is drawn. */
  grabFrame(): Promise<Uint8Array> {
    return new Promise((resolve) => this.grabs.push(resolve));
  }
  private grabs: ((px: Uint8Array) => void)[] = [];

  /** Table motion (tests and screenshots): freeze every running motion at a time in ms (null: live), and what is running. */
  motionFreeze(ms: number | null): void {
    this.motion.freeze(ms);
  }

  motionState(): ReturnType<TableMotion["state"]> {
    return this.motion.state();
  }

  /** The dice on the table, in screen coordinates (tests and diagnostics; `resting`: only those at rest, which the plates keep clear of). */
  diceOnScreen(resting = false): { x: number; y: number }[] {
    return this.dice.positions(resting).map((p) => this.project(p));
  }

  /**
   * Where a seat's player plate should be drawn on screen (for the DOM overlay): the middle of its right edge, against
   * its heart's left edge (the heart and plate read as one piece), and how many px one world unit spans there, so the
   * plate is drawn at its size on the table (layout.ts PLATE) and grows and shrinks with the zoom like the heart.
   */
  /**
   * -- seats -- how a seat's heart and its plate (pinned to the heart's left edge, as Table3D draws it) lie on screen for
   * camera `cam` with the heart at scale `f`: whether either reaches over the seat's own mat (past the mat's edge on
   * their side) or covers one of my seat buttons.
   */
  private pairOnScreen(cam: THREE.PerspectiveCamera, seat: Seat, f: number): { overMat: boolean; overButton: boolean } | null {
    const W = this.viewW;
    const H = this.viewH;
    const scr = (v: THREE.Vector3): [number, number] => {
      const p = v.clone().project(cam);
      return [((p.x + 1) / 2) * W, ((1 - p.y) / 2) * H];
    };
    type Rect = { left: number; right: number; top: number; bottom: number };
    const rectOf = (pts: [number, number][]): Rect => ({
      left: Math.min(...pts.map((p) => p[0])), right: Math.max(...pts.map((p) => p[0])),
      top: Math.min(...pts.map((p) => p[1])), bottom: Math.max(...pts.map((p) => p[1])),
    });
    const corners = this.props.heartCorners(seat.player, cam.position, f);
    if (!corners) return null;
    const heart = rectOf(corners.map(scr));
    // the plate: its size on the table, at the heart's scale, its right edge at the heart's left edge, centred on its middle
    const mid = corners.reduce((a, c) => a.add(c), new THREE.Vector3()).multiplyScalar(0.25);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion).setY(0).normalize();
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const edge = mid.clone().addScaledVector(right, -HEART.w * 0.47 * f);
    // (its size as Table3D last drew it, at the heart's full size; else its size on the table)
    const box = this.plateBoxes.get(seat.player);
    let plate: Rect;
    if (box) {
      const [ex, ey] = scr(edge);
      plate = { left: ex - (box.w + 4) * f, right: ex - 4 * f, top: ey - (box.h * f) / 2, bottom: ey + (box.h * f) / 2 };
    } else {
      const plateH = PLATE.h * 0.94 * f;
      plate = rectOf([0, 1].flatMap((sx) => [-1, 1].map((sy) => scr(edge.clone().addScaledVector(right, -sx * PLATE.w * f).addScaledVector(up, (sy * plateH) / 2)))));
    }
    // the mat's edge on their side
    const ez = heartSpot(seat)[1] > 0 ? MAT_D / 2 : -MAT_D / 2;
    const at = (lx: number, lz: number) => {
      const [x, z] = toWorld(seat, lx, lz);
      return scr(new THREE.Vector3(x, 0, z));
    };
    const matEdge: [[number, number], [number, number]] = [at(-MAT_W / 2, ez), at(MAT_W / 2, ez)];
    const matAbove = at(0, 0)[1] < scr(mid)[1];
    const clear = (r: Rect, gap: number) => {
      const y = (r.top + r.bottom) / 2;
      return offMat({ x: (r.left + r.right) / 2, y, w: r.right - r.left, h: r.bottom - r.top }, matEdge, matAbove, gap) === y;
    };
    const hits = (a: Rect, b: Rect) => !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
    const buttons = this.props.buttonDiscs().map(({ at: c, r }) => rectOf([-1, 1].flatMap((sx) => [-1, 1].map((sz) => scr(c.clone().add(new THREE.Vector3(sx * r, 0.08, sz * r)))))));
    return {
      overMat: !clear(heart, 2) || !clear(plate, 1),
      overButton: buttons.some((b) => hits(b, heart) || hits(b, plate)),
    };
  }

  /**
   * -- seats -- each heart's scale for where the camera is going: its size on the table, unless seen so low that it or
   * its plate would reach over its mat or cover a seat button; then as much smaller as that takes (down to half).
   */
  private fitHearts(): void {
    if (this.viewW < 2 || this.viewH < 2 || !this.seatList.length) return;
    const cam = this.goalCam;
    cam.copy(this.camera);
    tableLens(this.viewW, this.viewH, cam);
    cam.fov = this.camGoalFov;
    cam.updateProjectionMatrix();
    cam.position.copy(this.camGoalPos);
    cam.lookAt(this.camGoalLook);
    cam.updateMatrixWorld(true);
    for (const seat of this.seatList) {
      let fit = 0.5;
      for (let f = 1; f > 0.5; f -= 0.05) {
        const s = this.pairOnScreen(cam, seat, f);
        if (s && !s.overMat && !s.overButton) {
          fit = f;
          break;
        }
      }
      this.props.fitHeart(seat.player, fit);
    }
  }

  /**
   * -- seats -- each plate's size on screen (CSS px) as Table3D draws it with its heart at full size: the hearts are fitted
   * again when one changes (the plates follow the camera's distance, a moment behind it).
   */
  setPlateBoxes(boxes: Record<string, { w: number; h: number }>): void {
    let changed = false;
    for (const [pid, b] of Object.entries(boxes)) {
      const was = this.plateBoxes.get(pid);
      if (was && Math.abs(was.w - b.w) < 3 && Math.abs(was.h - b.h) < 3) continue;
      this.plateBoxes.set(pid, b);
      changed = true;
    }
    if (changed) this.fitHearts();
  }
  private plateBoxes = new Map<string, { w: number; h: number }>();

  /** Tests and diagnostics: each heart's scale now, and whether it or its plate reaches over its mat or a seat button. */
  pairState(): { player: string; fit: number; overMat: boolean; overButton: boolean }[] {
    return this.seatList.map((seat) => {
      const fit = this.props.heartFit(seat.player);
      const s = this.pairOnScreen(this.camera, seat, fit);
      return { player: seat.player, fit, overMat: s?.overMat ?? false, overButton: s?.overButton ?? false };
    });
  }

  seatScreen(player: string, width: number, height: number): {
    x: number; y: number; visible: boolean; edge: -1; pxPerUnit: number;
    /** The heart's scale now (its plate takes the same). */
    fit: number;
    /** The seat's mat's edge on the plate's side (its two ends), and whether the mat lies above it on screen. */
    matEdge: [[number, number], [number, number]]; matAbove: boolean;
  } | null {
    const seat = this.seatList.find((s) => s.player === player);
    if (!seat) return null;
    const edge = this.props.heartEdge(player, this.camera, -1);
    if (!edge) return null;
    const v = edge.clone().project(this.camera);
    const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0).setY(0).normalize();
    const u = edge.add(right).project(this.camera);
    const pxPerUnit = Math.hypot(((u.x - v.x) / 2) * width, ((u.y - v.y) / 2) * height);
    const screen = (lx: number, lz: number): [number, number] => {
      const [wx, wz] = toWorld(seat, lx, lz);
      const p = new THREE.Vector3(wx, 0, wz).project(this.camera);
      return [((p.x + 1) / 2) * width, ((1 - p.y) / 2) * height];
    };
    const ez = heartSpot(seat)[1] > 0 ? MAT_D / 2 : -MAT_D / 2;
    const y = ((1 - v.y) / 2) * height;
    return {
      x: ((v.x + 1) / 2) * width, y, visible: v.z < 1, edge: -1, pxPerUnit, fit: this.props.heartFit(player),
      matEdge: [screen(-MAT_W / 2, ez), screen(MAT_W / 2, ez)], matAbove: screen(0, 0)[1] < y,
    };
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

  /**
   * (tests) Other players' held fans: how many backs each draws, its count tag (0: none), whether it is still re-fanning,
   * and the box (page px) its cards will fill.
   */
  fanState(): { player: string; shown: number; tag: number; moving: boolean; box: { left: number; top: number; right: number; bottom: number } }[] {
    return [...this.handFans].map(([player, f]) => {
      const box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
      for (const p of f.goal.flatMap(fanCorners)) {
        const { x, y } = this.project(p);
        box.left = Math.min(box.left, x); box.right = Math.max(box.right, x); box.top = Math.min(box.top, y); box.bottom = Math.max(box.bottom, y);
      }
      return { player, shown: f.mesh.count, tag: f.tagCount, moving: f.moving, box };
    });
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
      const pile = pileAt(lx, lz, seat);
      if (pile) return { zone: `${seat.player}:${pile}`, position: "top" };
    }
    // the stack: the middle of the aisle between the rows
    if (Math.abs(p.z) < aisleOf(this.seatList) + 0.3 && Math.abs(p.x) < 2.2 && this.stackCenterFree()) return { zone: "stack" };
    return null;
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    for (const u of this.unsubs) u();
    this.motion.dispose();
    this.planar.dispose();
    this.end.dispose();
    this.dice.dispose();
    this.cannon?.dispose();
    this.diceHud.dispose();
    this.lifeBatch.dispose();
    this.typed.dispose();
    this.props.dispose();
    this.cursors.dispose();
    this.cursorOut.leave(); // (to the 2D table, say: my pointer leaves the 3D one)
    const gone = this.cursorOut.poll(performance.now());
    if (gone && this.sendsCursor()) useGame.getState().conn?.sendCursor(gone);
    this.clearTable();
    for (const c of this.cards.values()) this.disposeCard(c);
    this.cards.clear();
    for (const t of this.textures.values()) t.dispose();
    for (const m of this.materials.values()) m.dispose();
    for (const m of this.dimMats.values()) m.dispose();
    this.bodies.dispose();
    this.shadows.geometry.dispose();
    (this.shadows.material as THREE.Material).dispose();
    this.shadows.dispose();
    this.shadowTex.dispose();
    this.cardFaceGeo.dispose();
    this.fanGeo.dispose();
    this.cardBodyGeo.dispose();
    this.glowGeo.dispose();
    this.bodyMat.dispose();
    this.pileMat.dispose();
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
    this.fogBase = [30, 95 - e.fogDensity * 600];
    this.scene.fog = new THREE.Fog(fog, this.fogBase[0], this.fogBase[1]);
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
      p.tex.dispose();
      (p.slot.material as THREE.Material).dispose();
    }
    this.piles.clear();
    for (const f of this.handFans.values()) this.dropFan(f);
    this.handFans.clear();
  }

  private rebuildTable(): void {
    if (!this.seatList.length) return;
    this.clearTable();
    const size = tableSize(this.seatList);
    this.env = buildEnvironment(this.plane, size, this.quality, propSpots(this.seatList, size));
    this.world.add(this.env.group);
    for (const seat of this.seatList) {
      const color = this.view?.players.find((p) => p.id === seat.player)?.color ?? "#888";
      const mat = new THREE.Mesh(new THREE.PlaneGeometry(MAT_W + 0.5, MAT_D + 0.5), new THREE.MeshStandardMaterial({ map: matTexture(MAT_FELT, MAT_NAP, color), transparent: true, depthWrite: false, roughness: 1, envMapIntensity: 0.15, emissive: this.plane.ui.accent, emissiveIntensity: 0 }));
      mat.rotation.x = -Math.PI / 2;
      mat.rotation.z = seat.rot;
      const [mx, mz] = toWorld(seat, 0, 0);
      mat.position.set(mx, MAT_Y, mz);
      mat.receiveShadow = true;
      mat.renderOrder = -3; // the flat layers draw in a fixed order: mats, then contact shadows, then pile slots
      mat.userData = { mat: seat.player };
      this.world.add(mat);
      this.mats.set(seat.player, mat);
      for (const zone of Object.keys(PILES) as PileZone[]) {
        // in facing rows the far row's piles are mirrored: every library on my right, every command zone on my left
        const [lx, lz] = pileSpot(seat, zone);
        const [wx, wz] = toWorld(seat, lx, lz);
        // its well, sunk into the wood, and its nameplate under it as I see it (table3d/zoneWells.ts): one plane, upright
        // for me whoever's pile it is
        const duel = this.seatList.length === 2;
        const well = wellSize(zone);
        const art: WellArt = {
          zone, label: PILE_LABEL[zone as ZoneName] ?? zone, count: zone === "command" ? null : 0, duel, color, well,
          plateW: plateWidth(zone, duel), plateH: plateDepth(seat), plateDx: plateOffset(zone), stretch: wellStretch(duel, seat.side === "north"),
        };
        const piece = wellPiece(seat, [lx, lz], zone);
        const canvas = document.createElement("canvas");
        drawWell(canvas, art);
        const tex = canvasTexture(canvas);
        const [W, H] = wellCanvasSize(art);
        const slot = new THREE.Mesh(new THREE.PlaneGeometry(W / WELL_PX, H / WELL_PX), new THREE.MeshStandardMaterial({
          map: tex, transparent: true, depthWrite: false, roughness: 0.72, metalness: 0, envMapIntensity: 0.25, emissive: this.plane.ui.accent, emissiveIntensity: 0,
        }));
        slot.rotation.x = -Math.PI / 2;
        slot.rotation.z = this.myRot(); // its plate reads upright from my seat, whoever's pile it is
        const [px, pz] = toWorld(seat, ...piece.at);
        slot.position.set(px, SLOT_Y, pz);
        slot.renderOrder = -1;
        slot.receiveShadow = this.quality !== "low";
        slot.userData = { pile: zone, player: seat.player };
        const block = new THREE.Mesh(new THREE.BoxGeometry(CARD_W, 1, CARD_H), this.hitMat);
        block.rotation.y = seat.rot;
        block.position.set(wx, 0, wz);
        block.visible = false;
        block.userData = { pile: zone, player: seat.player };
        const layers = new THREE.InstancedMesh(this.cardBodyGeo, this.pileMat, PILE_LAYERS);
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
        this.piles.set(`${seat.player}:${zone}`, { block, slot, layers, top, count: -1, art, canvas, tex });
      }
      // the zone panels, as on the Oops I Baked a Pie table: beside each side of the mat, its surface, outlined in the
      // seat's colour, the zones in it outlined and marked in that colour too (zoneWells.ts)
      const columns: [PileZone, [number, number]][][] = [
        (["library", "graveyard", "exile"] as PileZone[]).map((z) => [z, pileSpot(seat, z)]),
        // (the command column as long as its commanders need: a partner's or background's well under the commander's)
        COMMAND_SLOTS.slice(0, Math.max(1, Math.min(COMMAND_SLOTS.length, this.view?.players.find((p) => p.id === seat.player)?.commanders.length ?? 1)))
          .map((_, i) => ["command", commandSlot(seat, i)]),
      ];
      for (const column of columns) {
        let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
        for (const [zone, at] of column) {
          const piece = wellPiece(seat, at, zone);
          const [cx, cz] = toWorld(seat, ...piece.at);
          x0 = Math.min(x0, cx - piece.w / 2); x1 = Math.max(x1, cx + piece.w / 2);
          z0 = Math.min(z0, cz - piece.h / 2); z1 = Math.max(z1, cz + piece.h / 2);
        }
        const pad = 0.14;
        const pw = x1 - x0 + 2 * pad;
        const ph = z1 - z0 + 2 * pad;
        const strip = new THREE.Mesh(new THREE.PlaneGeometry(pw, ph), zonePanelMaterial(color, pw, ph));
        strip.rotation.x = -Math.PI / 2;
        strip.position.set((x0 + x1) / 2, SLOT_Y - 0.0006, (z0 + z1) / 2);
        strip.renderOrder = -2;
        strip.receiveShadow = this.quality !== "low";
        this.world.add(strip);
      }
    }
    // drawn again once the wells' fonts are in (they normally are by now)
    void whenWellFontsReady().then(() => {
      for (const p of this.piles.values()) {
        drawWell(p.canvas, p.art);
        p.tex.needsUpdate = true;
      }
    });
  }

  // ------------------------------------------------------------------ textures & materials


  private backMaterial(owner: string): THREE.MeshStandardMaterial {
    const player = this.view?.players.find((p) => p.id === owner);
    const sleeve = player?.sleeve ? this.view?.game.assets?.[player.sleeve]?.url : undefined;
    const key = `back:${owner}:${sleeve ?? ""}:${player?.color ?? ""}`;
    let m = this.materials.get(key);
    if (!m) {
      // a sleeve, else the Magic card back the host caches (cards/cardBack.ts), else the back drawn here meanwhile
      const tex = this.loadTexture(sleeve ?? CARD_BACK_URL, sleeve ? () => this.loadTexture(CARD_BACK_URL, this.drawnBack) : this.drawnBack);
      // trimmed to the card's rounded corners: the real back's image has square white ones (as a sleeve photo may)
      m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55, alphaMap: cardCornerMask(), alphaTest: 0.5 });
      this.materials.set(key, m);
    }
    if (!this.backWatch) {
      // the host may fetch the real back after the table opened (it was offline then): every drawn back turns into it
      this.backWatch = onCardBack(() => {
        if (!checkCardBack.ready()) return;
        this.failed.delete(CARD_BACK_URL);
        for (const mat of this.materials.values()) {
          if (!this.drawnBackTex || mat.map !== this.drawnBackTex) continue;
          mat.map = this.loadTexture(CARD_BACK_URL, this.drawnBack);
          mat.needsUpdate = true;
        }
      });
      this.unsubs.push(this.backWatch);
    }
    return m;
  }

  /** The drawn back (cards/drawnBack.ts), one texture for every seat (kept with the textures, so disposed with them). */
  private drawnBack = (): THREE.Texture => {
    if (!this.drawnBackTex) this.textures.set("drawn:card-back", (this.drawnBackTex = canvasTexture(backCanvas())));
    return this.drawnBackTex;
  };
  private drawnBackTex: THREE.Texture | null = null;
  private backWatch: (() => void) | null = null;

  private loadTexture(url: string, fallback: () => THREE.Texture): THREE.Texture {
    const cached = this.textures.get(url);
    if (cached) return cached;
    if (this.failed.has(url)) return fallback();
    const failed = () => {
      this.failed.add(url);
      this.textures.delete(url);
      // swap every material using it for the fallback
      for (const [k, m] of this.materials) if (m.map === tex) { m.map = fallback(); m.needsUpdate = true; void k; }
    };
    // (the Magic card back with its square white corners painted black, so none shows at the card's rounded corners)
    const tex = url === CARD_BACK_URL ? cardImageTexture(url, failed) : this.loader.load(url, undefined, undefined, failed);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
    this.textures.set(url, tex);
    return tex;
  }

  /**
   * -- arranged boards -- how a tile's name is drawn (table3d/tiles.ts): tall enough to read upright at the seat view's
   * slant, and the same size on screen on every tile in the seat view (measured once per screen and seating, not as
   * the player moves the camera).
   */
  private tileLookFor(id: string): TileLook {
    const spot = this.placed.get(id);
    const tv = this.tileView();
    return spot && tv ? tileLook(spot.w * tv.ppu, tv.squash, nameScreenEm(tv.ppu)) : FLAT_LOOK;
  }
  private tileViewKey = "";
  private tileViewVal: { ppu: number; squash: number } | null = null;
  /** The seat view's scale at the middle of the table: CSS px per world unit across, and how foreshortened its depth is. */
  private tileView(): { ppu: number; squash: number } | null {
    const mine = this.seatList.find((s) => s.player === this.me);
    if (!mine || this.viewW < 2 || this.viewH < 2) return null;
    const key = `${this.seatKey}|${this.viewW}x${this.viewH}|${this.reserveTop}|${this.keepKey}`;
    if (key === this.tileViewKey) return this.tileViewVal;
    const f = this.fitView("seat", mine);
    if (!f) return null;
    const cam = this.fitCam;
    cam.copy(this.camera);
    tableLens(this.viewW, this.viewH, cam);
    cam.position.copy(f.pos);
    cam.lookAt(f.look);
    cam.updateMatrixWorld(true);
    const at = (lx: number, lz: number): THREE.Vector2 => {
      const [dx, dz] = toWorld({ ...mine, x: 0, z: 0 }, lx, lz);
      const p = new THREE.Vector3(f.look.x + dx, 0, f.look.z + dz).project(cam);
      return new THREE.Vector2((p.x * this.viewW) / 2, (p.y * this.viewH) / 2);
    };
    const across = at(-0.5, 0).distanceTo(at(0.5, 0));
    const deep = at(0, -0.5).distanceTo(at(0, 0.5));
    this.tileViewKey = key;
    this.tileViewVal = { ppu: across, squash: deep / Math.max(1e-6, across) };
    return this.tileViewVal;
  }

  /** -- arranged boards -- tile textures no card shows any more (a look for another screen, a card gone): freed. */
  private dropUnusedTiles(): void {
    const used = new Set<string>();
    for (const c of this.cards.values()) if (c.faceKey.startsWith("tile:")) used.add(c.faceKey.replace(/\|tapped$/, ""));
    let n = 0;
    for (const k of this.textures.keys()) if (k.startsWith("tile:")) n++;
    if (n <= used.size + 24) return;
    for (const [k, t] of [...this.textures]) {
      if (!k.startsWith("tile:") || used.has(k)) continue;
      t.dispose();
      this.textures.delete(k);
      for (const mk of [k, `${k}|tapped`]) {
        const m = this.materials.get(mk);
        if (!m) continue;
        this.dimMats.get(m)?.dispose();
        this.dimMats.delete(m);
        m.dispose();
        this.materials.delete(mk);
      }
    }
  }

  private faceKeyFor(card: GameCard): string {
    if (!isVisible(card) || card.face_down) return `back:${card.owner}`;
    if (card.ability) {
      // a triggered or activated ability: its source's art and its text (as the 2D table's GameCardFace)
      const src = card.ability.source_card_id ? useCardCache.getState().cards[card.ability.source_card_id] : undefined;
      return `ability:${card.ability.source_card_id ?? ""}:${src?.has_image ? "img" : "txt"}:${card.ability.kind}:${card.ability.source_name ?? ""}:${card.ability.text}`;
    }
    const data = card.card_id ? useCardCache.getState().cards[card.card_id] : undefined;
    // -- engine token art -- a described token pictured by a token printing: that picture, once it is known to be here
    const artId = tokenArtId(card);
    const art = artId ? useCardCache.getState().cards[artId] : undefined;
    const look = data ? (data.has_image ? "img" : "txt") : art?.has_image ? `art-${art.id}-${tokenArtFace(card)}` : "pending";
    // -- arranged boards -- an art tile (table3d/tiles.ts): what it shows is its key; a tapped one is a shade darker
    if (this.placed.has(card.id)) {
      const t = card.card_id ? "" : JSON.stringify([card.token?.type_line, card.token?.power, card.token?.toughness, card.token?.colors]);
      const l = this.tileLookFor(card.id);
      const bare = this.placed.get(card.id)?.under ? 1 : 0;
      return `tile:${card.card_id ?? card.name}:${card.face}:${look}:${card.commander_key ? 1 : 0}:${card.is_token ? 1 : 0}:${l.stretch}:${l.em}:${bare}:${t}${card.tapped ? "|tapped" : ""}`;
    }
    return `front:${card.card_id ?? card.name}:${card.face}:${look}`;
  }

  private faceMaterial(card: GameCard, key: string): THREE.MeshStandardMaterial {
    if (key.startsWith("back:")) return this.backMaterial(card.owner);
    let m = this.materials.get(key);
    if (m) return m;
    if (key.startsWith("tile:")) return this.tileMaterial(card, key);
    if (key.startsWith("ability:") && isVisible(card) && card.ability) {
      const id = card.ability.source_card_id;
      const art = id && useCardCache.getState().cards[id]?.has_image ? imageUrl(id, 0, "normal") : null;
      m = new THREE.MeshStandardMaterial({ map: abilityCardTexture(card.ability, art), roughness: 0.95, metalness: 0, envMapIntensity: 0.12 });
      this.materials.set(key, m);
      return m;
    }
    const vis = card as Extract<GameCard, { hidden?: undefined }>;
    const data = vis.card_id ? useCardCache.getState().cards[vis.card_id] : undefined;
    const text = () => textCardTexture(data, vis.face ?? 0, vis.name);
    const artId = tokenArtId(card); // -- engine token art --
    let tex: THREE.Texture;
    if (data?.has_image) {
      const imgFace = data.double_faced ? Math.min(vis.face ?? 0, data.image_faces - 1) : 0;
      tex = this.loadTexture(imageUrl(data.id, imgFace, this.quality === "low" ? "small" : "normal"), text);
    } else if (!data && artId && useCardCache.getState().cards[artId]?.has_image) {
      tex = this.loadTexture(imageUrl(artId, tokenArtFace(card), this.quality === "low" ? "small" : "normal"), text);
    } else tex = text();
    // printed card stock with a faint satin sheen from the room reflections
    // matte card stock: a glossy face catches the overhead light and washes the art out
    m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0, envMapIntensity: 0.12 });
    this.materials.set(key, m);
    return m;
  }

  /** -- arranged boards -- a tile's material: one texture per distinct tile, shared; tapped, the same texture a shade darker. */
  private tileMaterial(card: GameCard, key: string): THREE.MeshStandardMaterial {
    const base = key.replace(/\|tapped$/, "");
    let m = this.materials.get(base);
    if (!m) {
      const vis = card as Extract<GameCard, { hidden?: undefined }>;
      const data = vis.card_id ? useCardCache.getState().cards[vis.card_id] : undefined;
      const imgFace = data?.double_faced ? Math.min(vis.face ?? 0, data.image_faces - 1) : 0;
      const artId = tokenArtId(card); // -- engine token art -- the picture only; the tile's words stay the token's
      const art = data?.has_image ? imageUrl(data.id, imgFace, "normal")
        : artId && useCardCache.getState().cards[artId]?.has_image ? imageUrl(artId, tokenArtFace(card), "normal") : null;
      const t = vis.token;
      const custom = !vis.card_id && t ? { name: t.name, type_line: t.type_line, oracle_text: t.text, power: t.power, toughness: t.toughness, colors: t.colors } : undefined;
      const tex = tileTexture({ data, face: vis.face ?? 0, name: vis.name, custom, art, token: !!vis.is_token, commander: !!vis.commander_key, look: this.tileLookFor(card.id), bare: !!this.placed.get(card.id)?.under },
        this.quality === "low" ? 224 : TILE_PX, this.renderer.capabilities.getMaxAnisotropy());
      this.textures.set(base, tex);
      m = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0, envMapIntensity: 0.12 });
      this.materials.set(base, m);
    }
    if (base === key) return m;
    const dark = m.clone();
    dark.color.setScalar(0.74);
    this.materials.set(key, dark);
    return dark;
  }

  // ------------------------------------------------------------------ cards

  private makeCard(id: string): CardObj {
    const group = new THREE.Group();
    const face = new THREE.Mesh(this.cardFaceGeo, this.bodyMat);
    face.position.y = THICK + FACE_LIFT;
    face.userData = { card: id };
    face.receiveShadow = this.quality !== "low";
    const glow = new THREE.Mesh(this.glowGeo, new THREE.MeshBasicMaterial({ color: "#fff", transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    glow.position.y = -0.001;
    group.add(glow, face);
    this.world.add(group);
    const obj: CardObj = { id, group, face, glow, overlay: null, overlayKey: "", faceKey: "", target: new THREE.Vector3(), rot: 0, tilt: 0, scale: 1, seen: true, fresh: true };
    this.cards.set(id, obj);
    return obj;
  }

  private disposeCard(c: CardObj): void {
    this.world.remove(c.group);
    (c.glow.material as THREE.Material).dispose();
    this.clearOverlay(c);
    this.setBadge(c, 0);
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
    // a free pile's ×N is its own badge, kept readable from the default camera (an arranged tile draws it in its overlay)
    const pile = !c.tile ? o?.pile ?? 0 : 0;
    this.setBadge(c, pile);
    if (pile && o) {
      const { pile: _n, ...rest } = o;
      o = rest.pt || rest.damage || rest.chain || rest.owner || rest.keywords.length || rest.counters.length ? rest : null;
    }
    const look = c.tile ? this.tileLookFor(c.id) : FLAT_LOOK;
    const key = o ? `${c.tile ? `tile${look.stretch}` : ""}${JSON.stringify(o)}` : "";
    if (c.overlayKey === key) return;
    c.overlayKey = key;
    this.clearOverlay(c);
    if (!o) return;
    const mat = new THREE.MeshBasicMaterial({
      // -- arranged boards -- a tile's badges are laid out for its proportions (table3d/tiles.ts)
      map: canvasTexture(c.tile ? tileOverlayCanvas(o, 256, look) : cardOverlayCanvas(o)), transparent: true, depthWrite: false, toneMapped: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    });
    const m = new THREE.Mesh(this.cardFaceGeo, mat);
    m.position.y = THICK + FACE_LIFT * 2;
    m.renderOrder = 2;
    c.group.add(m);
    c.overlay = m;
  }

  /** -- token piles -- the ×N badge on a pile's top card (0: none); loop() sizes and turns it (sizeBadges). */
  private setBadge(c: CardObj, n: number): void {
    if ((c.badgeN ?? 0) === n) return;
    c.badgeN = n;
    if (c.badge) {
      c.group.remove(c.badge);
      const m = c.badge.material as THREE.MeshBasicMaterial;
      m.map?.dispose();
      m.dispose();
      c.badge = null;
    }
    if (!n) return;
    const canvas = pileBadgeCanvas(n);
    const mat = new THREE.MeshBasicMaterial({ map: canvasTexture(canvas), transparent: true, depthWrite: false, toneMapped: false,
      polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
    const m = new THREE.Mesh(this.badgeGeo, mat);
    m.position.y = THICK + FACE_LIFT * 3;
    m.renderOrder = 3;
    m.raycast = () => undefined; // (clicks go to the card under it)
    m.userData = { aspect: canvas.width / canvas.height };
    c.group.add(m);
    c.badge = m;
  }

  /**
   * -- token piles -- each ×N badge keeps at least PILE_BADGE_PX of height on screen however far the camera is (bigger on a
   * near card, never past a cap), reads upright from my seat, and sits on the corner of its card that is top right from
   * here, half hanging off it so it covers as little of the art as it can.
   */
  private sizeBadges(): void {
    const h = this.canvas.clientHeight; // (NDC spans the canvas, a view offset or not)
    if (!h) return;
    const mine = this.myRot();
    for (const c of this.cards.values()) {
      const b = c.badge;
      if (!b || !c.group.visible) continue;
      // screen pixels per world unit of depth at the card (toward the camera, along the table: foreshortening included)
      const at = c.group.position;
      badgeA.copy(at).project(this.camera);
      badgeDir.set(this.camera.position.x - at.x, 0, this.camera.position.z - at.z);
      if (badgeDir.lengthSq() < 1e-9) badgeDir.set(0, 0, 1);
      badgeB.copy(at).addScaledVector(badgeDir.normalize(), 0.5).project(this.camera);
      const pxPerUnit = Math.hypot(((badgeA.x - badgeB.x) / 2) * this.canvas.clientWidth, ((badgeA.y - badgeB.y) / 2) * h) / 0.5;
      const bh = Math.min(BADGE_MAX_H, Math.max(BADGE_MIN_H, pxPerUnit > 0 ? PILE_BADGE_PX / pxPerUnit : BADGE_MAX_H));
      const bw = bh * (b.userData.aspect as number);
      const gs = c.group.scale.x || 1;
      // turned from the card's frame to mine: the badge reads upright, on the corner that is top right from my seat
      const r = mine - c.group.rotation.y;
      const at2 = pileBadgeSpot(r, bw, bh, CARD_W, CARD_H);
      b.position.x = at2.x / gs;
      b.position.z = at2.z / gs;
      b.rotation.y = r;
      b.scale.set(bw / gs, 1, bh / gs);
    }
  }

  private place(c: CardObj, seat: Seat | undefined, lx: number, lz: number, y: number, extraRot = 0): void {
    c.scale = 1;
    c.tile = false;
    c.squash = 1;
    // -- arranged boards -- a battlefield card goes to its tile's spot, turned to read from my seat; its height follows
    // the tile's stacking (a stack's top card, a host over its Equipment) plus any lift the table gave it
    const spot = seat && this.placed.get(c.id);
    if (spot) {
      c.tile = true;
      c.squash = TILE_SQUASH;
      c.scale = tileScale(spot.w);
      c.target.set(spot.x, 0.004 + spot.rank * 0.0035 + Math.max(0, y - (0.004 + spot.index * 0.0035)), spot.z);
      c.rot = spot.rot + extraRot;
      return;
    }
    if (seat) {
      const [wx, wz] = toWorld(seat, lx, lz);
      c.target.set(wx, y, wz);
      // arranged, every card on the table reads from my seat (the piles' tops and the command zone too)
      c.rot = (this.arranged ? this.myRot() : seat.rot) + extraRot;
    } else {
      c.target.set(lx, y, lz);
      c.rot = extraRot;
    }
  }

  private myRot(): number {
    return this.seatList.find((s) => s.player === this.me)?.rot ?? 0;
  }

  private syncCards(): void {
    const view = this.view;
    if (!view) return;
    this.motion.layout();
    // -- arranged boards -- every mat's rows, laid out again only where something changed (table3d/arrange3d.ts)
    this.placed = this.arranged ? this.boards.layout(view, this.seatList, this.me, {
      data: (cid) => useCardCache.getState().cards[cid],
      version: useCardCache.getState().cards,
      order: (zone) => boardOrder(view.game.id, zone),
    }, this.keepOut) : new Map();
    for (const c of this.cards.values()) {
      c.seen = false;
      c.cover = undefined;
    }
    const seatOf = new Map(this.seatList.map((s) => [s.player, s]));
    const store = useGame.getState();
    const selection = new Set(store.selection);
    this.selectedIds = selection;
    this.beams = targetBeams(view, this.me);
    // -- combat filter -- (game/combatFilter.ts) the cards it leaves lit, worked out here once per sync: dimming is a material swap, no per-frame cost
    const lit = litCards(view, this.me, usePrefs.getState().combatFilter);
    const pending = store.pendingPositions;
    const need: string[] = [];
    const show = (id: string): CardObj | null => {
      const card = view.cards[id];
      if (!card) return null;
      const c = this.cards.get(id) ?? this.makeCard(id);
      c.seen = true;
      if (isVisible(card) && card.card_id && !useCardCache.getState().cards[card.card_id]) need.push(card.card_id);
      const artId = tokenArtId(card); // -- engine token art --
      if (artId && !useCardCache.getState().cards[artId]) need.push(artId);
      const src = isVisible(card) ? card.ability?.source_card_id : null;
      if (src && !useCardCache.getState().cards[src]) need.push(src);
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
      const piles = this.arranged ? this.boards.piles(pid) : zonePileTops(view, `${pid}:battlefield`);
      // -- token piles -- what lies wholly under another card (a pile's buried cards) is hidden; a raised card (selected, a
      // targeting choice, on its way somewhere) neither hides nor is hidden
      const tb0 = this.beams;
      const lifted = (id: string) => selection.has(id) || !!tb0?.cands.has(id) || id === tb0?.source || !!pending[id];
      // (nor is a card something is attached to: its tethers lead to it)
      const hosts = new Set<string>();
      for (const id of bf) {
        const a = view.cards[id];
        if (a && isVisible(a) && a.attached_to) hosts.add(a.attached_to);
      }
      const covers = this.arranged ? null : freeCovers(bf.flatMap((id, i) => {
        const card = view.cards[id];
        if (!card) return [];
        const [x, y] = pending[id] ?? [card.x ?? 20 + (i % 10) * 90, card.y ?? 20 + Math.floor(i / 10) * 130];
        return [{ id, x, y, turn: (card.tapped ? 1 : 0) + (card.flipped ? 2 : 0) + (card.rotation ?? 0) * 4, lifted: lifted(id) || hosts.has(id) }];
      }));
      bf.forEach((id, i) => {
        const card = view.cards[id];
        const c = show(id);
        if (!card || !c) return;
        const pos = pending[id] ?? [card.x ?? 20 + (i % 10) * 90, card.y ?? 20 + Math.floor(i / 10) * 130];
        const [lx, lz] = virtualToLocal(pos[0], pos[1]);
        const tapped = (card.tapped ? -Math.PI / 2 : 0) + (card.flipped ? Math.PI : 0) - ((card.rotation ?? 0) * Math.PI) / 180;
        // -- targeting -- the choices lift off the felt (the one pointed at or chosen more), the rest darkens
        const tb = this.beams;
        const lift = tb?.cands.has(id) ? (tb.targets.includes(id) ? 0.16 : 0.06) : 0;
        this.place(c, seat, lx, lz, 0.004 + i * 0.0035 + lift, tapped);
        const under = covers ? covers.get(id) : this.placed.get(id)?.cover;
        c.cover = under && !lifted(id) && !lifted(under) ? under : undefined;
        const face = this.faceMaterial(card, c.faceKey);
        const want = (tb && !tb.cands.has(id) && id !== tb.source) || (lit && !lit.has(id) && !selection.has(id)) ? this.dimmed(face) : face;
        if (c.face.material !== want) c.face.material = want;
        c.tilt = 0;
        // a stack member under its top card wears no badges (the top card carries the ×N and speaks for the stack)
        // (nor does a hidden one: 200 tokens with a counter each would be 200 badge textures)
        const overlay = c.cover || (c.tile && this.placed.get(id)?.under) ? null : overlayFor(card, view.rules?.stats?.[id], c.tile);
        const pile = countMark(card, piles.get(id))?.n; // ×N: the land pile it tops, or the token stack it is
        const ownerP = card.owner !== card.controller ? view.players.find((p) => p.id === card.owner) : undefined;
        const owner = ownerP ? { initial: ownerP.name.slice(0, 1).toUpperCase(), color: ownerP.color } : undefined;
        this.setOverlay(c, pile || owner ? { ...(overlay ?? { keywords: [], counters: [] }), ...(pile ? { pile } : {}), ...(owner ? { owner } : {}) } : overlay);
        this.setGlow(c, selection.has(id) ? this.plane.ui.frameHi : this.legalColor(view, id), selection.has(id) || tb?.cands.has(id) ? 0.9 : 0.55); // brass: the selected card's edge (DESIGN.md); ice means priority
      });
      // piles
      for (const zone of ["library", "graveyard", "exile"] as const) {
        const z = view.zones[`${pid}:${zone}`];
        const count = Array.isArray(z) ? z.length : (z as LibraryView | undefined)?.count ?? 0;
        const pile = this.piles.get(`${pid}:${zone}`);
        if (pile && pile.count !== count) {
          pile.count = count;
          // its nameplate's count (public: everyone sees how many cards each library, graveyard and exile holds)
          pile.art.count = count;
          drawWell(pile.canvas, pile.art);
          pile.tex.needsUpdate = true;
          // graveyard and exile draw their top card for real, so the stack below has one fewer
          this.stackPile(seat, zone, pile, zone === "library" ? count : Math.max(0, count - 1));
        }
        if (zone !== "library" && Array.isArray(z) && z.length) {
          const top = z[z.length - 1]!;
          const c = show(top);
          if (c && seat) {
            const [lx, lz] = pileSpot(seat, zone);
            this.place(c, seat, lx, lz, pileHeight(z.length - 1) + 0.002, 0);
            this.setOverlay(c, null);
            this.setGlow(c, selection.has(top) ? this.plane.ui.select : null, 0.9);
          }
        }
      }
      // command zone: each commander in its own slot (a partner's above), anything else after them
      const cmd = (view.zones[`${pid}:command`] as string[] | undefined) ?? [];
      const keys = view.players.find((p) => p.id === pid)?.commanders.map((c) => c.instance_id) ?? [];
      // the command slot fades and lights like the other piles (its count is what's in the zone)
      const cmdPile = this.piles.get(`${pid}:command`);
      if (cmdPile) {
        cmdPile.count = cmd.length;
        // the commander's tax to pay on its well's plate (zoneWells.ts WellArt.tax; its coins stand beside: seatProps.ts)
        const tax = view.players.find((p) => p.id === pid)?.commanders[0]?.tax ?? 0;
        if ((cmdPile.art.tax ?? 0) !== tax) {
          cmdPile.art.tax = tax;
          drawWell(cmdPile.canvas, cmdPile.art);
          cmdPile.tex.needsUpdate = true;
        }
      }
      let extra = 0;
      const [cx, cz] = commandSlot(seat, 0);
      cmd.forEach((id) => {
        const c = show(id);
        if (!c) return;
        const slot = keys.indexOf(id);
        const at = slot >= 0 && slot < COMMAND_SLOTS.length ? commandSlot(seat, slot) : null;
        const [lx, lz] = at ?? [cx + Math.sign(cx) * (++extra) * (CARD_W + 0.12), cz];
        this.place(c, seat, lx, lz, 0.004, 0);
        this.setOverlay(c, null);
        this.setGlow(c, selection.has(id) ? this.plane.ui.frameHi : this.legalColor(view, id), 0.6);
      });
      // other players' hands: a fan of backs held up at their edge (count only)
      if (showsFan(seat, this.me)) this.syncHandFan(seat, ((view.zones[`${pid}:hand`] as string[] | undefined) ?? []).length);
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
    // laid nearly flat in the aisle between the rows, so no stack card stands up over anyone's front row: centred and
    // sized to fit a pod's wide aisle; a duel's aisle is too narrow for a readable card, so there the stack lies at the
    // aisle's left end (the arranged rows are centred, so that corner is the last to fill)
    const aisle = aisleOf(this.seatList) * 2 - 0.25;
    const tilt = 0.3; // far edge raised a little: the face turns toward my seat
    const fit = aisle / (CARD_H * Math.cos(tilt));
    const narrow = fit < 1.7;
    const topScale = narrow ? 1.7 : Math.min(2.25, fit);
    const restScale = topScale * 0.82;
    const spacing = step * (topScale / 2.25);
    const x0 = narrow ? -(MAT_W / 2 - (CARD_W * topScale) / 2 - 0.3) + ((n - 1) / 2) * spacing : 0;
    view.stack.forEach((id, i) => {
      const c = show(id);
      if (!c) return;
      const top = i === n - 1;
      const x = x0 + (i - (n - 1) / 2) * spacing;
      const z = 0;
      const wx = x * Math.cos(myRot) + z * Math.sin(myRot);
      const wz = -x * Math.sin(myRot) + z * Math.cos(myRot);
      const scale = top ? topScale : restScale;
      const y = (top ? 0.42 : 0.3) + i * 0.02;
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
        this.motion.forget(c); // (where it was, for a flight to wherever it went)
        this.disposeCard(c);
        this.cards.delete(id);
      }
    }
    this.dropUnusedTiles();
    if (need.length) requestCards(need);
    this.stats.cards = this.cards.size;
    // a refused action's card glows red for a moment (static: no motion to reduce)
    const err = store.errorCard;
    const errObj = err && Date.now() - err.at < ERROR_MS ? this.cards.get(err.id) : undefined;
    if (errObj) this.setGlow(errObj, "#ff5a4a", 1);
    this.layoutCombat(view);
    this.syncArrows(view);
    this.syncTethers();
    // a stack or combat close-up follows the stack and the fight as they change
    if (typeof this.preset === "object" && ("stack" in this.preset || "combat" in this.preset)) this.updateCameraGoal();
  }

  /** Attachment cords for whatever is hovered or selected (game/attachments.ts); rebuilt only when one changes. */
  private syncTethers(): void {
    const view = this.view;
    if (!view) return;
    const store = useGame.getState();
    const links = attachmentLinks(view, [store.hover, ...store.selection]);
    const ends: [THREE.Vector3, THREE.Vector3][] = [];
    const foot = (c: CardObj) => ({ x: c.target.x, y: c.target.z, hw: (CARD_W / 2) * c.scale, hh: (CARD_H / 2) * c.scale, rot: -c.rot });
    // just over the card's face, as high as the hover or selection lift carries it
    const top = (c: CardObj) => c.target.y + liftFor({ hovered: c.id === this.hovered, selected: this.selectedIds.has(c.id), turning: 0 }) + THICK + 0.012;
    for (const l of links) {
      const a = this.cards.get(l.from);
      const h = l.player ? undefined : this.cards.get(l.to);
      // an Aura enchanting a player ends at their life heart
      const seat = l.player ? this.seatList.find((s) => s.player === l.to) : undefined;
      if (!a || (!h && !seat)) continue;
      const [hx, hz] = seat ? toWorld(seat, ...heartSpot(seat)) : [0, 0];
      const b = h ? h.target.clone().setY(top(h)) : new THREE.Vector3(hx, 0.05, hz);
      // a tucked attachment's line starts on the part of it that peeks out from under the host
      const p = h ? tetherAnchor(foot(a), foot(h)) : { x: a.target.x, y: a.target.z };
      ends.push([new THREE.Vector3(p.x, top(a), p.y), b]);
    }
    const key = ends.map(([a, b]) => `${a.x.toFixed(2)},${a.z.toFixed(2)},${a.y.toFixed(2)}>${b.x.toFixed(2)},${b.z.toFixed(2)},${b.y.toFixed(2)}`).join("|");
    if (key === this.tetherKey) return;
    this.tetherKey = key;
    for (const child of [...this.tethers.children]) {
      this.tethers.remove(child);
      (child.userData.dispose as () => void)();
    }
    for (const [a, b] of ends) this.tethers.add(makeTether(a, b));
  }

  /**
   * Combat as a formation (presentation only; stored positions never change): each attacker marches
   * out into the open wood beyond its mat, side by side with the others attacking the same player
   * and facing them; each blocker steps up directly in front of the attacker it blocks.
   */
  private layoutCombat(view: GameView): void {
    // -- arranged boards -- attackers and blockers stay in their rows, stepping forward, as on Arena; arrows say whom
    // they attack (syncArrows)
    if (this.arranged) return;
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
      if (id === MY_HAND) { // my hand's edge of the table (the hand itself is on the screen, not the table)
        const mine = this.seatList.find((s) => s.player === this.me);
        if (!mine) return null;
        const [hx, hz] = toWorld(mine, 0, MAT_D / 2 + 0.5);
        return new THREE.Vector3(hx, 0.35, hz);
      }
      const seat = this.seatList.find((s) => s.player === id);
      if (!seat) return null;
      // a player: their plaque (as Arena lands on the avatar), spread a little so several
      // attackers' crystals sit side by side
      const spread = from ? Math.max(-0.7, Math.min(0.7, toLocal(seat, from.x, from.z)[0] * 0.12)) : 0;
      const [hx, hz] = heartSpot(seat);
      const [wx, wz] = toWorld(seat, hx + spread, hz);
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
      if (c.attacking && (c.attacking.kind !== "player" || this.arranged)) add(c.id, c.attacking.id, ATTACK_RED, true);
      if (c.blocking) for (const t of [c.blocking, ...(c.blocking_more ?? [])]) add(c.id, t, "#5fa8ff", true);
    }
    // -- targeting -- from the source (or my hand, where the spell is) to the hovered and the chosen candidates, in brass
    const beams = this.beams;
    if (beams) for (const t of beams.targets) add(beams.source && this.cards.has(beams.source) ? beams.source : MY_HAND, t, this.plane.ui.accent2);
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

  /**
   * Another player's hand: a fan of backs held up at their own edge of the table (table3d/handFan.ts), count only. A
   * new count re-fans it: the cards it keeps ease to their new places, a drawn card slides out from behind the last
   * one, a card that left is gone at once (its flight, if any, is the table motion's). Snaps under reduced motion.
   */
  private syncHandFan(seat: Seat, count: number): void {
    let fan = this.handFans.get(seat.player);
    const mat = this.backMaterial(seat.player);
    if (fan) {
      fan.mesh.material = mat; // (a sleeve may have changed)
      if (fan.count === count) return;
    }
    const goal = handFan(seat, count);
    if (!fan) {
      const mesh = new THREE.InstancedMesh(this.fanGeo, mat, FAN_MAX);
      mesh.castShadow = this.quality !== "low";
      mesh.frustumCulled = false; // (its bounds are its instances', which move)
      mesh.userData.fan = seat.player;
      this.world.add(mesh);
      // a table that opens with cards in hand shows them held, not dealt
      fan = { mesh, count, cur: refanFrom(goal, goal), goal, moving: true, tag: null, tagCount: -1 };
      this.handFans.set(seat.player, fan);
    } else {
      fan.cur = refanFrom(fan.cur, goal);
      fan.goal = goal;
      fan.count = count;
      fan.moving = true;
    }
    fan.mesh.count = goal.length;
    this.syncFanTag(fan, count);
  }

  /** The count tag over a fan whose hand is bigger than FAN_MAX (a sprite: it faces whoever looks). */
  private syncFanTag(fan: HeldFan, count: number): void {
    const want = count > FAN_MAX ? count : 0;
    if (want === fan.tagCount) return;
    fan.tagCount = want;
    this.dropFanTag(fan);
    const at = fanTag(fan.goal);
    if (!want || !at) return;
    const tex = canvasTexture(handCountCanvas(want));
    const tag = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false }));
    tag.scale.set(0.62, 0.372, 1);
    tag.position.copy(at);
    tag.renderOrder = 5;
    this.world.add(tag);
    fan.tag = tag;
  }

  private dropFanTag(fan: HeldFan): void {
    if (!fan.tag) return;
    this.world.remove(fan.tag);
    const m = fan.tag.material as THREE.SpriteMaterial;
    m.map?.dispose();
    m.dispose();
    fan.tag = null;
  }

  /** Each frame: the fans still moving ease toward their goals (k: this frame's share of the way; 1 under reduced motion). */
  private tickFans(k: number): void {
    for (const fan of this.handFans.values()) {
      if (!fan.moving) continue;
      fan.moving = !easeFan(fan.cur, fan.goal, k);
      for (let i = 0; i < fan.cur.length; i++) {
        const c = fan.cur[i]!;
        fanM.compose(c.pos, c.quat, ONE);
        fan.mesh.setMatrixAt(i, fanM);
      }
      fan.mesh.instanceMatrix.needsUpdate = true;
    }
  }

  private dropFan(fan: HeldFan): void {
    this.world.remove(fan.mesh);
    fan.mesh.dispose();
    this.dropFanTag(fan);
  }


  /** Lay out a pile's card bodies (and the library's top back) for n cards. */
  private stackPile(seat: Seat, zone: PileZone, pile: PileObj, n: number): void {
    const [lx, lz] = pileSpot(seat, zone);
    const [wx, wz] = toWorld(seat, lx, lz);
    const h = pileHeight(n);
    const shown = Math.min(n, PILE_LAYERS);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const one = new THREE.Vector3(1, 1, 1);
    const salt = zone.length + seat.rot;
    const edge = new THREE.Color();
    for (let i = 0; i < shown; i++) {
      const y = shown <= 1 ? 0 : (i / shown) * h;
      q.setFromAxisAngle(up, seat.rot + jitter(i, salt) * 0.035);
      m.compose(new THREE.Vector3(wx + jitter(i, salt + 1) * 0.02, y, wz + jitter(i, salt + 2) * 0.02), q, one);
      pile.layers.setMatrixAt(i, m);
      // its edge: a card's dark border, every other one a shade apart, now and then a pale card core showing
      const k = jitter(i, salt + 3);
      edge.setRGB(0.1 + (i % 2) * 0.05 + k * 0.03, 0.09 + (i % 2) * 0.045 + k * 0.03, 0.085 + (i % 2) * 0.04 + k * 0.03, THREE.SRGBColorSpace);
      if (i % 7 === 3) edge.lerp(PILE_CORE, 0.35);
      pile.layers.setColorAt(i, edge);
    }
    if (pile.layers.instanceColor) pile.layers.instanceColor.needsUpdate = true;
    pile.layers.count = shown;
    pile.layers.instanceMatrix.needsUpdate = true;
    pile.layers.computeBoundingSphere();
    pile.block.scale.y = Math.max(0.06, h + THICK);
    pile.block.position.y = pile.block.scale.y / 2;
    if (pile.top) {
      pile.top.visible = n > 0;
      pile.top.position.set(wx, (shown <= 1 ? 0 : ((shown - 1) / shown) * h) + THICK + FACE_LIFT, wz);
      pile.top.rotation.y = seat.rot;
    }
  }

  private dimmed(m: THREE.MeshStandardMaterial): THREE.MeshStandardMaterial {
    let d = this.dimMats.get(m);
    if (!d) {
      d = m.clone();
      d.color.setScalar(0.26);
      this.dimMats.set(m, d);
    }
    return d;
  }

  private legalColor(view: GameView, id: string): string | null {
    const cls = legalClass(view, id, this.me);
    // a legal choice glows brass; the one pointed at and the chosen ones brighter
    if (cls === "rules-target") return this.beams?.targets.includes(id) ? this.plane.ui.accent2 : this.plane.ui.frameHi;
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

  /** The area the stack (K) or combat (X) close-up frames, or null when there's nothing there. */
  private closeUpBox(preset: CameraPreset): GroundBox | null {
    if (typeof preset !== "object") return null;
    if ("stack" in preset) return this.stackBox;
    if (!("combat" in preset) || !this.view) return null;
    let box: GroundBox | null = null;
    const r = CARD_H / 2 + 0.2;
    for (const id of combatCardIds(this.view)) {
      const c = this.cards.get(id);
      if (!c) continue;
      const b: GroundBox = box ?? { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity };
      box = { minX: Math.min(b.minX, c.target.x - r), maxX: Math.max(b.maxX, c.target.x + r), minZ: Math.min(b.minZ, c.target.z - r), maxZ: Math.max(b.maxZ, c.target.z + r) };
    }
    return box;
  }

  private updateCameraGoal(): void {
    const mine = this.seatList.find((s) => s.player === this.me) ?? this.seatList[0];
    if (!mine) return;
    const preset = this.preset;
    const box = this.closeUpBox(preset); // K / X: nothing there any more (resolved, combat over): my seat
    let pos: THREE.Vector3;
    let look: THREE.Vector3;
    const fitted = this.fitView(preset, mine);
    if (fitted) {
      // the seat view (behind my seat, looking across the aisle), the whole table, or Look at one player's board
      ({ pos, look } = fitted);
    } else if (box) {
      // the stack's standing cards, or the fight (attackers out in the aisle with their blockers), seen from my side
      const [dx, dz] = toWorld({ ...mine, x: 0, z: 0 }, 0, 1);
      const f = frameBox(box, [dx, dz], typeof preset === "object" && "stack" in preset ? { y: 1, elevation: 0.8 } : {});
      look = new THREE.Vector3(...f.look);
      pos = new THREE.Vector3(...f.pos).sub(look).multiplyScalar(LENS_REACH).add(look); // (framed for a 42° lens)
    } else if (typeof preset === "object" && "card" in preset) {
      // close up on one card, seen from my side of the table
      const c = this.cards.get(preset.card);
      look = c ? c.target.clone().setY(0) : new THREE.Vector3();
      const [dx, dz] = toWorld({ ...mine, x: 0, z: 0 }, 0, 1);
      pos = look.clone().add(new THREE.Vector3(dx * 2.6, 5.2, dz * 2.6).multiplyScalar(LENS_REACH)); // (framed for a 42° lens)
    } else {
      // a close-up with nothing left to show: my seat
      ({ pos, look } = this.fitView("seat", mine)!);
    }
    // -- camera -- the player's move of this view, on top of how the view frames it
    this.camBase = { pos: pos.clone(), look: look.clone() };
    const moved = adjustCamera(this.camBase, this.adj, TABLE_FOV);
    this.camGoalFov = moved.fov ?? TABLE_FOV;
    const off = moved.pos.clone().sub(moved.look);
    this.camGoalPos.copy(moved.pos);
    this.camGoalLook.copy(moved.look);
    // -- framing -- the room's fog starts past the table, however far back the camera sits for this screen
    if (this.scene.fog instanceof THREE.Fog) {
      const near = Math.max(this.fogBase[0], off.length() * 1.3);
      this.scene.fog.near = near;
      this.scene.fog.far = this.fogBase[1] + (near - this.fogBase[0]);
    }
    this.fitHearts();
    // -- arranged boards -- the tiles' names are drawn for this screen's seat view: drawn again when it changed
    const tv = this.tileViewVal;
    if (this.view && this.tileView() !== tv) this.syncCards();
  }

  /**
   * -- framing -- the seat view, the whole table and Look (2–6) fit what they show to this screen, between the top bar
   * and my hand (table3d/framing.ts); fitted again only when the screen, the seats or the view change. Null: a
   * close-up (C, K, X), framed as before.
   */
  private fitView(preset: CameraPreset, mine: Seat): { pos: THREE.Vector3; look: THREE.Vector3 } | null {
    if (typeof preset === "object" && !("focus" in preset)) return null;
    const key = `${JSON.stringify(preset)}|${this.seatKey}|${this.viewW}x${this.viewH}|${this.arranged}|${this.reserveTop}|${this.keepKey}`;
    if (this.fitKey === key && this.fitted) return { pos: this.fitted.pos.clone(), look: this.fitted.look.clone() };
    const cam = this.fitCam;
    cam.copy(this.camera);
    tableLens(this.viewW, this.viewH, cam);
    let pts: FitPoint[];
    let dir: THREE.Vector3;
    if (typeof preset === "object") {
      // Look: that player's board, as large as it goes; arranged boards read from my seat, so it's seen from my side
      const seat = this.seatList.find((s) => s.player === preset.focus) ?? mine;
      pts = seatPoints(seat, { buttons: seat === mine });
      dir = viewDir(this.arranged ? mine.rot : seat.rot, FOCUS_ELEVATION);
    } else {
      const elevation = preset === "overview" ? OVERVIEW_ELEVATION : seatElevation(this.seatList.length, this.viewW / Math.max(1, this.viewH));
      pts = tablePoints(this.seatList, mine, tableSize(this.seatList), elevation);
      dir = viewDir(mine.rot, elevation);
    }
    // clear of the fixed chrome: the camera strip, the stack pill and the turn dial
    const keep = this.keepOut3d.map((b) => ndcBox(b, this.viewW, this.viewH));
    const f = fitCamera(cam, pts, dir, tableRect(this.viewW, this.viewH, this.reserveTop), keep);
    this.fitKey = key;
    this.fitted = f;
    return { pos: f.pos.clone(), look: f.look.clone() };
  }
  private fitKey = "";
  /** -- framing -- the fixed chrome over the canvas (CSS px boxes): the table is framed clear of it. */
  private keepOut3d: { left: number; top: number; right: number; bottom: number }[] = [];
  private keepKey = "";
  private fitted: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null;
  private reserveTop = 0;
  /** -- arranged boards -- the turn dial's box on the canvas, and the corner of my mat it covers from my seat. */
  private dialKey = "";
  private dialWhere = "";
  private dial: { left: number; top: number; bottom: number } | null = null;
  private keepOut: { top: number; left: number } | null = null;

  /** -- arranged boards -- the turn dial's box (CSS px, relative to the canvas), so my rows stop short of the corner it covers. */
  setDialBox(box: { left: number; top: number; bottom: number } | null): void {
    // the tallest the dial has been on this screen, so my board doesn't reflow every step
    const where = box ? `${Math.round(box.left / 8)},${this.viewW}x${this.viewH}` : "";
    const top = box ? Math.min(box.top, where === this.dialWhere && this.dial ? this.dial.top : Infinity) : 0;
    const key = `${where}|${Math.round(top / 8)}`;
    this.dialWhere = where;
    if (key === this.dialKey) return;
    this.dialKey = key;
    this.dial = box && { ...box, top };
    const next = this.dialCorner();
    if (next?.top === this.keepOut?.top && next?.left === this.keepOut?.left) return;
    this.keepOut = next;
    this.syncCards();
  }

  /** Where the dial's corner falls on my mat, seen from my seat's view (layout units; null: it misses my mat). */
  private dialCorner(): { top: number; left: number } | null {
    const box = this.dial;
    const mine = this.seatList.find((s) => s.player === this.me);
    if (!box || !mine) return null;
    const f = this.fitView("seat", mine);
    if (!f) return null;
    const cam = this.fitCam;
    cam.copy(this.camera);
    tableLens(this.viewW, this.viewH, cam);
    cam.position.copy(f.pos);
    cam.lookAt(f.look);
    cam.updateMatrixWorld(true);
    const hit = (sx: number, sy: number): [number, number] | null => {
      this.ray.setFromCamera(new THREE.Vector2((sx / this.viewW) * 2 - 1, -(sy / this.viewH) * 2 + 1), cam);
      const p = this.ray.ray.intersectPlane(this.tablePlane, new THREE.Vector3());
      return p ? toLocal(mine, p.x, p.z) : null;
    };
    const a = hit(box.left, box.top);
    const b = hit(box.left, Math.min(box.bottom, this.viewH - 1));
    if (!a || !b) return null;
    const lx = Math.min(a[0], b[0]) - 0.1;
    const lz = a[1] - 0.1;
    if (lx >= MAT_W / 2 || lz >= MAT_D / 2) return null;
    const q = (v: number) => Math.round(Math.max(0, v) / 10) * 10;
    return { top: q((lz + MAT_D / 2) * AU), left: q((lx + MAT_W / 2) * AU) };
  }

  /**
   * -- framing -- the fixed chrome over the canvas the table is framed clear of (CSS px boxes, relative to the canvas):
   * the camera strip, the stack pill, the turn dial. Boxes are rounded to 8 px and a box only grows where it was
   * (the dial's tallest form on this screen), so the camera doesn't move as they change.
   */
  setKeepOuts(boxes: { left: number; top: number; right: number; bottom: number }[]): void {
    const q = (v: number) => Math.round(v / 8) * 8;
    const next = boxes.filter((b) => b.right > b.left && b.bottom > b.top).map((b) => ({ left: q(b.left), top: q(b.top), right: q(b.right), bottom: q(b.bottom) }));
    for (const b of next) {
      const was = this.keepOut3d.find((o) => o.left === b.left && o.right === b.right && o.bottom === b.bottom);
      if (was) b.top = Math.min(b.top, was.top);
    }
    const key = `${this.viewW}x${this.viewH}|${next.map((b) => `${b.left},${b.top},${b.right},${b.bottom}`).join(";")}`;
    if (key === this.keepKey) return;
    this.keepKey = key;
    this.keepOut3d = next;
    this.updateCameraGoal();
  }

  /** -- framing -- what the table is framed in and around (tests and diagnostics). */
  framingState(): { view: [number, number]; keepOut: { left: number; top: number; right: number; bottom: number }[]; reserveTop: number; elevation: number; adjust: CamAdjust; dragging: string; fov: number } {
    return {
      view: [this.viewW, this.viewH], keepOut: this.keepOut3d.map((b) => ({ ...b })), reserveTop: this.reserveTop, elevation: seatElevation(this.seatList.length, this.viewW / Math.max(1, this.viewH)),
      adjust: { ...this.adj }, dragging: this.rightPress ? "right" : this.panGrab ? "middle" : "", fov: this.camera.fov,
    };
  }

  /** -- camera -- how far the player has zoomed the view out (1: as the view frames it; above 1: farther). */
  cameraZoom(): number {
    return this.adj.zoom;
  }

  /** -- framing -- keep a strip this tall (px) clear at the top of the table (a tip banner sits there); 0: none. */
  setTopReserve(px: number): void {
    if (px === this.reserveTop) return;
    this.reserveTop = px;
    this.updateCameraGoal();
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

  private pick(clientX: number, clientY: number): { card?: string; pile?: PileZone; player?: string; heart?: string; side?: -1 | 1; seatButton?: SeatActionId; tax?: string; planar?: boolean } | null {
    this.ray.setFromCamera(this.pointer(clientX, clientY), this.camera);
    const targets: THREE.Object3D[] = [...this.props.targets(), ...this.planar.targets()];
    for (const c of this.cards.values()) if (c.group.visible && !this.drag?.ids.includes(c.id)) targets.push(c.face);
    for (const p of this.piles.values()) targets.push(p.block, p.slot, ...(p.top?.visible ? [p.top] : []));
    const hits = this.ray.intersectObjects(targets, false);
    const hit = hits[0];
    if (!hit) return null;
    const d = hit.object.userData as { card?: string; pile?: PileZone; player?: string; heart?: string; seatButton?: SeatActionId; tax?: string; planar?: boolean };
    // the Oops heart: its left half (▼) takes life away, its right half (▲) gives it
    if (d.heart) return { ...d, side: (hit.uv?.x ?? 1) < 0.5 ? -1 : 1 };
    return d;
  }

  private bindInput(): void {
    const cv = this.canvas;
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (e: HTMLElementEventMap[K]) => void, opts?: AddEventListenerOptions) => {
      cv.addEventListener(type, fn as EventListener, opts);
      this.unsubs.push(() => cv.removeEventListener(type, fn as EventListener));
    };
    on("pointerdown", (e) => this.onDown(e));
    on("mousedown", (e) => { if (e.button === 1) e.preventDefault(); }); // a middle-drag pans: no browser autoscroll
    on("pointermove", (e) => {
      this.onMove(e);
      this.trackPointer(e.clientX, e.clientY); // (after the move: it knows which card is under the pointer)
    });
    on("pointerup", (e) => this.onUp(e));
    on("pointerleave", () => {
      this.cursorOut.leave(); // onto the hand or a panel: nothing of what I hover there goes out
      this.setHover(null);
    });
    on("pointerleave", () => this.props.hoverHeart(null, undefined));
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
    // hover a seat button and type a number: that many (digits go to the button, not the camera keys)
    const onDigit = (e: KeyboardEvent) => {
      if (this.typed.key(this.hoveredButton, e.key)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };
    window.addEventListener("keydown", onDigit, true);
    this.unsubs.push(() => window.removeEventListener("keydown", onDigit, true));
    on("contextmenu", (e) => {
      // a right press opens its menu when it is let go without moving (a right-drag orbits instead), as in Tabletop
      // Simulator; a menu asked for otherwise (the keyboard's menu key, a long touch) opens at once
      e.preventDefault();
      if (this.rightPress || performance.now() - this.lastRightUp < 400) return;
      this.onContext(e);
    });
    on("wheel", (e) => {
      e.preventDefault();
      const over = this.pick(e.clientX, e.clientY);
      if (over?.heart) {
        if (!this.lifeLocked()) this.lifeBatch.bump(over.heart, e.deltaY < 0 ? 1 : -1);
        return;
      }
      // zoom toward the point under the pointer (a notch: about 12%; a trackpad's small steps, a little at a time)
      const ground = this.groundAt(e.clientX, e.clientY);
      if (!ground || !this.camBase) return;
      const lines = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      this.moveView(zoomAt(this.adj, this.camBase, ground, Math.exp(THREE.MathUtils.clamp(lines, -300, 300) * 0.0012), this.panBounds()));
    }, { passive: false });
  }

  private setHover(id: string | null): void {
    const s = useGame.getState();
    if (this.hovered === id) {
      // -- card preview -- over empty table, any hover still showing goes: one a page element left behind (a hand card
      // played, a stack entry resolved) as well as this table's own
      if (!id && s.hover) s.setHover(null);
      return;
    }
    this.hovered = id;
    if (id) s.setHover(id);
    else if (s.hover) s.setHover(null);
    this.syncTethers();
    if (this.beams) this.syncCards(); // -- targeting -- the arrow follows the pointer from candidate to candidate
    this.canvas.style.cursor = id ? "pointer" : "";
  }

  private onDown(e: PointerEvent): void {
    if (e.button === 1) {
      // middle-drag pans: the point grabbed stays under the pointer
      e.preventDefault();
      const ground = this.groundAt(e.clientX, e.clientY);
      if (ground) {
        this.panGrab = { id: e.pointerId, ground };
        this.canvas.setPointerCapture(e.pointerId);
      }
      return;
    }
    if (e.button === 2) {
      // right-drag orbits (decided once it moves); let go without moving and it's the menu (contextmenu)
      this.rightPress = { id: e.pointerId, x: e.clientX, y: e.clientY, adj: this.adj, moved: false };
      this.canvas.setPointerCapture(e.pointerId);
      return;
    }
    if (e.button !== 0) return;
    // a click on landed dice clears them away (from this screen)
    this.ray.setFromCamera(this.pointer(e.clientX, e.clientY), this.camera);
    const die = this.dice.pick(this.ray);
    if (die) {
      this.dice.dismiss(die);
      return;
    }
    const hit = this.pick(e.clientX, e.clientY);
    const store = useGame.getState();
    if (hit?.heart && answerByClick(store.view, hit.heart, this.me)) return; // -- targeting -- a targetable player's heart chooses them
    if (hit?.heart) {
      if (this.lifeLocked()) return;
      this.props.pressHeart(hit.heart, hit.side ?? 1);
      this.lifeBatch.bump(hit.heart, (hit.side ?? 1) * (e.shiftKey ? 5 : 1)); // ▼ −1, ▲ +1
      return;
    }
    if (hit?.tax) {
      void send({ type: "commander_tax", commander: hit.tax, delta: 2 }); // cast once more: +2
      return;
    }
    if (hit?.planar) {
      showPlanarText(); // -- planechase -- the plane on the table: the plaque opens its full text
      return;
    }
    if (hit?.seatButton) {
      this.props.press(hit.seatButton);
      runSeatAction(hit.seatButton, 1, this.me, { x: e.clientX, y: e.clientY });
      return;
    }

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
    if (clickAnswer(store.view, id, this.me, legalClass(store.view, id, this.me))) return; // a target, or a highlighted land to pay
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
    this.drag = { ids, anchor: id, start: [e.clientX, e.clientY], grab, offsets, active: false, trail: [] };
    this.canvas.setPointerCapture(e.pointerId);
  }

  private onMove(e: PointerEvent): void {
    const rp = this.rightPress;
    if (rp && rp.id === e.pointerId) {
      const dx = e.clientX - rp.x;
      const dy = e.clientY - rp.y;
      if (!rp.moved && Math.hypot(dx, dy) < 5) return;
      rp.moved = true;
      if (this.camBase) this.moveView(orbitBy(rp.adj, dx, dy, this.camBase, this.panBounds()));
      return;
    }
    const pg = this.panGrab;
    if (pg && pg.id === e.pointerId) {
      const now = this.groundAt(e.clientX, e.clientY);
      if (now && this.camBase) this.moveView(panBy(this.adj, pg.ground.x - now.x, pg.ground.z - now.z, this.camBase, this.panBounds()));
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
      // where the hand has been lately: how fast it was moving when it let go (a flick)
      d.trail.push({ t: e.timeStamp, x: p.x, z: p.z }); // the event's own time: a busy frame doesn't skew the speed
      if (d.trail.length > 8) d.trail.shift();
      for (const cid of d.ids) {
        const c = this.cards.get(cid);
        const off = d.offsets.get(cid);
        if (c && off) c.target.set(p.x + off.x, LIFT, p.z + off.z);
      }
      return;
    }
    const hit = this.pick(e.clientX, e.clientY);
    this.setHover(hit?.card ?? null);
    this.hoveredButton = hit?.seatButton ?? null;
    this.props.hover(this.hoveredButton);
    this.props.hoverHeart(hit?.heart ?? null, hit?.side); // the heart's − or + half under the pointer lights up
    const taxOf = hit?.tax ? this.view?.players.flatMap((p) => p.commanders).find((c) => c.key === hit.tax) : undefined;
    const dealt = taxOf && this.view ? dealtText(commanderDealt(this.view.players, taxOf.key)) : "";
    // (a seat button names itself on the table, on its own plate: no browser tooltip over it)
    const tip = taxOf ? `${taxSentence(taxOf.tax)}\n${taxOf.name}: click +2, right-click −2${dealt ? `\nCommander damage dealt: ${dealt}` : ""}`
      : hit?.heart ? `${this.view?.players.find((p) => p.id === hit.heart)?.name ?? ""}'s life${this.lifeLocked() ? "" : ": click − to lose 1 or + to gain 1, right-click for 5, or the wheel"}` : "";
    if (this.canvas.title !== (tip ?? "")) this.canvas.title = tip ?? "";
    this.canvas.style.cursor = hit?.seatButton || (hit?.heart && !this.lifeLocked()) || hit?.tax || hit?.planar ? "pointer" : "";
  }

  private onUp(e: PointerEvent): void {
    const rp = this.rightPress;
    if (rp && rp.id === e.pointerId && e.button === 2) {
      this.rightPress = null;
      this.lastRightUp = performance.now();
      if (!rp.moved) this.onContext(e); // a right-click: the card's, pile's or table's menu
      return;
    }
    if (this.panGrab && this.panGrab.id === e.pointerId && e.button === 1) {
      this.panGrab = null;
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
    if (target && this.flick(d, e.timeStamp)) return;
    if (target && this.arrangedDrop(d.ids, d.anchor, target.zone)) return;
    if (target) dropCards(d.ids, d.anchor, { ...target, manual: e.altKey, at: { clientX: e.clientX, clientY: e.clientY } });
    else toast("Dropped off the table: nothing changed", "info");
    this.syncCards(); // snap back (or to the pending position) until the server answers
  }

  /**
   * Let go of your own cards while still moving them and they slide on, knocking your other cards aside (physics:
   * table3d/cardPhysics.ts). Where everything stops is sent as one move. A slow release is a normal, exact drop.
   */
  private flick(d: NonNullable<TableScene["drag"]>, released: number): boolean {
    if (usePrefs.getState().cardPhysics === false) return false;
    const recent = d.trail.filter((p) => released - p.t < 90);
    if (recent.length < 2) return false;
    const a = recent[0]!, b = recent[recent.length - 1]!;
    const dt = (b.t - a.t) / 1000;
    if (dt <= 0) return false;
    const vx = (b.x - a.x) / dt, vz = (b.z - a.z) / dt;
    if (Math.hypot(vx, vz) < FLICK_SPEED) return false;
    return this.flickCards(d.ids, vx, vz);
  }

  /** Slide these cards of mine from where they are now at (vx, vz) world units a second (tests use it directly). */
  flickCards(ids: string[], vx: number, vz: number): boolean {
    const view = this.view;
    const seat = this.seatList.find((s) => s.player === this.me);
    if (!view || !seat || !ids.length) return false;
    if (this.arranged) return this.flickArranged(ids, vx, vz);
    const now = performance.now();
    const d = { ids };
    const mat = `${this.me}:battlefield`;
    if (!d.ids.every((id) => view.cards[id]?.zone === mat)) return false; // only rearranging your own battlefield
    // the velocity on the mat's own axes
    const [ox, oz] = toLocal(seat, 0, 0);
    const [ux, uz] = toLocal(seat, vx, vz);
    const lv = [ux - ox, uz - oz];
    const pending = useGame.getState().pendingPositions;
    const cards: SlideCard[] = [];
    for (const id of (view.zones[mat] as string[] | undefined) ?? []) {
      const card = view.cards[id];
      if (!card || ("attached_to" in card && card.attached_to)) continue; // attachments ride on their host
      const turned = !!card.tapped !== !!((card.rotation ?? 0) % 180);
      const [w, dd] = turned ? [CARD_H, CARD_W] : [CARD_W, CARD_H];
      if (d.ids.includes(id)) {
        const c = this.cards.get(id);
        if (!c) continue;
        const [lx, lz] = toLocal(seat, c.target.x, c.target.z);
        cards.push({ id, x: lx, z: lz, w, d: dd, vx: lv[0], vz: lv[1] });
      } else {
        const [vx0, vy0] = pending[id] ?? [card.x ?? 0, card.y ?? 0];
        const [lx, lz] = virtualToLocal(vx0, vy0);
        cards.push({ id, x: lx, z: lz, w, d: dd });
      }
    }
    const result = slide(cards, MAT_W / 2 + 0.7, MAT_D / 2 + 1.0);
    const final: Record<string, [number, number]> = {};
    for (const c of cards) {
      const at = result.rest.get(c.id) ?? (d.ids.includes(c.id) ? [c.x, c.z] as [number, number] : null);
      if (at) final[c.id] = localToVirtual(at[0], at[1]);
    }
    const moves = Object.entries(final).slice(0, 250).map(([id, [x, y]]) => [id, Math.round(x), Math.round(y)]);
    if (!moves.length) return false;
    useGame.getState().setPending(final);
    void send({ type: "set_position", moves });
    this.sliding = { seat, start: now, frames: result.frames, tracks: result.tracks };
    this.syncCards();
    return true;
  }

  /**
   * -- arranged boards -- cards let go on the arranged board they came from take that spot in their row: my order, on
   * this screen only (game/arrange.ts), and nothing is sent. False: not that kind of drop (it moves as usual).
   */
  private arrangedDrop(ids: string[], anchor: string, zone: string): boolean {
    const view = this.view;
    const c = this.cards.get(anchor);
    const mat = this.boards.mats.get(zone.split(":")[0]!);
    if (!this.arranged || !view || !c || !mat || mat.zone !== zone || !ids.every((id) => view.cards[id]?.zone === zone)) return false;
    const [lx, lz] = toLocal(mat.frame, c.target.x, c.target.z);
    const order = reorderMat(mat, ids, lx, lz);
    if (order) {
      saveBoardOrder(view.game.id, zone, order);
      useBoardOrderTick.getState().bump();
    }
    this.syncCards();
    return true;
  }

  /**
   * -- arranged boards -- a flick on my arranged mat: each slot (a card, a stack, a host with what's tucked under it)
   * slides as one tile-sized body and knocks the others aside, then every row takes the order its cards came to rest
   * in (my order, display only: nothing is sent).
   */
  private flickArranged(ids: string[], vx: number, vz: number): boolean {
    const view = this.view;
    const zone = `${this.me}:battlefield`;
    const mat = this.boards.mats.get(this.me);
    if (!view || !mat || !ids.every((id) => view.cards[id]?.zone === zone)) return false;
    const L = mat.layout;
    const [ox, oz] = toLocal(mat.frame, 0, 0);
    const [ux, uz] = toLocal(mat.frame, vx, vz);
    const tw = L.w / AU;
    const th = L.h / AU;
    const bodies: SlideCard[] = [];
    const slots = L.rows.flatMap((r) => r.slots);
    for (const slot of slots) {
      const lead = this.placed.get(slot[0]!);
      const card = view.cards[slot[0]!];
      if (!lead || !card) continue;
      const turned = !!card.tapped !== !!((card.rotation ?? 0) % 180);
      const held = slot.find((id) => ids.includes(id));
      // a flicked slot starts where it was let go (dragged), the rest where they lie
      const from = held && this.cards.get(held) ? toLocal(mat.frame, this.cards.get(held)!.target.x, this.cards.get(held)!.target.z) : null;
      const off = held ? [this.placed.get(held)!.lx - lead.lx, this.placed.get(held)!.lz - lead.lz] : [0, 0];
      bodies.push({
        id: slot[0]!, x: from ? from[0] - off[0]! : lead.lx, z: from ? from[1] - off[1]! : lead.lz, w: turned ? th : tw, d: turned ? tw : th,
        ...(held ? { vx: ux - ox, vz: uz - oz } : {}),
      });
    }
    const result = slide(bodies, MAT_W / 2, MAT_D / 2);
    if (!result.rest.size) return false;
    // every card of a slot rides with its body
    const tracks = new Map<string, Float32Array>();
    for (const slot of slots) {
      const track = result.tracks.get(slot[0]!);
      const lead = this.placed.get(slot[0]!);
      if (!track || !lead) continue;
      for (const id of slot) {
        const s = this.placed.get(id);
        if (!s) continue;
        const dx = s.lx - lead.lx;
        const dz = s.lz - lead.lz;
        tracks.set(id, track.map((v, i) => v + (i % 2 ? dz : dx)));
      }
    }
    const order = orderFromRest(L, (id) => {
      const r = result.rest.get(id);
      return r ? [(r[0] + MAT_W / 2) * AU, (r[1] + MAT_D / 2) * AU] : null;
    });
    const gameId = view.game.id;
    this.sliding = {
      seat: mat.frame, start: performance.now(), frames: result.frames, tracks,
      done: () => {
        saveBoardOrder(gameId, zone, order);
        useBoardOrderTick.getState().bump();
      },
    };
    return true;
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

  /** -- out of the game -- the hearts are totals, not controls (as on the 2D table). */
  private lifeLocked(): boolean {
    return isOut(this.view, this.me);
  }

  private onContext(e: MouseEvent): void {
    e.preventDefault();
    const hit = this.pick(e.clientX, e.clientY);
    if (hit?.heart) {
      if (this.lifeLocked()) return;
      this.props.pressHeart(hit.heart, hit.side ?? 1);
      this.lifeBatch.bump(hit.heart, (hit.side ?? 1) * 5); // right-click: 5 at a time
      return;
    }
    if (hit?.tax) {
      void send({ type: "commander_tax", commander: hit.tax, delta: -2 });
      return;
    }
    if (hit?.seatButton) {
      this.props.press(hit.seatButton);
      runSeatAction(hit.seatButton, 3, this.me, { x: e.clientX, y: e.clientY }); // right-click: three
      return;
    }
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

  /** One card's body and contact shadow into the instanced draws (a fading stand-in keeps only its shadow). */
  private writeBody(obj: THREE.Object3D, n: number, opacity = 1, shadow = true): number {
    if (n >= 1024) return n;
    obj.updateMatrix();
    this.bodies.setMatrixAt(n, opacity >= 0.99 ? obj.matrix : NO_BODY);
    // the shadow sits on the table, offset away from the key light and softer as the card rises
    const lift = Math.max(0, obj.position.y);
    const spread = (1 + Math.min(lift, 1.2) * 0.55) * obj.scale.x;
    shadowPos.set(obj.position.x + 0.05 + lift * 0.2, SHADOW_Y, obj.position.z + 0.08 + lift * 0.3);
    shadowQ.setFromAxisAngle(UP, obj.rotation.y);
    shadowScale.set(spread, 1, spread * (obj.scale.z / (obj.scale.x || 1)));
    shadowM.compose(shadowPos, shadowQ, shadowScale);
    this.shadows.setMatrixAt(n, shadowM);
    const strength = shadow ? opacity / (1 + lift * 2.5) : 0;
    shadowColor.setRGB(strength, strength, strength);
    this.shadows.setColorAt(n, shadowColor);
    return n + 1;
  }

  private loop = (): void => {
    this.raf = requestAnimationFrame(this.loop);
    const started = performance.now();
    const dt = Math.min(0.5, this.clock.getDelta()); // real time: slow devices still settle quickly
    const t = this.clock.elapsedTime;
    const reduced = document.body.classList.contains("reduced-motion");
    // empty pile outlines stay faint until a drag needs them as drop targets
    const anyDrag = document.body.classList.contains("dragging");
    for (const p of this.piles.values()) {
      // (a well is always there; while a card is dragged, its gold catches the light as a drop target)
      const m = p.slot.material as THREE.MeshStandardMaterial;
      m.emissiveIntensity = anyDrag ? 0.14 : 0;
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
    this.tethers.visible = !dragging; // attachment lines catch up when the move lands
    const sl = this.sliding;
    if (sl) {
      // a flick plays back at the table's animation speed; reduced motion jumps to where it stopped
      const f = reduced ? sl.frames : Math.floor(((performance.now() - sl.start) / 1000) * SLIDE_FPS * speed);
      for (const [id, track] of sl.tracks) {
        const c = this.cards.get(id);
        if (!c) continue;
        const i = Math.min(f, track.length / 2 - 1) * 2;
        const [wx, wz] = toWorld(sl.seat, track[i]!, track[i + 1]!);
        c.target.x = wx;
        c.target.z = wz;
      }
      if (f >= sl.frames) {
        this.sliding = null;
        sl.done?.();
      }
    }
    let n = 0;
    // table motion (motion3d.ts): flights, riffles, numbers; nothing to do while idle
    const moving = this.motion.active;
    if (moving) this.motion.update(started, reduced);
    this.planar.update(started); // -- planechase -- a planeswalk or chaos playing (idle: nothing)
    for (const c of this.cards.values()) {
      if (c.fresh) {
        // new to the table with no flight to bring it: it is simply where it belongs (never glides in from the middle)
        c.fresh = false;
        c.group.position.copy(c.target);
        c.group.rotation.set(c.tilt, c.rot, 0);
        c.group.scale.setScalar(c.scale);
        c.sq = c.squash ?? 1;
      }
      if (!c.flying) {
        if (c.struck) this.motion.unstrike(c);
        // hovered and selected cards ride a little higher, and a tap lifts the card as it turns
        const lift = liftFor({ hovered: c.id === this.hovered && !dragging, selected: this.selectedIds.has(c.id), turning: reduced ? 0 : angleDelta(c.group.rotation.y, c.rot) });
        liftTarget.copy(c.target);
        liftTarget.y += lift;
        c.group.position.lerp(liftTarget, k);
        c.group.rotation.y = angleLerp(c.group.rotation.y, c.rot, k);
        c.group.rotation.x += (c.tilt - c.group.rotation.x) * k;
        // -- arranged boards -- the tile pointed at grows a little, as on Arena (its full card is in the preview)
        const want = c.tile && c.id === this.hovered && !dragging ? c.scale * 1.12 : c.scale;
        const sc = c.group.scale.x + (want - c.group.scale.x) * k;
        c.group.scale.setScalar(sc);
        if (c.struck) this.motion.restrike(c, started);
      }
      // -- arranged boards -- a tile is its card squashed to a tile's depth, eased with the rest of its move
      const sq = c.squash ?? 1;
      c.sq = c.sq === undefined || Math.abs(sq - c.sq) < 1e-3 ? sq : c.sq + (sq - c.sq) * k;
      if (c.sq !== 1) c.group.scale.z = c.group.scale.x * c.sq;
      // -- token piles -- a card lying wholly under its cover draws nothing; either one moving off (a flight, a drag, an attack,
      // the easing after a change) shows it meanwhile
      const cover = c.cover ? this.cards.get(c.cover) : undefined;
      c.group.visible = !cover || !!cover.flying || !!cover.fresh || !!c.flying || !lyingOn(c.group, cover.group);
      if (c.group.visible) n = this.writeBody(c.group, n, 1, !(c.tile && this.placed.get(c.id)?.under));
    }
    this.sizeBadges();
    if (moving) {
      this.bodyN = n;
      this.motion.standIns(this.pushStandIn);
      n = this.bodyN;
    }
    this.bodies.count = n;
    this.bodies.instanceMatrix.needsUpdate = true;
    this.shadows.count = n;
    this.shadows.instanceMatrix.needsUpdate = true;
    if (this.shadows.instanceColor) this.shadows.instanceColor.needsUpdate = true;
    this.dice.update(performance.now(), reduced, speed);
    this.cannon?.update(performance.now(), speed);
    this.props.tick(t, this.camera, reduced);
    this.tickFans(ease(dt, 9 * speed, reduced));
    const kc = ease(dt, 5 * speed, reduced);
    this.camPos.lerp(this.camGoalPos, kc);
    this.camLook.lerp(this.camGoalLook, kc);
    // -- flicker -- a camera that has arrived stops exactly, not creeping by fractions of a pixel forever
    if (this.camPos.distanceToSquared(this.camGoalPos) < 1e-8 && this.camLook.distanceToSquared(this.camGoalLook) < 1e-8) {
      this.camPos.copy(this.camGoalPos);
      this.camLook.copy(this.camGoalLook);
    }
    this.camera.position.copy(this.camPos);
    if (this.end.active) this.end.update(started, reduced, this.camera.position, this.camLook, this.camGoalLook);
    this.camera.lookAt(this.camLook);
    this.fitLens(kc);
    this.fitDepth();
    // -- live cursors -- mine out (throttled, a trailing send, one "gone"), the others' eased and faded
    const out = this.cursorOut.poll(started);
    if (out && this.sendsCursor()) useGame.getState().conn?.sendCursor(out);
    this.cursors.group.visible = usePrefs.getState().cursors;
    if (this.cursors.group.visible) {
      this.camera.updateMatrixWorld();
      this.cursors.update(dt, started, reduced, this.camera, this.camera.view?.fullHeight ?? this.canvas.clientHeight);
    }
    if (!reduced && !this.still) {
      // candle flicker, drifting dust and flowing beams only when motion is welcome
      this.env?.update(t);
      arrowTime.value = t;
    }
    this.renderer.info.reset();
    if (this.post) this.post.render();
    else this.renderer.render(this.scene, this.camera);
    if (this.grabs.length) {
      // (tests: the frame just drawn, read before the browser shows it)
      const gl = this.renderer.getContext();
      const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
      const px = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      for (const g of this.grabs.splice(0)) g(px);
    }
    if (this.afterFrame.length) for (const f of this.afterFrame.splice(0)) f();
    if (this.dice.count || this.diceHud.el.childElementCount) {
      // the dice's chips and line, in the canvas's own pixels
      const w = this.canvas.clientWidth;
      const h = this.canvas.clientHeight;
      this.diceHud.render(this.dice.hud((p) => {
        const v = this.tmpV.copy(p).project(this.camera);
        return { x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h, visible: v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1 };
      }));
    }
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
