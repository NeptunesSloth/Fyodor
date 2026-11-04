/**
 * -- live cursors -- every other seated player's pointer over the 3D table (as in Tabletop Simulator): a small arrow
 * in their seat colour with a dark outline (it reads on felt and on wood) and their name beside it, so the colour is
 * never the only cue. It is drawn at a steady size on screen, eased toward each position the server relays (a snap
 * with reduced motion) and fades out after a few seconds without a move or when they leave the table. Display only:
 * the positions travel in a viewer-independent frame (table3d/cursors.ts) and carry nothing but a point on the table.
 */
import * as THREE from "three";
import { cursorToWorld, CursorTrack, type CursorSpot } from "./cursors";
import type { Seat } from "./layout";

/** How tall a cursor's arrow is on screen (CSS px). */
const ARROW_PX = 22;
/** Canvas pixels per CSS px (crisp on high-DPI screens). */
const RES = 2;
/** Just above the cards (a hovered card lifts higher; the cursor draws over everything anyway). */
const HEIGHT = 0.12;

export type CursorMessage = { from: string; gone: true } | ({ from: string; gone?: false } & CursorSpot);

interface Pointer {
  track: CursorTrack;
  spot: CursorSpot | null;
  sprite: THREE.Sprite;
  tex: THREE.CanvasTexture;
  look: string;
  /** the arrow's height as a fraction of the texture's */
  arrowFrac: number;
  aspect: number;
}

/** Draw the arrow and the name plate; returns the texture's aspect, its tip's anchor and the arrow's share of its height. */
function drawPointer(canvas: HTMLCanvasElement, color: string, name: string): { aspect: number; center: [number, number]; arrowFrac: number } {
  const A = ARROW_PX * RES; // arrow height
  const pad = 4 * RES;
  const font = `600 ${12 * RES}px Inter, system-ui, sans-serif`;
  const probe = canvas.getContext("2d")!;
  probe.font = font;
  const label = name.length > 18 ? `${name.slice(0, 17)}…` : name;
  const textW = Math.ceil(probe.measureText(label).width);
  const plateX = pad + A * 0.55;
  const plateY = pad + A * 0.7;
  const plateH = 18 * RES;
  const W = Math.ceil(plateX + textW + 14 * RES + pad);
  const H = Math.ceil(plateY + plateH + pad);
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext("2d")!;
  // the arrow: the classic pointer, tip at the top left
  const tip: [number, number] = [pad, pad];
  const path = new Path2D();
  const p = (x: number, y: number) => [tip[0] + x * A, tip[1] + y * A] as const;
  path.moveTo(...p(0, 0));
  path.lineTo(...p(0, 0.86));
  path.lineTo(...p(0.24, 0.66));
  path.lineTo(...p(0.4, 1));
  path.lineTo(...p(0.53, 0.94));
  path.lineTo(...p(0.37, 0.61));
  path.lineTo(...p(0.66, 0.61));
  path.closePath();
  g.lineJoin = "round";
  g.strokeStyle = "rgba(8,6,5,0.92)";
  g.lineWidth = 3.2 * RES;
  g.stroke(path);
  g.fillStyle = color;
  g.fill(path);
  g.strokeStyle = "rgba(255,255,255,0.35)";
  g.lineWidth = 0.8 * RES;
  g.stroke(path);
  // the name plate: dark, edged in the seat colour
  const plate = new Path2D();
  plate.roundRect(plateX, plateY, W - plateX - pad, plateH, 4 * RES);
  g.fillStyle = "rgba(14,11,9,0.88)";
  g.fill(plate);
  g.strokeStyle = color;
  g.lineWidth = 1.5 * RES;
  g.stroke(plate);
  g.font = font;
  g.textBaseline = "middle";
  g.fillStyle = "#f4e6c4";
  g.fillText(label, plateX + 7 * RES, plateY + plateH / 2 + RES * 0.5);
  return { aspect: W / H, center: [tip[0] / W, 1 - tip[1] / H], arrowFrac: A / H };
}

export class Cursors3D {
  readonly group = new THREE.Group();
  private pointers = new Map<string, Pointer>();
  private seats: Seat[] = [];
  private looks: Record<string, { color: string; name: string }> = {};
  private tmp = new THREE.Vector3();

  /** `onCard`: where a point on a card (its half-widths, -1..1) is on this screen, while that card is on the table here. */
  constructor(private readonly onCard: (card: string, cx: number, cy: number) => [number, number] | null) {
    this.group.name = "cursors";
  }

  /** The seats as this screen lays them out, and each player's colour and name. */
  setTable(seats: Seat[], looks: Record<string, { color: string; name: string }>, now: number): void {
    const moved = seats !== this.seats;
    this.seats = seats;
    this.looks = looks;
    for (const [pid, p] of this.pointers) {
      if (!(pid in looks)) {
        this.drop(pid);
        continue;
      }
      if (moved && p.spot) this.place(p, p.spot, now, true);
      this.restyle(pid, p);
    }
  }

  /** A cursor message from the server (never one of mine). */
  receive(msg: CursorMessage, now: number): void {
    if (msg.gone) {
      this.pointers.get(msg.from)?.track.leave(now);
      return;
    }
    if (!(msg.from in this.looks)) return;
    let p = this.pointers.get(msg.from);
    if (!p) p = this.make(msg.from);
    this.place(p, { player: msg.player, x: msg.x, y: msg.y, card: msg.card, cx: msg.cx, cy: msg.cy }, now, false);
  }

  /** Once a frame, from the table's loop. */
  update(dt: number, now: number, reduced: boolean, camera: THREE.PerspectiveCamera, viewportH: number): void {
    const perPx = (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)) / Math.max(1, viewportH);
    for (const p of this.pointers.values()) {
      const o = p.track.step(dt, now, reduced);
      p.sprite.visible = o > 0.01;
      if (!p.sprite.visible) continue;
      (p.sprite.material as THREE.SpriteMaterial).opacity = o;
      p.sprite.position.set(p.track.x, HEIGHT, p.track.z);
      // a steady size on screen, whatever the camera's distance
      const d = this.tmp.copy(p.sprite.position).applyMatrix4(camera.matrixWorldInverse).z;
      const h = (ARROW_PX / p.arrowFrac) * perPx * Math.max(0.5, -d);
      p.sprite.scale.set(h * p.aspect, h, 1);
    }
  }

  /** Where a player's cursor tip is drawn (world), while it shows. */
  worldOf(pid: string): THREE.Vector3 | null {
    const p = this.pointers.get(pid);
    return p && p.sprite.visible ? p.sprite.position : null;
  }

  dispose(): void {
    for (const pid of [...this.pointers.keys()]) this.drop(pid);
  }

  private place(p: Pointer, spot: CursorSpot, now: number, snap: boolean): void {
    const over = spot.card && spot.cx !== undefined && spot.cy !== undefined ? this.onCard(spot.card, spot.cx, spot.cy) : null;
    const at = over ?? cursorToWorld(this.seats, spot);
    if (!at) return;
    p.spot = spot;
    if (snap) p.track.jump(at[0], at[1]); // a new seat layout isn't a move: an idle cursor stays faded
    else p.track.target(at[0], at[1], now);
  }

  private make(pid: string): Pointer {
    const tex = new THREE.CanvasTexture(document.createElement("canvas"));
    tex.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false, toneMapped: false, fog: false }));
    sprite.renderOrder = 30;
    sprite.visible = false;
    sprite.userData = { cursor: pid };
    sprite.raycast = () => {}; // never in the way of a pick
    this.group.add(sprite);
    const p: Pointer = { track: new CursorTrack(), spot: null, sprite, tex, look: "", arrowFrac: 1, aspect: 1 };
    this.pointers.set(pid, p);
    this.restyle(pid, p);
    return p;
  }

  private restyle(pid: string, p: Pointer): void {
    const look = this.looks[pid] ?? { color: "#bbbbbb", name: "" };
    const key = `${look.color}|${look.name}`;
    if (key === p.look) return;
    p.look = key;
    const canvas = p.tex.image as HTMLCanvasElement;
    const drawn = drawPointer(canvas, look.color, look.name);
    p.tex.dispose(); // (the canvas changed size: a new texture)
    p.tex = new THREE.CanvasTexture(canvas);
    p.tex.colorSpace = THREE.SRGBColorSpace;
    const m = p.sprite.material as THREE.SpriteMaterial;
    m.map = p.tex;
    m.needsUpdate = true;
    p.sprite.center.set(drawn.center[0], drawn.center[1]);
    p.aspect = drawn.aspect;
    p.arrowFrac = drawn.arrowFrac;
  }

  private drop(pid: string): void {
    const p = this.pointers.get(pid);
    if (!p) return;
    this.group.remove(p.sprite);
    p.tex.dispose();
    (p.sprite.material as THREE.Material).dispose();
    this.pointers.delete(pid);
  }
}
