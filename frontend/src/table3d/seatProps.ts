/**
 * Things at each seat of the 3D table, after the Oops I Baked a Pie table:
 * - Life: the Oops heart. Black, edged thick in the seat's colour, the total big in its middle, ▼ on its left and ▲
 *   on its right. It lies at the mat's inner corner by the middle of the table, a little above the felt, turned so
 *   you read every seat's number upright. Click its left half −1, its right half +1, right-click for 5, or the wheel
 *   (TableScene). Attack arrows aim at it.
 * - Your seat's buttons, as the Oops table has them: in a row just past your mat's near edge (from its left end), bevelled
 *   brass medallions with stamped symbols (game/seatIcons.ts), Untap, Draw, Scry, Mill and Reveal, then Mulligan apart to
 *   the right and the Bag of Extras past it.
 * - Each commander's tax: a short column of brass coins beside its command well, one per cast from the command zone,
 *   the tax to pay ("+4") on the well's brass nameplate under them; at 0 an empty socket. A new coin drops onto the stack.
 * - A partner's (or background's) well in the command zone, as the commander's (table3d/zoneWells.ts).
 */
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { SEAT_ACTIONS, type SeatActionId } from "../game/seatActions";
import { useGame } from "../state/gameStore";
import { drawSeatIcon, drawTaxCoinFace, drawTaxSocket, taxCasts } from "../game/seatIcons";
import { motionMs, onMotionSkip } from "../game/motion/timing";
import { BUTTON_R, buttonRowZ, COIN, plateDepth, commandSlot, COMMAND_SLOTS, COMMAND_WELL, HEART, heartSpot, heartTilt, plateOffset, plateWidth, TAX_READOUT, TAX_STACK, taxReadoutSpot, taxSpot, toWorld, wellPiece, type Seat } from "./layout";
import { drawWell, WELL_PX, wellCanvasSize, wellStretch, whenWellFontsReady, type WellArt } from "./zoneWells";

const HEART_W = HEART.w;
const HEART_Y = HEART.y;
const BUTTON_H = 0.08;
/** How far a seat button's chit is tipped up toward its owner (radians). */
const CHIT_TILT = 0.5;
/** The buttons' row (layout.ts buttonRowZ): one medallion every PITCH, the two groups apart by DIVIDE. */
const PITCH = 0.64;
const DIVIDE = 0.36;
/** 1v1: the first group's first medallion (under my command zone), and Mulligan's (right of my heart, the Bag past it). */
const DUEL_ROW_X = -7.8;
const DUEL_MULLIGAN_X = 3.45;
const LABEL_H = 0.5;

/**
 * A seat button's name as it shows over the button while hovered: Cinzel on a small blackened plate with a brass edge
 * (the game's own tooltip; the table is a canvas). Returns the plate's width over its height.
 */
function drawLabel(canvas: HTMLCanvasElement, text: string): number {
  const H = 64;
  const font = '600 34px Cinzel, Georgia, serif';
  const probe = canvas.getContext("2d")!;
  probe.font = font;
  const W = Math.ceil(probe.measureText(text).width) + 44;
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext("2d")!;
  const plate = new Path2D();
  plate.roundRect(3, 3, W - 6, H - 6, 8);
  const fill = g.createLinearGradient(0, 0, 0, H);
  fill.addColorStop(0, "#1f1a16");
  fill.addColorStop(1, "#0a0807");
  g.fillStyle = fill;
  g.fill(plate);
  const edge = g.createLinearGradient(0, 0, W, H);
  edge.addColorStop(0, "#f0d08a");
  edge.addColorStop(1, "#7a5528");
  g.strokeStyle = edge;
  g.lineWidth = 2.5;
  g.stroke(plate);
  g.font = font;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillStyle = "#f2dca6";
  g.fillText(text, W / 2, H / 2 + 2);
  return W / H;
}

/** The Oops heart, in a 256×232 box. */
function heartPath(): Path2D {
  const p = new Path2D();
  p.moveTo(128, 224);
  p.bezierCurveTo(70, 182, 12, 138, 12, 76);
  p.bezierCurveTo(12, 36, 42, 10, 78, 10);
  p.bezierCurveTo(102, 10, 120, 24, 128, 44);
  p.bezierCurveTo(136, 24, 154, 10, 178, 10);
  p.bezierCurveTo(214, 10, 244, 36, 244, 76);
  p.bezierCurveTo(244, 138, 186, 182, 128, 224);
  p.closePath();
  return p;
}

/** The life total (and the clicks still on their way under it), centred at (128, y) in the heart's box. */
function lifeNumber(g: CanvasRenderingContext2D, life: number, pending: number, y: number): void {
  g.textAlign = "center";
  g.textBaseline = "middle";
  const n = String(life + pending);
  g.fillStyle = life + pending <= 0 ? "#ff8a7a" : "#f1ece2";
  g.font = `700 ${n.length > 2 ? 64 : 84}px "Inter Variable", Inter, Arial, sans-serif`;
  g.lineJoin = "round";
  g.lineWidth = 8;
  g.strokeStyle = "rgba(0, 0, 0, 0.85)";
  g.strokeText(n, 128, y);
  g.fillText(n, 128, y);
  if (pending) {
    g.font = '800 30px "Inter Variable", Inter, Arial, sans-serif';
    g.fillStyle = pending > 0 ? "#9ee68a" : "#ff9a8a";
    g.strokeText(pending > 0 ? `+${pending}` : `${pending}`, 128, y + 48);
    g.fillText(pending > 0 ? `+${pending}` : `${pending}`, 128, y + 48);
  }
}

/**
 * The Oops heart, drawn for the table: black, edged thick in the seat's colour, the life total big in its middle, and
 * its two halves the controls, marked ▼ and ▲ in its lobes. `hot`: the half under the pointer, lit faintly.
 */
function drawHeart(canvas: HTMLCanvasElement, color: string, life: number, pending: number, hot: -1 | 0 | 1 = 0, pressed: -1 | 0 | 1 = 0, readOnly = false): void {
  const g = canvas.getContext("2d")!;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.save();
  g.scale(canvas.width / 256, canvas.height / 232);
  const heart = heartPath();
  g.fillStyle = "#050505";
  g.fill(heart);
  // read-only (out of the game: the total, not a control): the black heart and its number, as the 2D table's
  if (readOnly) {
    g.lineJoin = "round";
    g.lineWidth = 15;
    g.strokeStyle = color;
    g.stroke(heart);
    lifeNumber(g, life, pending, 118);
    g.restore();
    return;
  }
  // the halves are the controls (− left, + right): the black heart as before, the half under the pointer lit
  // faintly, the one pressed a shade darker
  if (hot || pressed) {
    g.save();
    g.clip(heart);
    g.fillStyle = pressed ? "rgba(0, 0, 0, 0.35)" : "rgba(255, 240, 210, 0.09)";
    g.fillRect((pressed || hot) < 0 ? 0 : 128, 0, 128, 232);
    g.restore();
  }
  g.lineJoin = "round";
  g.lineWidth = 15;
  g.strokeStyle = color;
  g.stroke(heart);
  // ▼ and ▲ in the lobes: parchment, large enough to read across the table (brighter on the lit half)
  const tri = (x: number, down: boolean, lit: boolean) => {
    const w = 34;
    const h = 22;
    const y = 92;
    g.beginPath();
    if (down) { g.moveTo(x - w / 2, y - h / 2); g.lineTo(x + w / 2, y - h / 2); g.lineTo(x, y + h / 2); }
    else { g.moveTo(x - w / 2, y + h / 2); g.lineTo(x + w / 2, y + h / 2); g.lineTo(x, y - h / 2); }
    g.closePath();
    g.fillStyle = lit ? "#fff4dc" : "#cbbf9f";
    g.fill();
  };
  tri(56, true, hot === -1);
  tri(200, false, hot === 1);
  lifeNumber(g, life, pending, 128);
  g.restore();
}

let blob: THREE.CanvasTexture | null = null;
const blobTexture = () => {
  if (blob) return blob;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0, "rgba(0,0,0,0.5)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return (blob = new THREE.CanvasTexture(c));
};

/** A commander's tax medallion: the face (`mesh`, turned to the viewer), its brass edge, and when its number last changed. */
/**
 * A commander's tax: its socket and the column's base (world), the hit cylinder over its coins and the hit box over its
 * number on the well's plate, the tax shown and its coins, and the top coin's fall (when it started, and whether it is
 * still falling).
 */
interface Tax {
  key: string; base: THREE.Vector3; salt: number; first: number;
  socket: THREE.Mesh; hit: THREE.Mesh; readout: THREE.Mesh;
  shown: number; coins: number; dropAt: number; dropping: boolean;
  /** A partner's (or background's) well, whose plate carries its tax at three or more seats. */
  well?: { art: WellArt; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture };
}
/** How far a new tax coin falls onto its stack, and for how long (at the table's animation speed). */
const COIN_DROP_H = 0.42;
const COIN_DROP_MS = 260;

interface Heart {
  group: THREE.Group; face: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; shown: string;
  /** The half under the pointer (−1 the − half, 1 the + half), lit; the half pressed (held down, or for a moment). */
  hot: -1 | 0 | 1;
  pressed: -1 | 0 | 1;
  pressAt: number;
  /** Its scale (eased toward `fitTo`): 1, its size on the table; smaller seen low, so it and its plate keep off the mat. */
  fit: number;
  fitTo: number;
  /** -- table motion -- the life total on the heart rolls to a new value (docs/GAME_UI_MOTION_RESEARCH.md §4: 300–600 ms scaled to the
   * change): what it shows now, where it's going, and the clicks still on their way. */
  roll: { from: number; to: number; start: number; dur: number; at: number | null; pending: number };
}
/**
 * A seat button: its face, brass edge and glow ring; `lift`, how far it rises while hovered (eased); `tip`, where its name
 * shows while hovered (just over the mat's edge above it, as seen from the seat).
 */
interface Button {
  group: THREE.Group; top: THREE.Mesh; side: THREE.Mesh; edge: THREE.MeshStandardMaterial; glow: THREE.Mesh; sink: THREE.Mesh;
  canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; typed: string; press: number; lift: number; tip: THREE.Vector3;
}

/** The whole number a rolling life total shows at ``now`` (ease-out; it lands exactly on ``to``). */
export function lifeRollAt(r: { from: number; to: number; start: number; dur: number }, now: number): number {
  const k = r.dur > 0 ? Math.min(1, Math.max(0, (now - r.start) / r.dur)) : 1;
  if (k >= 1) return r.to;
  return Math.round(r.from + (r.to - r.from) * (1 - Math.pow(1 - k, 3)));
}

export class SeatProps {
  readonly group = new THREE.Group();
  private hearts = new Map<string, Heart>();
  private taxes = new Map<string, Tax>();
  private taxKey = "";
  private buttons = new Map<SeatActionId, Button>();
  private hovered: SeatActionId | null = null;
  private disposables: { dispose(): void }[] = [];
  private tmp = new THREE.Vector3();
  /** Any click or key lands every rolling life total at once (game/motion/timing.ts). */
  private unskip = onMotionSkip(() => {
    for (const h of this.hearts.values()) {
      if (h.roll.at !== null && h.roll.at !== h.roll.to) {
        h.roll.at = h.roll.to;
        this.drawLife(h, h.roll.at);
      }
    }
    // and every falling tax coin onto its stack
    for (const t of this.taxes.values()) if (t.dropping) { t.dropping = false; this.coinsDirty = true; }
  });

  /** Hearts for every seat; buttons for mine (seat colours from the view). */
  rebuild(seats: Seat[], me: string, colors: Record<string, string>, readOnly = false): void {
    this.clear();
    this.readOnly = readOnly;
    for (const seat of seats) {
      const color = colors[seat.player] ?? "#c9a35a";
      const canvas = document.createElement("canvas");
      canvas.width = 512;
      canvas.height = 464;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      // the heart lies on the table, its top edge tipped a little up toward whoever is looking
      // printed like the Oops heart: unlit, so the black stays black under the table's warm light
      const face = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(HEART_W, HEART.h)), this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false })));
      const tilt = heartTilt(seat);
      face.rotation.x = -Math.PI / 2 + tilt;
      face.userData = { heart: seat.player };
      face.position.y = Math.sin(tilt) * HEART.h * 0.5; // tipped up from its bottom edge, which rests over the felt
      const shadow = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(HEART_W * 1.05, HEART_W).rotateX(-Math.PI / 2)), this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
      shadow.position.y = -HEART_Y + 0.006;
      const group = new THREE.Group();
      group.add(shadow, face);
      const [wx, wz] = toWorld(seat, ...heartSpot(seat));
      group.position.set(wx, HEART_Y, wz);
      this.group.add(group);
      this.hearts.set(seat.player, { group, face, canvas, tex, color, shown: "", hot: 0, pressed: 0, pressAt: 0, fit: 1, fitTo: 1, roll: { from: 0, to: 0, start: 0, dur: 0, at: null, pending: 0 } });
    }
    const mine = seats.find((s) => s.player === me);
    if (!mine) return;
    // the medallions: a face drawn lit from the top left (the same picture as the 2D table's buttons, unlit, its rim's
    // edge soft in the texture's alpha), a brass edge lit by the table's light, a contact shadow, and a glow ring for hover
    const contact = this.keep(new THREE.PlaneGeometry(BUTTON_R * 2.7, BUTTON_R * 2.7).rotateX(-Math.PI / 2));
    const faceGeo = this.keep(new THREE.PlaneGeometry(BUTTON_R * 2, BUTTON_R * 2).rotateX(-Math.PI / 2));
    // an ivory chit: a low rounded tile, its inked face printed on top
    const sideGeo = this.keep(new RoundedBoxGeometry(BUTTON_R * 2, BUTTON_H, BUTTON_R * 2, 3, BUTTON_R * 0.36));
    const ringGeo = this.keep(new THREE.RingGeometry(BUTTON_R * 1.04, BUTTON_R * 1.32, 64).rotateX(-Math.PI / 2));
    const ROW_Z = buttonRowZ(mine.duel);
    const groups = [SEAT_ACTIONS.filter((a) => a.id !== "mulligan" && a.id !== "extras"), SEAT_ACTIONS.filter((a) => a.id === "mulligan" || a.id === "extras")];
    const span = (groups[0]!.length + groups[1]!.length - 1) * PITCH + DIVIDE;
    const x0 = 0.7 - span; // (ends a little right of the mat's middle: the turn dial covers the screen's bottom right)
    // 1v1: my heart and plate take the middle of my near edge, so the first group starts under my command zone and
    // Mulligan and the Bag go right of my heart (the heart and plate between them divide the groups)
    const lxOf = (id: SeatActionId) => {
      const k = groups[0]!.findIndex((a) => a.id === id);
      const j = groups[1]!.findIndex((a) => a.id === id);
      if (mine.duel) return k >= 0 ? DUEL_ROW_X + k * PITCH : DUEL_MULLIGAN_X + j * PITCH;
      return k >= 0 ? x0 + k * PITCH : x0 + (groups[0]!.length - 1) * PITCH + DIVIDE + (j + 1) * PITCH;
    };
    SEAT_ACTIONS.forEach((a) => {
      const group = new THREE.Group();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 256;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      const top = new THREE.Mesh(faceGeo, this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
      top.position.y = BUTTON_H + 0.002;
      top.userData = { seatButton: a.id };
      const edge = this.keep(new THREE.MeshStandardMaterial({ color: 0xcdb98e, roughness: 0.55, metalness: 0, emissive: 0xffc870, emissiveIntensity: 0 }));
      const side = new THREE.Mesh(sideGeo, edge);
      side.position.y = BUTTON_H / 2;
      side.userData = { seatButton: a.id };
      side.castShadow = true;
      const under = new THREE.Mesh(contact, this.shadowMat());
      under.position.set(0.03, 0.004, 0.04);
      const glow = new THREE.Mesh(ringGeo, this.keep(new THREE.MeshBasicMaterial({ color: 0xffd58a, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false })));
      glow.position.y = 0.006;
      // pressed: a dark ring where the medallion sinks into the table
      const sink = new THREE.Mesh(ringGeo, this.keep(new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0, depthWrite: false })));
      sink.position.y = 0.007;
      glow.visible = sink.visible = false;
      // the chit tipped up toward me like a lectern (seen at the table's low angle, a flat one's face is squashed); its
      // contact shadow stays flat on the table
      const chitG = new THREE.Group();
      chitG.add(glow, sink, side, top);
      chitG.rotation.x = CHIT_TILT;
      chitG.position.y = Math.sin(CHIT_TILT) * BUTTON_R;
      group.add(under, chitG);
      const lx = lxOf(a.id);
      const [wx, wz] = toWorld(mine, lx, ROW_Z);
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const [tx, tz] = toWorld(mine, lx, ROW_Z - 0.68);
      const b: Button = { group, top, side, edge, glow, sink, canvas, tex, typed: "", press: 0, lift: 0, tip: new THREE.Vector3(tx, 0.2, tz) };
      drawSeatIcon(canvas, a.id);
      tex.needsUpdate = true;
      this.buttons.set(a.id, b);
    });
    // one deliberate divider between the two groups: a short brass inlay in the table
    if (!mine.duel) {
      const divider = new THREE.Mesh(this.keep(new THREE.BoxGeometry(0.045, 0.012, BUTTON_R * 1.5)), this.keep(new THREE.MeshStandardMaterial({ color: 0xb48a4a, roughness: 0.4, metalness: 0.8 })));
      const [dx, dz] = toWorld(mine, x0 + (groups[0]!.length - 1) * PITCH + (DIVIDE + PITCH) / 2, ROW_Z);
      divider.position.set(dx, 0.006, dz);
      divider.rotation.y = mine.rot;
      this.group.add(divider);
    }
    const canvas = document.createElement("canvas");
    const tex = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(this.keep(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, toneMapped: false })));
    sprite.renderOrder = 20;
    sprite.visible = false;
    this.group.add(sprite);
    this.label = { sprite, canvas, tex };
  }

  /** A seat's life, with any clicks still on their way (shown under the number). */
  setLife(player: string, life: number, pending: number): void {
    const h = this.hearts.get(player);
    if (!h) return;
    const r = h.roll;
    r.pending = pending;
    if (r.at === null) { // (first sight of this heart: no roll)
      r.from = r.to = r.at = life;
    } else if (life !== r.to) {
      const delta = Math.abs(life - r.at);
      r.from = r.at;
      r.to = life;
      r.start = performance.now();
      r.dur = motionMs(Math.min(600, 300 + delta * 25), false); // (a number is feedback: reduced motion keeps it)
    }
    this.drawLife(h, r.at);
  }

  private drawLife(h: Heart, shown: number): void {
    const key = `${shown}|${h.roll.pending}|${h.hot}|${h.pressed}|${this.readOnly}`;
    if (h.shown === key) return;
    h.shown = key;
    drawHeart(h.canvas, h.color, shown, h.roll.pending, h.hot, h.pressed, this.readOnly);
    h.tex.needsUpdate = true;
  }

  /** Out of the game: the hearts are totals, not controls (no halves to click). */
  private readOnly = false;

  /** A heart half pressed: darker and sunk while the pointer is held down on it (at least a moment), then back. */
  pressHeart(player: string, side: -1 | 1): void {
    const h = this.hearts.get(player);
    if (!h || this.readOnly) return;
    h.pressed = side;
    h.pressAt = performance.now();
    this.heartHeld = player;
    this.drawLife(h, h.roll.at ?? 0);
    const release = () => { if (this.heartHeld === player) this.heartHeld = null; };
    window.addEventListener("pointerup", release, { once: true });
    window.addEventListener("pointercancel", release, { once: true });
  }

  private heartHeld: string | null = null;

  /** The heart half under the pointer (null: none), lit so you see which way a click goes. */
  hoverHeart(player: string | null, side: -1 | 1 | undefined): void {
    if (this.readOnly) player = null;
    for (const [pid, h] of this.hearts) {
      const hot = pid === player ? side ?? 0 : 0;
      if (h.hot === hot) continue;
      h.hot = hot;
      this.drawLife(h, h.roll.at ?? 0);
    }
  }

  setTyped(id: SeatActionId | null, n: string): void {
    for (const [bid, b] of this.buttons) {
      const typed = bid === id ? n : "";
      if (b.typed === typed) continue;
      b.typed = typed;
      drawSeatIcon(b.canvas, bid, typed);
      b.tex.needsUpdate = true;
    }
  }

  /**
   * Each commander's tax beside its well in the command zone (and a well for a partner when there is one): a column of
   * brass coins in a socket, one per cast from the command zone (the tax to pay is on the well's plate). `commanders`: per seat,
   * its commanders' keys in slot order, with their tax.
   */
  setCommanders(seats: Seat[], commanders: Record<string, { key: string; tax: number }[]>, colors: Record<string, string>, viewRot = 0): void {
    const key = JSON.stringify([seats.map((s) => [s.player, (commanders[s.player] ?? []).map((c) => c.key)]), colors]);
    if (key !== this.taxKey) {
      this.taxKey = key;
      for (const extra of this.slots) this.group.remove(extra);
      this.slots = [];
      this.taxes.clear();
      const duel = seats.length === 2;
      const shared = this.taxShared();
      let total = 0;
      for (const seat of seats) {
        const list = commanders[seat.player] ?? [];
        list.slice(0, COMMAND_SLOTS.length).forEach((c, i) => {
          let partnerWell: Tax["well"];
          if (i > 0) {
            // the partner's (or background's) well, as the commander's (TableScene draws that one with the piles)
            const at = commandSlot(seat, i);
            const art: WellArt = { zone: "command", label: i === 1 ? "Partner" : "Command", count: null, duel, color: colors[seat.player] ?? "#888", well: COMMAND_WELL, plateW: plateWidth("command", duel), plateH: plateDepth(seat), plateDx: plateOffset("command"), stretch: wellStretch(duel, seat.side === "north") };
            const canvas = document.createElement("canvas");
            drawWell(canvas, art);
            const tex = this.keep(new THREE.CanvasTexture(canvas));
            tex.colorSpace = THREE.SRGBColorSpace;
            tex.anisotropy = 8;
            const [W, H] = wellCanvasSize(art);
            const well = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(W / WELL_PX, H / WELL_PX)),
              this.keep(new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false, roughness: 0.72, metalness: 0, envMapIntensity: 0.25 })));
            well.rotation.x = -Math.PI / 2;
            well.rotation.z = viewRot; // its plate upright from my seat
            const [sx, sz] = toWorld(seat, ...wellPiece(seat, at, "command").at);
            well.position.set(sx, 0.0034, sz); // as the other wells (TableScene SLOT_Y)
            well.renderOrder = -1;
            well.receiveShadow = true;
            this.group.add(well);
            this.slots.push(well);
            partnerWell = { art, canvas, tex };
          }
          // the socket, sunk in the wood beside the well; the coins stand in it
          const [bx, bz] = toWorld(seat, ...taxSpot(seat, i));
          const socket = new THREE.Mesh(shared.socketGeo, shared.socketMat);
          socket.position.set(bx, 0.0036, bz);
          socket.renderOrder = -1;
          socket.userData = { tax: c.key };
          // what the pointer finds: the column, as tall as its coins (scaled with them)
          const hit = new THREE.Mesh(shared.hitGeo, shared.hitMat);
          hit.position.set(bx, 0, bz);
          hit.visible = false;
          hit.userData = { tax: c.key };
          // the tax's number on the well's plate clicks like the coins (an invisible box over it, nearer the eye than the plate)
          const readout = new THREE.Mesh(shared.readoutGeo, shared.hitMat);
          const [rx, rz] = toWorld(seat, ...taxReadoutSpot(seat, i));
          readout.position.set(rx, 0.03, rz);
          readout.visible = false;
          readout.userData = { tax: c.key };
          this.group.add(socket, hit, readout);
          this.slots.push(socket, hit, readout);
          this.taxes.set(c.key, { key: c.key, base: new THREE.Vector3(bx, 0, bz), salt: total * 7 + i, first: total, socket, hit, readout, shown: -1, coins: 0, dropAt: 0, dropping: false, well: partnerWell });
          total += TAX_STACK;
        });
      }
      // every seat's coins: one instanced column of cylinders (one draw call per face kind)
      if (this.coins) this.group.remove(this.coins);
      this.coins = new THREE.InstancedMesh(shared.coinGeo, shared.coinMats, Math.max(1, total));
      this.coins.count = 0;
      this.coins.castShadow = true;
      this.coins.frustumCulled = false;
      this.group.add(this.coins);
      this.coinsDirty = true;
    }
    const now = performance.now();
    for (const list of Object.values(commanders)) {
      for (const c of list) {
        const t = this.taxes.get(c.key);
        if (!t || t.shown === c.tax) continue;
        const coins = Math.min(TAX_STACK, taxCasts(c.tax));
        // one more coin: it drops onto the stack (a short fall; reduced motion and a first sight place it)
        t.dropping = t.shown >= 0 && coins > t.coins;
        t.dropAt = now;
        t.shown = c.tax;
        t.coins = coins;
        // the tax to pay on its well's plate (TableScene draws the commander's well; a partner's is here)
        if (t.well) {
          t.well.art.tax = c.tax;
          drawWell(t.well.canvas, t.well.art);
          t.well.tex.needsUpdate = true;
        }
        t.hit.scale.set(1, Math.max(1, coins), 1);
        this.coinsDirty = true;
      }
    }
    if (!this.fontAsked) { // a partner's plate drawn again once its fonts are in (they normally are by now)
      this.fontAsked = true;
      void whenWellFontsReady().then(() => {
        for (const t of this.taxes.values()) {
          if (!t.well) continue;
          drawWell(t.well.canvas, t.well.art);
          t.well.tex.needsUpdate = true;
        }
      });
    }
  }

  /** The tax pieces' shared geometry and materials (made once, disposed with the props). */
  private taxShared() {
    if (this.shared) return this.shared;
    const face = document.createElement("canvas");
    face.width = face.height = 256;
    drawTaxCoinFace(face);
    const faceTex = this.keep(new THREE.CanvasTexture(face));
    faceTex.colorSpace = THREE.SRGBColorSpace;
    faceTex.anisotropy = 8;
    // the reeded edge: fine vertical grooves
    const reed = document.createElement("canvas");
    reed.width = 256;
    reed.height = 8;
    const rg = reed.getContext("2d")!;
    for (let x = 0; x < 256; x += 4) {
      rg.fillStyle = "#f0d49a";
      rg.fillRect(x, 0, 2, 8);
      rg.fillStyle = "#8a6430";
      rg.fillRect(x + 2, 0, 2, 8);
    }
    const reedTex = this.keep(new THREE.CanvasTexture(reed));
    reedTex.colorSpace = THREE.SRGBColorSpace;
    const sock = document.createElement("canvas");
    sock.width = sock.height = 128;
    drawTaxSocket(sock);
    const sockTex = this.keep(new THREE.CanvasTexture(sock));
    sockTex.colorSpace = THREE.SRGBColorSpace;
    const brass = { metalness: 0.85, roughness: 0.38, envMapIntensity: 1.1 };
    const coinGeo = this.keep(new THREE.CylinderGeometry(COIN.r, COIN.r, COIN.h, 40));
    const hitGeo = this.keep(new THREE.CylinderGeometry(COIN.r * 1.25, COIN.r * 1.25, COIN.h * 1.4, 12).translate(0, (COIN.h * 1.4) / 2, 0));
    this.shared = {
      coinGeo,
      // a cylinder's groups: its side, its top, its bottom
      coinMats: [
        this.keep(new THREE.MeshStandardMaterial({ color: 0xffffff, map: reedTex, ...brass })),
        this.keep(new THREE.MeshStandardMaterial({ color: 0xffffff, map: faceTex, ...brass, roughness: 0.42 })),
        this.keep(new THREE.MeshStandardMaterial({ color: 0x8a6430, ...brass })),
      ],
      socketGeo: this.keep(new THREE.PlaneGeometry(COIN.r * 2.5, COIN.r * 2.5).rotateX(-Math.PI / 2)),
      socketMat: this.keep(new THREE.MeshStandardMaterial({ map: sockTex, transparent: true, depthWrite: false, roughness: 0.8, metalness: 0, emissive: 0xffc870, emissiveIntensity: 0 })),
      hitGeo,
      hitMat: this.keep(new THREE.MeshBasicMaterial({ visible: false })),
      readoutGeo: this.keep(new THREE.BoxGeometry(TAX_READOUT.w, 0.06, TAX_READOUT.h)),
    };
    return this.shared;
  }

  private shared: {
    coinGeo: THREE.BufferGeometry; coinMats: THREE.Material[]; socketGeo: THREE.BufferGeometry; socketMat: THREE.MeshStandardMaterial;
    hitGeo: THREE.BufferGeometry; hitMat: THREE.Material; readoutGeo: THREE.BufferGeometry;
  } | null = null;
  private coins: THREE.InstancedMesh | null = null;
  private coinsDirty = false;
  private coinM = new THREE.Matrix4();
  private coinQ = new THREE.Quaternion();
  private coinP = new THREE.Vector3();
  private coinS = new THREE.Vector3(1, 1, 1);
  private coinUp = new THREE.Vector3(0, 1, 0);

  /** Lay the coins out (only while one falls, or after a change). */
  private layCoins(now: number, reduced: boolean): void {
    const coins = this.coins;
    if (!coins || !this.coinsDirty) return;
    let n = 0;
    let falling = false;
    for (const t of this.taxes.values()) {
      for (let i = 0; i < t.coins; i++) {
        // hand-stacked: each a little off true, turned a little
        const j = (k: number) => Math.sin((t.salt + 1) * 12.9898 + i * 78.233 + k * 37.719) * 0.5;
        let y = COIN.h * (i + 0.5) + 0.002;
        if (i === t.coins - 1 && t.dropping && !reduced) {
          const dur = motionMs(COIN_DROP_MS, false);
          const k = dur > 0 ? Math.min(1, (now - t.dropAt) / dur) : 1;
          if (k < 1) {
            y += COIN_DROP_H * (1 - k * k); // falling (gravity's ease-in)
            falling = true;
          } else t.dropping = false;
        }
        // (each a little toward the viewer's lower right of the one under it: seen from above, a stack shows every coin's rim)
        this.coinP.set(t.base.x + j(1) * 0.02 + i * 0.012, y, t.base.z + j(2) * 0.02 + i * 0.022 - (t.coins - 1) * 0.011);
        this.coinQ.setFromAxisAngle(this.coinUp, j(3) * 1.2);
        this.coinM.compose(this.coinP, this.coinQ, this.coinS);
        coins.setMatrixAt(n++, this.coinM);
      }
      if (reduced) t.dropping = false;
    }
    coins.count = n;
    coins.instanceMatrix.needsUpdate = true;
    this.coinsDirty = falling;
  }

  /** Where a commander's tax column stands (its middle; on the socket when there are no coins). */
  taxWorld(key: string): THREE.Vector3 | null {
    const t = this.taxes.get(key);
    return t ? t.base.clone().setY((Math.max(1, t.coins) * COIN.h) / 2) : null;
  }

  /** The commander-tax key the pointer is over, if any (TableScene's tooltip). */
  taxUnder(): string | null {
    return this.taxHover?.key ?? null;
  }

  private fontAsked = false;
  private blobMat: THREE.MeshBasicMaterial | null = null;
  private shadowMat(): THREE.MeshBasicMaterial {
    return (this.blobMat ??= this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
  }

  private slots: THREE.Mesh[] = [];

  hover(id: SeatActionId | null): void {
    if (id === this.hovered) return;
    this.hovered = id;
    const label = this.label;
    const b = id ? this.buttons.get(id) : undefined;
    if (!label) return;
    label.sprite.visible = !!b;
    if (!b || !id) return;
    const aspect = drawLabel(label.canvas, SEAT_ACTIONS.find((a) => a.id === id)?.label ?? "");
    label.tex.dispose(); // (the canvas changed size: a new texture)
    label.tex = new THREE.CanvasTexture(label.canvas);
    label.tex.colorSpace = THREE.SRGBColorSpace;
    (label.sprite.material as THREE.SpriteMaterial).map = label.tex;
    (label.sprite.material as THREE.SpriteMaterial).needsUpdate = true;
    label.sprite.scale.set(LABEL_H * aspect, LABEL_H, 1);
    label.sprite.position.copy(b.tip);
  }

  /** The hovered button's name, over it (one plate, redrawn for each button). */
  private label: { sprite: THREE.Sprite; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture } | null = null;

  /** A button pressed: sunk while the pointer is held down on it (at least a moment), then back up. */
  press(id: SeatActionId): void {
    const b = this.buttons.get(id);
    if (!b) return;
    b.press = performance.now();
    this.held = id;
    const release = () => { if (this.held === id) this.held = null; };
    window.addEventListener("pointerup", release, { once: true });
    window.addEventListener("pointercancel", release, { once: true });
  }

  private held: SeatActionId | null = null;

  /** Hearts turn to the viewer (upright for everyone); buttons light when hovered and dip when pressed. */
  tick(_t: number, camera: THREE.Camera, reduced: boolean): void {
    camera.getWorldPosition(this.tmp);
    for (const h of this.hearts.values()) {
      const p = h.group.position;
      h.group.rotation.y = Math.atan2(this.tmp.x - p.x, this.tmp.z - p.z);
      // its scale eases with the camera (a low orbit makes it smaller: TableScene fitHearts)
      if (h.fit !== h.fitTo) {
        h.fit = reduced || Math.abs(h.fitTo - h.fit) < 0.002 ? h.fitTo : h.fit + (h.fitTo - h.fit) * 0.2;
        h.group.scale.setScalar(h.fit);
      }
    }
    const now = performance.now();
    for (const [pid, h] of this.hearts) { // a pressed half comes back up once let go (after a moment)
      if (!h.pressed || pid === this.heartHeld || now - h.pressAt < 160) continue;
      h.pressed = 0;
      this.drawLife(h, h.roll.at ?? 0);
    }
    for (const h of this.hearts.values()) { // a life total rolling to its new value (only while one changes)
      const r = h.roll;
      if (r.at === null || r.at === r.to) continue;
      r.at = lifeRollAt(r, now);
      this.drawLife(h, r.at);
    }
    for (const [id, b] of this.buttons) {
      // hovered: the medallion rises a little, its face and edge catch more light and a warm ring glows on the table
      // under it; pressed: it dips into the table and comes back
      // pressed (held down, or for a moment after a click): sunk into the table, darker, a dark ring round it, no glow
      const pressed = id === this.held || now - b.press < 180;
      const on = id === this.hovered && !pressed;
      b.lift = on ? b.lift + (1 - b.lift) * (reduced ? 1 : 0.3) : 0; // (the glow goes as soon as the pointer leaves)
      (b.top.material as THREE.MeshBasicMaterial).color.setScalar(pressed ? 0.74 : 1 + 0.28 * b.lift);
      b.edge.emissiveIntensity = 0.35 * b.lift;
      (b.glow.material as THREE.MeshBasicMaterial).opacity = 0.42 * b.lift;
      (b.sink.material as THREE.MeshBasicMaterial).opacity = pressed ? 0.6 : 0;
      b.glow.visible = b.lift > 0.01; // (drawn only while showing: no draw calls for empty rings)
      b.sink.visible = pressed;
      const dip = pressed ? -0.05 : 0;
      b.top.position.y = BUTTON_H + 0.002 + 0.045 * b.lift + dip;
      b.side.position.y = BUTTON_H / 2 + 0.045 * b.lift + dip;
    }
    // the name plate hides while a panel (the Bag of Extras it opened, a dialog) is up
    if (this.label) this.label.sprite.visible = !!this.hovered && !useGame.getState().dialog;
    if (this.shared) this.shared.socketMat.emissiveIntensity = 0;
    if (this.taxHover && this.shared) this.shared.socketMat.emissiveIntensity = 0.12; // (one socket material: a faint warmth on all, only while one is hovered)
    // a new coin falling onto its stack (game state never waits for it: the plate already says the new tax)
    this.layCoins(now, reduced);
    this.cam = camera;
  }

  /**
   * Which tax medallion the pointer is over (the table's own picking reports only cards, hearts and buttons to these
   * props): a small raycast against the pucks alone, on the pointer's moves over the table's canvas.
   */
  private taxHover: Tax | null = null;
  private cam: THREE.Camera | null = null;
  private ray = new THREE.Raycaster();
  private onPointer = (e: PointerEvent) => {
    const canvas = e.target as HTMLElement | null;
    this.taxHover = null;
    if (!this.cam || !this.taxes.size || !(canvas instanceof HTMLCanvasElement) || !canvas.classList.contains("table3d-canvas")) return;
    const r = canvas.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), this.cam);
    const hit = this.ray.intersectObjects([...this.taxes.values()].flatMap((t) => [t.hit, t.socket, t.readout]), false)[0];
    const key = hit?.object.userData.tax as string | undefined;
    this.taxHover = key ? this.taxes.get(key) ?? null : null;
  };
  private listening = typeof window !== "undefined" && (window.addEventListener("pointermove", this.onPointer, { passive: true }), true);

  /** What the pointer can hit. */
  targets(): THREE.Object3D[] {
    const out: THREE.Object3D[] = [];
    for (const h of this.hearts.values()) out.push(h.face);
    for (const t of this.taxes.values()) out.push(t.hit, t.socket, t.readout);
    for (const b of this.buttons.values()) out.push(b.top, b.side);
    return out;
  }

  heartWorld(player: string): THREE.Vector3 | null {
    return this.hearts.get(player)?.group.position.clone() ?? null;
  }

  /** The middle of a heart's right-hand (side −1: left-hand) edge as `camera` sees it (the heart turns to face it): a 1v1 plate starts there. */
  heartEdge(player: string, camera: THREE.Camera, side: 1 | -1 = 1): THREE.Vector3 | null {
    const h = this.hearts.get(player);
    if (!h) return null;
    camera.getWorldPosition(this.tmp);
    const p = h.group.position;
    const toCam = this.tmp.sub(p).setY(0);
    if (toCam.lengthSq() < 1e-6) toCam.set(0, 0, 1);
    toCam.normalize();
    // the face's right, seen from the camera: up × toward-camera
    const right = new THREE.Vector3(toCam.z, 0, -toCam.x);
    return p.clone().addScaledVector(right, side * HEART_W * 0.47 * h.fit).setY(HEART_Y + h.face.position.y * h.fit);
  }

  /** The scale a heart is to settle at (1: its size on the table), and the scale it shows now (its plate follows it). */
  fitHeart(player: string, f: number): void {
    const h = this.hearts.get(player);
    if (h) h.fitTo = f;
  }
  heartFit(player: string): number {
    return this.hearts.get(player)?.fit ?? 1;
  }

  /** A heart's face's corners (world) at scale `f`, turned to face an eye at `eye` (as tick turns it). */
  heartCorners(player: string, eye: THREE.Vector3, f: number): THREE.Vector3[] | null {
    const h = this.hearts.get(player);
    if (!h) return null;
    const p = h.group.position;
    const turn = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, Math.atan2(eye.x - p.x, eye.z - p.z), 0));
    h.face.updateMatrix();
    const m = new THREE.Matrix4().compose(p, turn, new THREE.Vector3(f, f, f)).multiply(h.face.matrix);
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => new THREE.Vector3((sx! * HEART_W) / 2, (sy! * HEART.h) / 2, 0).applyMatrix4(m));
  }

  /** My seat buttons' medallions (world centres and radius), which a heart must never cover. */
  buttonDiscs(): { at: THREE.Vector3; r: number }[] {
    return [...this.buttons.values()].map((b) => ({ at: b.group.position.clone(), r: BUTTON_R }));
  }

  buttonWorld(id: SeatActionId): THREE.Vector3 | null {
    const b = this.buttons.get(id);
    return b ? b.group.position.clone().setY(BUTTON_H) : null;
  }

  private keep<T extends { dispose(): void }>(x: T): T {
    this.disposables.push(x);
    return x;
  }

  private clear(): void {
    this.group.clear();
    this.taxes.clear();
    this.taxKey = "";
    this.slots = [];
    this.shared = null;
    this.coins = null;
    this.hearts.clear();
    this.buttons.clear();
    this.blobMat = null;
    this.label?.tex.dispose();
    this.label = null;
    this.hovered = null;
    this.taxHover = null;
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.unskip();
    if (this.listening) window.removeEventListener("pointermove", this.onPointer);
    this.clear();
  }
}
