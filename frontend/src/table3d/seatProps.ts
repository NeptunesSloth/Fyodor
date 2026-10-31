/**
 * Things at each seat of the 3D table, after the Oops I Baked a Pie table:
 * - Life: the Oops heart. Black, edged thick in the seat's colour, the total big in its middle, ▼ on its left and ▲
 *   on its right. It lies at the mat's inner corner by the middle of the table, a little above the felt, turned so
 *   you read every seat's number upright. Click its left half −1, its right half +1, right-click for 5, or the wheel
 *   (TableScene). Attack arrows aim at it.
 * - Your seat's buttons, where the Oops table has them: in a row just past your mat's near edge, glossy black
 *   discs with the Oops symbols (game/seatIcons.ts), Untap, Draw, Scry, Mill and Reveal, and Mulligan apart to the
 *   right.
 */
import * as THREE from "three";
import { SEAT_ACTIONS, type SeatActionId } from "../game/seatActions";
import { drawSeatIcon } from "../game/seatIcons";
import { CARD_H, CARD_W, COMMAND_SLOTS, heartSpot, MAT_D, taxSpot, toWorld, type Seat } from "./layout";
import { slotTexture } from "./textures";

const HEART_W = 1.45;
const HEART_Y = 0.16;
const BUTTON_R = 0.26;
const BUTTON_H = 0.08;

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

/** A commander's tax counter: a dark chip with a brass rim, the tax big, TAX small, the commander's name on hover. */
function drawTax(canvas: HTMLCanvasElement, tax: number, color: string): void {
  const g = canvas.getContext("2d")!;
  const W = canvas.width;
  g.clearRect(0, 0, W, W);
  g.fillStyle = "#0d0b09";
  g.beginPath();
  g.arc(W / 2, W / 2, W / 2 - 3, 0, Math.PI * 2);
  g.fill();
  g.lineWidth = 7;
  g.strokeStyle = color;
  g.stroke();
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillStyle = tax ? "#f1d58e" : "#bdb7ad";
  g.font = `800 ${tax >= 10 ? 46 : 56}px Inter, Arial, sans-serif`;
  g.fillText(String(tax), W / 2, W / 2 - 6);
  g.fillStyle = "#8e8a84";
  g.font = "700 20px Inter, Arial, sans-serif";
  g.fillText("TAX", W / 2, W / 2 + 32);
}

interface Tax { mesh: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; shown: number }

interface Heart { group: THREE.Group; face: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; shown: string }
interface Button { group: THREE.Group; top: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; typed: string; press: number; flat: boolean }

export class SeatProps {
  readonly group = new THREE.Group();
  private hearts = new Map<string, Heart>();
  private taxes = new Map<string, Tax>();
  private taxKey = "";
  private buttons = new Map<SeatActionId, Button>();
  private hovered: SeatActionId | null = null;
  private disposables: { dispose(): void }[] = [];
  private tmp = new THREE.Vector3();

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
      this.hearts.set(seat.player, { group, face, canvas, tex, color, shown: "" });
    }
    const mine = seats.find((s) => s.player === me);
    if (!mine) return;
    SEAT_ACTIONS.forEach((a, i) => {
      const flat = a.id === "mulligan"; // a pile of cards printed on the table, not a disc
      const group = new THREE.Group();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 128;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      const r = flat ? BUTTON_R * 1.5 : BUTTON_R;
      const top = new THREE.Mesh(
        this.keep(flat ? new THREE.PlaneGeometry(r * 2, r * 2).rotateX(-Math.PI / 2) : new THREE.CircleGeometry(r * 0.97, 40).rotateX(-Math.PI / 2)),
        // unlit, so the disc is black and its symbol its own colour under the table's warm light (as on the Oops table)
        this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: flat, toneMapped: false })),
      );
      top.position.y = flat ? 0.004 : BUTTON_H + 0.002;
      top.userData = { seatButton: a.id };
      group.add(top);
      if (!flat) {
        const side = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(r, r * 1.05, BUTTON_H, 40)), this.keep(new THREE.MeshStandardMaterial({ color: 0x0c0b0a, roughness: 0.35, metalness: 0.3 })));
        side.position.y = BUTTON_H / 2;
        side.userData = { seatButton: a.id };
        group.add(side);
      }
      // a row just past my mat's near edge, a little left of centre, Mulligan apart on the right (as on the Oops mat)
      const lx = flat ? 2.6 : -1.9 + i * 0.66;
      const [wx, wz] = toWorld(mine, lx, MAT_D / 2 + 0.52);
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const b: Button = { group, top, canvas, tex, typed: "", press: 0, flat };
      drawSeatIcon(canvas, a.id);
      tex.needsUpdate = true;
      this.buttons.set(a.id, b);
    });
  }



  /** A seat's life, with any clicks still on their way (shown under the number). */
  setLife(player: string, life: number, pending: number): void {
    const h = this.hearts.get(player);
    if (!h) return;
    const key = `${life}|${pending}`;
    if (h.shown === key) return;
    h.shown = key;
    drawHeart(h.canvas, h.color, life, pending);
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
  setCommanders(seats: Seat[], commanders: Record<string, { key: string; tax: number }[]>, colors: Record<string, string>): void {
    const key = JSON.stringify(seats.map((s) => [s.player, (commanders[s.player] ?? []).map((c) => c.key)]));
    if (key !== this.taxKey) {
      this.taxKey = key;
      for (const t of this.taxes.values()) this.group.remove(t.mesh);
      this.taxes.clear();
      for (const extra of this.slots) this.group.remove(extra);
      this.slots = [];
      for (const seat of seats) {
        const list = commanders[seat.player] ?? [];
        const color = colors[seat.player] ?? "#c9a35a";
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
          const mesh = new THREE.Mesh(this.keep(new THREE.CircleGeometry(0.27, 32).rotateX(-Math.PI / 2)),
            this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
          const [wx, wz] = toWorld(seat, ...taxSpot(i));
          mesh.position.set(wx, 0.01, wz);
          mesh.rotation.y = seat.rot;
          mesh.userData = { tax: c.key };
          this.group.add(mesh);
          this.taxes.set(c.key, { mesh, canvas, tex, color, shown: -1 });
        });
      }
    }
    for (const list of Object.values(commanders)) {
      for (const c of list) {
        const t = this.taxes.get(c.key);
        if (!t || t.shown === c.tax) continue;
        t.shown = c.tax;
        drawTax(t.canvas, c.tax, t.color);
        t.tex.needsUpdate = true;
      }
    }
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
  tick(_t: number, camera: THREE.Camera, _reduced: boolean): void {
    camera.getWorldPosition(this.tmp);
    for (const h of this.hearts.values()) {
      const p = h.group.position;
      h.group.rotation.y = Math.atan2(this.tmp.x - p.x, this.tmp.z - p.z);
    }
    const now = performance.now();
    for (const [id, b] of this.buttons) {
      (b.top.material as THREE.MeshBasicMaterial).color.setScalar(id === this.hovered ? 1.35 : 1);
      const since = now - b.press;
      b.group.position.y = !b.flat && since < 160 ? -0.03 * Math.sin((since / 160) * Math.PI) : 0;
    }
  }

  /** What the pointer can hit. */
  targets(): THREE.Object3D[] {
    const out: THREE.Object3D[] = [];
    for (const h of this.hearts.values()) out.push(h.face);
    for (const t of this.taxes.values()) out.push(t.mesh);
    for (const b of this.buttons.values()) out.push(...b.group.children);
    return out;
  }

  heartWorld(player: string): THREE.Vector3 | null {
    return this.hearts.get(player)?.group.position.clone() ?? null;
  }

  buttonWorld(id: SeatActionId): THREE.Vector3 | null {
    const b = this.buttons.get(id);
    return b ? b.group.position.clone().setY(b.flat ? 0 : BUTTON_H) : null;
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
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.clear();
  }
}
