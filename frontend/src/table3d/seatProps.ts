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
import { drawSeatIcon, drawTaxMedallion, whenIconFontReady } from "../game/seatIcons";
import { motionMs, onMotionSkip } from "../game/motion/timing";
import { CARD_H, CARD_W, COMMAND_SLOTS, heartSpot, MAT_D, taxSpot, toWorld, type Seat } from "./layout";
import { slotTexture } from "./textures";

const HEART_W = 1.45;
const HEART_Y = 0.16;
const BUTTON_R = 0.26;
const BUTTON_H = 0.08;
const TAX_R = 0.26;
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
interface Button { group: THREE.Group; top: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; typed: string; press: number }

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
    // the medallions' brass edge, lit by the table's light (their faces carry their own, game/seatIcons.ts)
    const edge = this.keep(new THREE.MeshStandardMaterial({ color: 0x8a6432, roughness: 0.42, metalness: 0.75 }));
    SEAT_ACTIONS.forEach((a, i) => {
      const group = new THREE.Group();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 128;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      const r = BUTTON_R;
      const top = new THREE.Mesh(
        this.keep(new THREE.CircleGeometry(r * 0.985, 48).rotateX(-Math.PI / 2)),
        // unlit: the face is drawn lit from the top left, the same picture as the 2D table's buttons
        this.keep(new THREE.MeshBasicMaterial({ map: tex, toneMapped: false })),
      );
      top.position.y = BUTTON_H + 0.002;
      top.userData = { seatButton: a.id };
      const side = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(r, r * 1.06, BUTTON_H, 48)), edge);
      side.position.y = BUTTON_H / 2;
      side.userData = { seatButton: a.id };
      side.castShadow = true;
      group.add(top, side);
      // a row just past my mat's near edge, from its left end (the turn dial covers the screen's bottom right); Mulligan
      // apart on the right (as on the Oops mat), the Bag of Extras past it
      const lx = a.id === "mulligan" ? -0.7 : a.id === "extras" ? 0.3 : -4.3 + i * 0.66;
      const [wx, wz] = toWorld(mine, lx, MAT_D / 2 + 0.52);
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const b: Button = { group, top, canvas, tex, typed: "", press: 0 };
      drawSeatIcon(canvas, a.id);
      tex.needsUpdate = true;
      this.buttons.set(a.id, b);
    });
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
          canvas.width = canvas.height = 128;
          const tex = this.keep(new THREE.CanvasTexture(canvas));
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 4;
          // a low brass puck lying by the slot, its face (unlit, drawn lit) turned to whoever looks (tick)
          const mesh = new THREE.Mesh(this.keep(new THREE.CircleGeometry(TAX_R * 0.985, 40).rotateX(-Math.PI / 2)),
            this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
          const edge = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(TAX_R, TAX_R * 1.06, TAX_H, 40)), this.taxEdge());
          // against its slot's edge, on the side layout.ts gives it
          const [sx0, sz0] = COMMAND_SLOTS[i]!;
          const [tx0, tz0] = taxSpot(i);
          const k = (CARD_W / 2 + TAX_R + 0.05) / (Math.hypot(tx0 - sx0, tz0 - sz0) || 1);
          const [wx, wz] = toWorld(seat, sx0 + (tx0 - sx0) * k, sz0 + (tz0 - sz0) * k);
          mesh.position.set(wx, TAX_H + 0.002, wz);
          edge.position.set(wx, TAX_H / 2, wz);
          mesh.userData = { tax: c.key };
          edge.userData = { tax: c.key };
          this.group.add(edge, mesh);
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
  private edgeMat: THREE.MeshStandardMaterial | null = null;
  private taxEdge(): THREE.MeshStandardMaterial {
    return (this.edgeMat ??= this.keep(new THREE.MeshStandardMaterial({ color: 0x8a6432, roughness: 0.42, metalness: 0.75 })));
  }

  private slots: THREE.Mesh[] = [];

  taxWorld(key: string): THREE.Vector3 | null {
    return this.taxes.get(key)?.mesh.position.clone() ?? null;
  }

  hover(id: SeatActionId | null): void {
    this.hovered = id;
  }

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
      // hovered: the brass catches more light; pressed: the medallion dips into the table and comes back
      (b.top.material as THREE.MeshBasicMaterial).color.setScalar(id === this.hovered ? 1.3 : 1);
      const since = now - b.press;
      b.group.position.y = since < 160 ? -0.035 * Math.sin((since / 160) * Math.PI) : 0;
    }
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
    for (const b of this.buttons.values()) out.push(...b.group.children);
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
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.unskip();
    this.clear();
  }
}
