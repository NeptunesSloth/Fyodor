/**
 * Things at each seat of the 3D table, after the Oops I Baked a Pie table:
 * - Life: the Oops heart. Black, edged thick in the seat's colour, the total big in its middle, ▼ on its left and ▲
 *   on its right. It lies at the mat's inner corner by the middle of the table, a little above the felt, turned so
 *   you read every seat's number upright. Click its left half −1, its right half +1, right-click for 5, or the wheel
 *   (TableScene). Attack arrows aim at it.
 * - Your seat's buttons, as the Oops table has them: in a row just past your mat's near edge (from its left end), bevelled
 *   brass medallions with stamped symbols (game/seatIcons.ts), Untap, Draw, Scry, Mill and Reveal, then Mulligan apart to
 *   the right and the Bag of Extras past it.
 * - Each commander's tax: a small brass medallion by its command-zone slot, dim at 0 and lit once there is tax to pay.
 */
import * as THREE from "three";
import { SEAT_ACTIONS, type SeatActionId } from "../game/seatActions";
import { useGame } from "../state/gameStore";
import { drawSeatIcon, drawTaxMedallion, whenIconFontReady } from "../game/seatIcons";
import { motionMs, onMotionSkip } from "../game/motion/timing";
import { CARD_H, CARD_W, COMMAND_SLOTS, heartSpot, MAT_D, toWorld, type Seat } from "./layout";
import { slotTexture } from "./textures";

const HEART_W = 1.45;
const HEART_Y = 0.16;
const BUTTON_R = 0.33;
const BUTTON_H = 0.08;
/** The buttons' row: just past my mat's near edge, one medallion every PITCH, the two groups apart by DIVIDE. */
const ROW_Z = MAT_D / 2 + 0.44;
const PITCH = 0.8;
const DIVIDE = 0.45;
const TAX_R = 0.38;
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
const TAX_H = 0.05;

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

function drawHeart(canvas: HTMLCanvasElement, color: string, life: number, pending: number): void {
  const g = canvas.getContext("2d")!;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.save();
  g.scale(canvas.width / 256, canvas.height / 232);
  const heart = heartPath();
  g.fillStyle = "#050505";
  g.fill(heart);
  g.lineJoin = "round";
  g.lineWidth = 15;
  g.strokeStyle = color;
  g.stroke(heart);
  g.textAlign = "center";
  g.textBaseline = "middle";
  const n = String(life + pending);
  g.fillStyle = life + pending <= 0 ? "#ff8a7a" : "#e6e2da";
  g.font = `700 ${n.length > 2 ? 64 : 84}px Inter, "Helvetica Neue", Arial, sans-serif`;
  g.fillText(n, 128, 104);
  // ▼ and ▲: the halves you click
  g.fillStyle = "#8e8a84";
  g.beginPath();
  g.moveTo(40, 98); g.lineTo(60, 98); g.lineTo(50, 112); g.closePath();
  g.moveTo(196, 112); g.lineTo(216, 112); g.lineTo(206, 98); g.closePath();
  g.fill();
  if (pending) {
    g.font = "800 34px Inter, Arial, sans-serif";
    g.fillStyle = pending > 0 ? "#9ee68a" : "#ff9a8a";
    g.fillText(pending > 0 ? `+${pending}` : `${pending}`, 128, 160);
  }
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
interface Tax { mesh: THREE.Mesh; edge: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; shown: number; changed: number }

interface Heart {
  group: THREE.Group; face: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; shown: string;
  /** -- table motion -- the life total on the heart rolls to a new value (docs/GAME_UI_MOTION_RESEARCH.md §4: 300–600 ms scaled to the
   * change): what it shows now, where it's going, and the clicks still on their way. */
  roll: { from: number; to: number; start: number; dur: number; at: number | null; pending: number };
}
/**
 * A seat button: its face, brass edge and glow ring; `lift`, how far it rises while hovered (eased); `tip`, where its name
 * shows while hovered (just over the mat's edge above it, as seen from the seat).
 */
interface Button {
  group: THREE.Group; top: THREE.Mesh; side: THREE.Mesh; edge: THREE.MeshStandardMaterial; glow: THREE.Mesh;
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
  private look = new THREE.Vector3();
  /** Any click or key lands every rolling life total at once (game/motion/timing.ts). */
  private unskip = onMotionSkip(() => {
    for (const h of this.hearts.values()) {
      if (h.roll.at !== null && h.roll.at !== h.roll.to) {
        h.roll.at = h.roll.to;
        this.drawLife(h, h.roll.at);
      }
    }
  });

  /** Hearts for every seat; buttons for mine (seat colours from the view). */
  rebuild(seats: Seat[], me: string, colors: Record<string, string>): void {
    this.clear();
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
      const face = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(HEART_W, HEART_W * (232 / 256))), this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false })));
      face.rotation.x = -Math.PI / 2 + 0.7;
      face.userData = { heart: seat.player };
      face.position.y = Math.sin(0.7) * HEART_W * 0.45; // tipped up from its bottom edge, which rests over the felt
      const shadow = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(HEART_W * 1.05, HEART_W).rotateX(-Math.PI / 2)), this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
      shadow.position.y = -HEART_Y + 0.006;
      const group = new THREE.Group();
      group.add(shadow, face);
      const [wx, wz] = toWorld(seat, ...heartSpot(seat));
      group.position.set(wx, HEART_Y, wz);
      this.group.add(group);
      this.hearts.set(seat.player, { group, face, canvas, tex, color, shown: "", roll: { from: 0, to: 0, start: 0, dur: 0, at: null, pending: 0 } });
    }
    const mine = seats.find((s) => s.player === me);
    if (!mine) return;
    // the medallions: a face drawn lit from the top left (the same picture as the 2D table's buttons, unlit, its rim's
    // edge soft in the texture's alpha), a brass edge lit by the table's light, a contact shadow, and a glow ring for hover
    const contact = this.keep(new THREE.PlaneGeometry(BUTTON_R * 2.7, BUTTON_R * 2.7).rotateX(-Math.PI / 2));
    const faceGeo = this.keep(new THREE.PlaneGeometry(BUTTON_R * 2, BUTTON_R * 2).rotateX(-Math.PI / 2));
    const sideGeo = this.keep(new THREE.CylinderGeometry(BUTTON_R * 0.96, BUTTON_R * 1.02, BUTTON_H, 64));
    const ringGeo = this.keep(new THREE.RingGeometry(BUTTON_R * 1.04, BUTTON_R * 1.32, 64).rotateX(-Math.PI / 2));
    const groups = [SEAT_ACTIONS.filter((a) => a.id !== "mulligan" && a.id !== "extras"), SEAT_ACTIONS.filter((a) => a.id === "mulligan" || a.id === "extras")];
    const span = (groups[0]!.length + groups[1]!.length - 1) * PITCH + DIVIDE;
    const x0 = 0.7 - span; // (ends a little right of the mat's middle: the turn dial covers the screen's bottom right)
    const lxOf = (id: SeatActionId) => {
      const k = groups[0]!.findIndex((a) => a.id === id);
      return k >= 0 ? x0 + k * PITCH : x0 + (groups[0]!.length - 1) * PITCH + DIVIDE + (groups[1]!.findIndex((a) => a.id === id) + 1) * PITCH;
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
      const edge = this.keep(new THREE.MeshStandardMaterial({ color: 0x8a6432, roughness: 0.42, metalness: 0.75, emissive: 0xffc870, emissiveIntensity: 0 }));
      const side = new THREE.Mesh(sideGeo, edge);
      side.position.y = BUTTON_H / 2;
      side.userData = { seatButton: a.id };
      side.castShadow = true;
      const under = new THREE.Mesh(contact, this.shadowMat());
      under.position.set(0.03, 0.004, 0.04);
      const glow = new THREE.Mesh(ringGeo, this.keep(new THREE.MeshBasicMaterial({ color: 0xffd58a, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false })));
      glow.position.y = 0.006;
      group.add(under, glow, side, top);
      const lx = lxOf(a.id);
      const [wx, wz] = toWorld(mine, lx, ROW_Z);
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const [tx, tz] = toWorld(mine, lx, ROW_Z - 0.68);
      const b: Button = { group, top, side, edge, glow, canvas, tex, typed: "", press: 0, lift: 0, tip: new THREE.Vector3(tx, 0.2, tz) };
      drawSeatIcon(canvas, a.id);
      tex.needsUpdate = true;
      this.buttons.set(a.id, b);
    });
    // one deliberate divider between the two groups: a short brass inlay in the table
    const divider = new THREE.Mesh(this.keep(new THREE.BoxGeometry(0.045, 0.012, BUTTON_R * 1.5)), this.keep(new THREE.MeshStandardMaterial({ color: 0xb48a4a, roughness: 0.4, metalness: 0.8 })));
    const [dx, dz] = toWorld(mine, x0 + (groups[0]!.length - 1) * PITCH + (DIVIDE + PITCH) / 2, ROW_Z);
    divider.position.set(dx, 0.006, dz);
    divider.rotation.y = mine.rot;
    this.group.add(divider);
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
    const key = `${shown}|${h.roll.pending}`;
    if (h.shown === key) return;
    h.shown = key;
    drawHeart(h.canvas, h.color, shown, h.roll.pending);
    h.tex.needsUpdate = true;
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
   * Each commander's tax counter beside its slot in the command zone (and a slot for a partner when there is one).
   * `commanders`: per seat, its commanders' keys in slot order, with their tax.
   */
  setCommanders(seats: Seat[], commanders: Record<string, { key: string; tax: number }[]>, _colors: Record<string, string>): void {
    const key = JSON.stringify(seats.map((s) => [s.player, (commanders[s.player] ?? []).map((c) => c.key)]));
    if (key !== this.taxKey) {
      this.taxKey = key;
      for (const t of this.taxes.values()) this.group.remove(t.mesh, t.edge);
      this.taxes.clear();
      for (const extra of this.slots) this.group.remove(extra);
      this.slots = [];
      for (const seat of seats) {
        const list = commanders[seat.player] ?? [];
        list.slice(0, COMMAND_SLOTS.length).forEach((c, i) => {
          if (i > 0) {
            // the partner's slot, outlined on the felt like the others
            const slot = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(CARD_W * 1.05, CARD_H * 1.05)),
              this.keep(new THREE.MeshBasicMaterial({ map: this.keep(slotTexture(i === 1 ? "Partner" : "Command", "#b39458")), transparent: true, depthWrite: false })));
            slot.rotation.x = -Math.PI / 2;
            slot.rotation.z = seat.rot;
            const [sx, sz] = toWorld(seat, ...COMMAND_SLOTS[i]!);
            slot.position.set(sx, 0.003, sz);
            this.group.add(slot);
            this.slots.push(slot);
          }
          const canvas = document.createElement("canvas");
          canvas.width = canvas.height = 256;
          const tex = this.keep(new THREE.CanvasTexture(canvas));
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 8;
          // a low brass puck under the command zone, its face (unlit, drawn lit, its edge soft in the texture's alpha) turned
          // to whoever looks (tick); a partner's beside it, toward the mat
          const mesh = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(TAX_R * 2, TAX_R * 2).rotateX(-Math.PI / 2)),
            this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
          const edge = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(TAX_R * 0.96, TAX_R * 1.02, TAX_H, 64)), this.taxEdge());
          const [sx0, sz0] = COMMAND_SLOTS[0]!;
          const inward = sx0 < 0 ? 1 : -1;
          const [wx, wz] = toWorld(seat, sx0 + inward * (0.14 + i * (TAX_R * 2 + 0.14)), sz0 + CARD_H / 2 + 0.03 + TAX_R);
          mesh.position.set(wx, TAX_H + 0.002, wz);
          edge.position.set(wx, TAX_H / 2, wz);
          mesh.userData = { tax: c.key };
          edge.userData = { tax: c.key };
          const under = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(TAX_R * 2.7, TAX_R * 2.7).rotateX(-Math.PI / 2)), this.shadowMat());
          under.position.set(wx + 0.03, 0.004, wz + 0.04);
          this.group.add(under, edge, mesh);
          this.slots.push(under); // (removed with the slots when the commanders change)
          this.taxes.set(c.key, { mesh, edge, canvas, tex, shown: -1, changed: 0 });
        });
      }
    }
    for (const list of Object.values(commanders)) {
      for (const c of list) {
        const t = this.taxes.get(c.key);
        if (!t || t.shown === c.tax) continue;
        if (t.shown >= 0) t.changed = performance.now(); // (a change, not the first drawing: it hops)
        t.shown = c.tax;
        drawTaxMedallion(t.canvas, c.tax);
        t.tex.needsUpdate = true;
      }
    }
    if (!this.fontAsked) { // drawn again once the number font is in (it normally is by now)
      this.fontAsked = true;
      void whenIconFontReady().then(() => {
        for (const t of this.taxes.values()) {
          if (t.shown < 0) continue;
          drawTaxMedallion(t.canvas, t.shown);
          t.tex.needsUpdate = true;
        }
      });
    }
  }

  private fontAsked = false;
  private blobMat: THREE.MeshBasicMaterial | null = null;
  private shadowMat(): THREE.MeshBasicMaterial {
    return (this.blobMat ??= this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
  }
  private edgeMat: THREE.MeshStandardMaterial | null = null;
  private taxEdge(): THREE.MeshStandardMaterial {
    return (this.edgeMat ??= this.keep(new THREE.MeshStandardMaterial({ color: 0x8a6432, roughness: 0.42, metalness: 0.75 })));
  }

  private slots: THREE.Mesh[] = [];

  taxWorld(key: string): THREE.Vector3 | null {
    return this.taxes.get(key)?.mesh.position.clone() ?? null;
  }

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

  press(id: SeatActionId): void {
    const b = this.buttons.get(id);
    if (b) b.press = performance.now();
  }

  /** Hearts turn to the viewer (upright for everyone); buttons light when hovered and dip when pressed. */
  tick(_t: number, camera: THREE.Camera, reduced: boolean): void {
    camera.getWorldPosition(this.tmp);
    for (const h of this.hearts.values()) {
      const p = h.group.position;
      h.group.rotation.y = Math.atan2(this.tmp.x - p.x, this.tmp.z - p.z);
    }
    const now = performance.now();
    for (const h of this.hearts.values()) { // a life total rolling to its new value (only while one changes)
      const r = h.roll;
      if (r.at === null || r.at === r.to) continue;
      r.at = lifeRollAt(r, now);
      this.drawLife(h, r.at);
    }
    for (const [id, b] of this.buttons) {
      // hovered: the medallion rises a little, its face and edge catch more light and a warm ring glows on the table
      // under it; pressed: it dips into the table and comes back
      const on = id === this.hovered;
      b.lift += ((on ? 1 : 0) - b.lift) * (reduced ? 1 : 0.3);
      (b.top.material as THREE.MeshBasicMaterial).color.setScalar(1 + 0.28 * b.lift);
      b.edge.emissiveIntensity = 0.35 * b.lift;
      (b.glow.material as THREE.MeshBasicMaterial).opacity = 0.42 * b.lift;
      const since = now - b.press;
      const dip = since < 160 ? -0.035 * Math.sin((since / 160) * Math.PI) : 0;
      b.top.position.y = BUTTON_H + 0.002 + 0.045 * b.lift + dip;
      b.side.position.y = BUTTON_H / 2 + 0.045 * b.lift + dip;
    }
    // the name plate hides while a panel (the Bag of Extras it opened, a dialog) is up
    if (this.label) this.label.sprite.visible = !!this.hovered && !useGame.getState().dialog;
    camera.getWorldDirection(this.look);
    const facing = Math.atan2(-this.look.x, -this.look.z); // the table's "up the screen", for things lying flat on it
    for (const t of this.taxes.values()) {
      // the tax medallion's face turns upright for the viewer (it is round: only its number turns), and hops when it changes
      t.mesh.rotation.y = facing;
      const since = now - t.changed;
      const hop = !reduced && since < 240 ? 1 + 0.14 * Math.sin((since / 240) * Math.PI) : 1;
      t.mesh.scale.setScalar(hop);
    }
  }

  /** What the pointer can hit. */
  targets(): THREE.Object3D[] {
    const out: THREE.Object3D[] = [];
    for (const h of this.hearts.values()) out.push(h.face);
    for (const t of this.taxes.values()) out.push(t.mesh, t.edge);
    for (const b of this.buttons.values()) out.push(b.top, b.side);
    return out;
  }

  heartWorld(player: string): THREE.Vector3 | null {
    return this.hearts.get(player)?.group.position.clone() ?? null;
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
    this.hearts.clear();
    this.buttons.clear();
    this.edgeMat = null;
    this.blobMat = null;
    this.label?.tex.dispose();
    this.label = null;
    this.hovered = null;
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.unskip();
    this.clear();
  }
}
