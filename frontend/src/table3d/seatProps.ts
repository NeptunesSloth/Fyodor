/**
 * Things at each seat of the 3D table, after the Oops I Baked a Pie tables:
 * - A life heart hovering in the air over every seat, in the seat's colour, with no name: whose it is shows by
 *   where it floats. It turns to face you, and the number is the control (TableScene: click +1, right-click −1,
 *   the wheel). Attack arrows aim at it.
 * - Your seat's buttons, physical discs on the table beside your mat: Untap, Draw, Scry, Mill and Reveal
 *   (game/seatActions.ts). They sit along the mat's left side, where your hand doesn't cover them.
 */
import * as THREE from "three";
import { SEAT_ACTIONS, SEAT_ICONS, type SeatActionId } from "../game/seatActions";
import { heartSpot, MAT_D, MAT_W, toWorld, type Seat } from "./layout";

const HEART_Y = 1.2;
const BUTTON_R = 0.27;
const BUTTON_H = 0.09;

function heartShape(): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(0, -0.42);
  s.bezierCurveTo(-0.5, -0.06, -0.56, 0.3, -0.28, 0.4);
  s.bezierCurveTo(-0.12, 0.45, -0.02, 0.36, 0, 0.25);
  s.bezierCurveTo(0.02, 0.36, 0.12, 0.45, 0.28, 0.4);
  s.bezierCurveTo(0.56, 0.3, 0.5, -0.06, 0, -0.42);
  return s;
}

let heartGeo: THREE.ExtrudeGeometry | null = null;
const heartGeometry = () => {
  if (heartGeo) return heartGeo;
  heartGeo = new THREE.ExtrudeGeometry(heartShape(), { depth: 0.1, bevelEnabled: true, bevelThickness: 0.035, bevelSize: 0.035, bevelSegments: 3, curveSegments: 20 });
  heartGeo.center();
  return heartGeo;
};

let blob: THREE.CanvasTexture | null = null;
const blobTexture = () => {
  if (blob) return blob;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0, "rgba(0,0,0,0.45)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return (blob = new THREE.CanvasTexture(c));
};

function drawLife(canvas: HTMLCanvasElement, life: number, pending: number): void {
  const g = canvas.getContext("2d")!;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.textAlign = "center";
  g.textBaseline = "middle";
  const n = String(life + pending);
  g.font = `700 ${n.length > 2 ? 96 : 120}px Cinzel, Georgia, serif`;
  g.lineWidth = 14;
  g.strokeStyle = "rgba(8, 6, 4, 0.92)";
  g.strokeText(n, 128, pending ? 112 : 128);
  g.fillStyle = life + pending <= 0 ? "#ffb3a8" : "#f8f0de";
  g.fillText(n, 128, pending ? 112 : 128);
  if (pending) {
    const p = pending > 0 ? `+${pending}` : `${pending}`;
    g.font = "800 52px Inter, Arial, sans-serif";
    g.lineWidth = 10;
    g.strokeText(p, 128, 196);
    g.fillStyle = pending > 0 ? "#b6f09a" : "#ffa08f";
    g.fillText(p, 128, 196);
  }
}

function drawButton(canvas: HTMLCanvasElement, id: SeatActionId, color: string, typed: string): void {
  const g = canvas.getContext("2d")!;
  const W = canvas.width;
  g.clearRect(0, 0, W, W);
  const grad = g.createRadialGradient(W * 0.38, W * 0.32, 4, W / 2, W / 2, W / 2);
  grad.addColorStop(0, `#${new THREE.Color(color).lerp(new THREE.Color("#ffffff"), 0.45).getHexString()}`);
  grad.addColorStop(0.6, color);
  grad.addColorStop(1, `#${new THREE.Color(color).lerp(new THREE.Color("#000000"), 0.45).getHexString()}`);
  g.fillStyle = grad;
  g.beginPath();
  g.arc(W / 2, W / 2, W / 2 - 2, 0, Math.PI * 2);
  g.fill();
  g.save();
  const s = (W * 0.62) / 24;
  g.translate(W / 2 - 12 * s, W / 2 - 12 * s);
  g.scale(s, s);
  g.strokeStyle = "#120d08";
  g.lineWidth = 2.3;
  g.lineCap = "round";
  g.lineJoin = "round";
  for (const d of SEAT_ICONS[id]) g.stroke(new Path2D(d));
  g.restore();
  if (typed) {
    g.fillStyle = "rgba(18, 13, 8, 0.85)";
    g.beginPath();
    g.arc(W / 2, W / 2, W * 0.3, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#f1d58e";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.font = `800 ${typed.length > 2 ? 44 : 60}px Inter, Arial, sans-serif`;
    g.fillText(typed, W / 2, W / 2 + 3);
  }
}

interface Heart { group: THREE.Group; body: THREE.Mesh; label: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; shadow: THREE.Mesh; seat: Seat; phase: number; shown: string }
interface Button { group: THREE.Group; top: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; typed: string; press: number }

export class SeatProps {
  readonly group = new THREE.Group();
  private hearts = new Map<string, Heart>();
  private buttons = new Map<SeatActionId, Button>();
  private hovered: SeatActionId | null = null;
  private disposables: { dispose(): void }[] = [];

  /** Hearts for every seat; buttons for mine (seat colours from the view). */
  rebuild(seats: Seat[], me: string, colors: Record<string, string>): void {
    this.clear();
    seats.forEach((seat, i) => {
      const color = colors[seat.player] ?? "#c9a35a";
      const body = new THREE.Mesh(heartGeometry(), this.keep(new THREE.MeshStandardMaterial({
        color, emissive: new THREE.Color(color), emissiveIntensity: 0.18, roughness: 0.32, metalness: 0.25,
      })));
      body.userData = { heart: seat.player };
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 256;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      const label = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(0.66, 0.66)), this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false })));
      label.position.set(0, 0.03, 0.12);
      label.userData = { heart: seat.player };
      const group = new THREE.Group();
      group.add(body, label);
      const [wx, wz] = toWorld(seat, ...heartSpot(seat));
      group.position.set(wx, HEART_Y, wz);
      const shadow = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(0.9, 0.9).rotateX(-Math.PI / 2)), this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
      shadow.position.set(wx, 0.006, wz);
      this.group.add(group, shadow);
      this.hearts.set(seat.player, { group, body, label, canvas, tex, shadow, seat, phase: i * 1.7, shown: "" });
    });
    const mine = seats.find((s) => s.player === me);
    if (!mine) return;
    SEAT_ACTIONS.forEach((a, i) => {
      const group = new THREE.Group();
      const side = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(BUTTON_R, BUTTON_R * 1.08, BUTTON_H, 36)), this.keep(new THREE.MeshStandardMaterial({ color: 0x2a2017, roughness: 0.5, metalness: 0.4 })));
      side.position.y = BUTTON_H / 2;
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 128;
      const tex = this.keep(new THREE.CanvasTexture(canvas));
      tex.colorSpace = THREE.SRGBColorSpace;
      // the face lies flat on top, its icon upright as you look across from your seat
      const top = new THREE.Mesh(this.keep(new THREE.CircleGeometry(BUTTON_R * 0.96, 36).rotateX(-Math.PI / 2)), this.keep(new THREE.MeshStandardMaterial({ map: tex, roughness: 0.45, metalness: 0.1, emissive: new THREE.Color(a.color), emissiveIntensity: 0 })));
      top.position.y = BUTTON_H + 0.002;
      side.userData = top.userData = { seatButton: a.id };
      group.add(side, top);
      // a column down the mat's left side, near enough to reach, clear of the hand
      const [wx, wz] = toWorld(mine, -MAT_W / 2 - 0.55, -MAT_D / 2 + 0.3 + i * 0.66);
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const b: Button = { group, top, canvas, tex, color: a.color, typed: "", press: 0 };
      drawButton(canvas, a.id, a.color, "");
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
    drawLife(h.canvas, life, pending);
    h.tex.needsUpdate = true;
  }

  setTyped(id: SeatActionId | null, n: string): void {
    for (const [bid, b] of this.buttons) {
      const typed = bid === id ? n : "";
      if (b.typed === typed) continue;
      b.typed = typed;
      drawButton(b.canvas, bid, b.color, typed);
      b.tex.needsUpdate = true;
    }
  }

  hover(id: SeatActionId | null): void {
    this.hovered = id;
  }

  press(id: SeatActionId): void {
    const b = this.buttons.get(id);
    if (b) b.press = performance.now();
  }

  /** Hearts face the camera and drift a little; buttons light when hovered and dip when pressed. */
  tick(t: number, camera: THREE.Camera, reduced: boolean): void {
    for (const h of this.hearts.values()) {
      h.group.quaternion.copy(camera.quaternion);
      const bob = reduced ? 0 : Math.sin(t * 1.3 + h.phase) * 0.06;
      h.group.position.y = HEART_Y + bob;
      const s = 1 - bob * 0.6;
      h.shadow.scale.set(s, 1, s);
    }
    const now = performance.now();
    for (const [id, b] of this.buttons) {
      (b.top.material as THREE.MeshStandardMaterial).emissiveIntensity = id === this.hovered ? 0.35 : 0;
      const since = now - b.press;
      b.group.position.y = since < 160 ? -0.035 * Math.sin((since / 160) * Math.PI) : 0;
    }
  }

  /** What the pointer can hit. */
  targets(): THREE.Object3D[] {
    const out: THREE.Object3D[] = [];
    for (const h of this.hearts.values()) out.push(h.body, h.label);
    for (const b of this.buttons.values()) out.push(...b.group.children);
    return out;
  }

  heartWorld(player: string): THREE.Vector3 | null {
    return this.hearts.get(player)?.group.position.clone() ?? null;
  }

  /** Where attack arrows aim at a player: the table under their heart. */
  heartFloor(player: string): THREE.Vector3 | null {
    const h = this.hearts.get(player);
    return h ? new THREE.Vector3(h.group.position.x, 0.3, h.group.position.z) : null;
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
    this.hearts.clear();
    this.buttons.clear();
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.clear();
  }
}
