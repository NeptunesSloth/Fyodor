/**
 * Things at each seat of the 3D table, after the Oops I Baked a Pie table:
 * - Life: the Oops heart. Black, edged thick in the seat's colour, the total big in its middle, ▼ on its left and ▲
 *   on its right. It lies at the mat's inner corner by the middle of the table, a little above the felt, turned so
 *   you read every seat's number upright. Click its left half −1, its right half +1, right-click for 5, or the wheel
 *   (TableScene). Attack arrows aim at it.
 * - Your seat's buttons, as the Oops table has them: in a row just past your mat's near edge (from its left end), glossy black
 *   discs with the Oops symbols (game/seatIcons.ts), Untap, Draw, Scry, Mill and Reveal, and Mulligan apart to the
 *   right, and the Bag of Extras (a leather pouch) past it.
 */
import * as THREE from "three";
import { SEAT_ACTIONS, type SeatActionId } from "../game/seatActions";
import { drawSeatIcon } from "../game/seatIcons";
import { motionMs, onMotionSkip } from "../game/motion/timing";
import { CARD_H, CARD_W, commandSlot, COMMAND_SLOTS, HEART, heartSpot, heartTilt, MAT_D, taxSpot, toWorld, type Seat } from "./layout";
import { slotTexture } from "./textures";

const HEART_W = HEART.w;
/** 1v1: Mulligan's spot along my near edge, right of my heart and plate (the bag just past it). */
const DUEL_MULLIGAN_X = 3.45;
const HEART_Y = HEART.y;
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

/** A bar of the −/+ glyphs: a rounded rectangle centred on (x, y). */
function bar(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): void {
  g.beginPath();
  g.roundRect(x - w / 2, y - h / 2, w, h, h / 2);
}

/**
 * The Oops heart, drawn for the table: black, edged thick in the seat's colour, the life total big in its lower
 * middle, and its two halves the controls: a large white − on the left lobe over a dark red half, a large white + on
 * the right over a dark green one, each outlined dark so it reads on any table. `hot`: the half under the pointer, lit.
 */
function drawHeart(canvas: HTMLCanvasElement, color: string, life: number, pending: number, hot: -1 | 0 | 1 = 0): void {
  const g = canvas.getContext("2d")!;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.save();
  g.scale(canvas.width / 256, canvas.height / 232);
  const heart = heartPath();
  g.fillStyle = "#050505";
  g.fill(heart);
  // the halves: − loses life (left, red), + gains it (right, green), lit a little from above; the one under the
  // pointer brighter
  g.save();
  g.clip(heart);
  const half = (x: number, top: string, bottom: string) => {
    const grad = g.createLinearGradient(0, 10, 0, 224);
    grad.addColorStop(0, top);
    grad.addColorStop(1, bottom);
    g.fillStyle = grad;
    g.fillRect(x, 0, 128, 232);
  };
  if (hot === -1) half(0, "#b5422f", "#6e2219");
  else half(0, "#86301f", "#4a1812");
  if (hot === 1) half(128, "#3d9a57", "#1f5a31");
  else half(128, "#2c7342", "#173f24");
  g.fillStyle = "rgba(0, 0, 0, 0.5)";
  g.fillRect(126.5, 0, 3, 232);
  g.restore();
  g.lineJoin = "round";
  g.lineWidth = 15;
  g.strokeStyle = color;
  g.stroke(heart);
  // − and +: engraved brass, lit from the top left, in the lobes above the number
  const signs = (dx: number, dy: number, w: number, h: number) => {
    const at: [number, number, number, number][] = [[64, 64, w, h], [192, 64, w, h], [192, 64, h, w]];
    for (const [x, y, bw, bh] of at) {
      bar(g, x + dx, y + dy, bw, bh);
      g.fill();
    }
  };
  g.fillStyle = "rgba(0, 0, 0, 0.75)"; // the cut's shadow, down and right
  signs(3, 3, 50, 15);
  const brass = g.createLinearGradient(40, 40, 216, 88);
  brass.addColorStop(0, "#fbe9b0");
  brass.addColorStop(0.45, "#d8ad55");
  brass.addColorStop(1, "#8f6526");
  g.fillStyle = "rgba(40, 24, 6, 0.95)"; // its dark edge
  signs(0, 0, 52, 17);
  g.fillStyle = brass;
  signs(0, 0, 46, 11);
  // the light catching each bar's top and left edges (inside the bar), the shade its bottom and right
  for (const [x, y, bw, bh] of [[64, 64, 46, 11], [192, 64, 46, 11], [192, 64, 11, 46]] as const) {
    g.save();
    bar(g, x, y, bw, bh);
    g.clip();
    g.lineWidth = 3;
    g.strokeStyle = "rgba(255, 249, 226, 0.9)";
    bar(g, x + 2, y + 2, bw, bh);
    g.stroke();
    g.strokeStyle = "rgba(70, 42, 10, 0.75)";
    bar(g, x - 2, y - 2, bw, bh);
    g.stroke();
    g.restore();
  }
  g.textAlign = "center";
  g.textBaseline = "middle";
  const n = String(life + pending);
  g.fillStyle = life + pending <= 0 ? "#ff8a7a" : "#f1ece2";
  g.font = `700 ${n.length > 2 ? 54 : 68}px "Inter Variable", Inter, Arial, sans-serif`;
  g.lineJoin = "round";
  g.lineWidth = 8;
  g.strokeStyle = "rgba(0, 0, 0, 0.85)";
  g.strokeText(n, 128, 140);
  g.fillText(n, 128, 140);
  if (pending) {
    g.font = '800 30px "Inter Variable", Inter, Arial, sans-serif';
    g.fillStyle = pending > 0 ? "#9ee68a" : "#ff9a8a";
    g.strokeText(pending > 0 ? `+${pending}` : `${pending}`, 128, 188);
    g.fillText(pending > 0 ? `+${pending}` : `${pending}`, 128, 188);
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

interface Heart {
  group: THREE.Group; face: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; color: string; shown: string;
  /** The half under the pointer (−1 the − half, 1 the + half), lit. */
  hot: -1 | 0 | 1;
  /** -- table motion -- the life total on the heart rolls to a new value (docs/GAME_UI_MOTION_RESEARCH.md §4: 300–600 ms scaled to the
   * change): what it shows now, where it's going, and the clicks still on their way. */
  roll: { from: number; to: number; start: number; dur: number; at: number | null; pending: number };
}
interface Button { group: THREE.Group; top: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; typed: string; press: number; flat: boolean }

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
      this.hearts.set(seat.player, { group, face, canvas, tex, color, shown: "", hot: 0, roll: { from: 0, to: 0, start: 0, dur: 0, at: null, pending: 0 } });
    }
    const mine = seats.find((s) => s.player === me);
    if (!mine) return;
    SEAT_ACTIONS.forEach((a, i) => {
      if (a.id === "extras") return this.buildPouch(mine);
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
      // a row just past my mat's near edge, from its left end (the turn dial covers the screen's bottom right), Mulligan
      // apart on the right (as on the Oops mat); 1v1: my heart and plate take the middle, so the row starts under my
      // command zone and Mulligan and the bag go right of my plate
      const lx = mine.duel ? (flat ? DUEL_MULLIGAN_X : -5.95 + i * 0.66) : flat ? -0.7 : -4.3 + i * 0.66;
      const [wx, wz] = toWorld(mine, lx, MAT_D / 2 + (mine.duel ? 0.62 : 0.52));
      group.position.set(wx, 0, wz);
      group.rotation.y = mine.rot;
      this.group.add(group);
      const b: Button = { group, top, canvas, tex, typed: "", press: 0, flat };
      drawSeatIcon(canvas, a.id);
      tex.needsUpdate = true;
      this.buttons.set(a.id, b);
    });
  }



  /**
   * -- table toys -- the Bag of Extras (game/ExtrasBag.tsx): a small leather drawstring pouch past Mulligan, off the mat like
   * the seat buttons, a gold coin in its mouth. A seat button like the others (click opens it); it lifts a little when hovered.
   */
  private buildPouch(mine: Seat): void {
    const group = new THREE.Group();
    const profile: [number, number][] = [[0, 0], [0.11, 0.008], [0.19, 0.045], [0.235, 0.11], [0.23, 0.19], [0.18, 0.26], [0.11, 0.3],
      [0.085, 0.325], [0.1, 0.345], [0.15, 0.39], [0.16, 0.405], [0.13, 0.41], [0.08, 0.38], [0, 0.37]];
    const leather = this.keep(new THREE.MeshStandardMaterial({ color: 0x6e4626, roughness: 0.82, metalness: 0, emissive: 0x2a1608, emissiveIntensity: 0 }));
    const sack = new THREE.Mesh(this.keep(new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), 20)), leather);
    sack.scale.set(1, 1, 0.86); // a sack, not a vase
    const cord = new THREE.Mesh(this.keep(new THREE.TorusGeometry(0.092, 0.016, 6, 20).rotateX(Math.PI / 2)),
      this.keep(new THREE.MeshStandardMaterial({ color: 0xd9b267, roughness: 0.55, metalness: 0.2 })));
    cord.position.y = 0.33;
    const coin = new THREE.Mesh(this.keep(new THREE.CylinderGeometry(0.075, 0.075, 0.02, 18)),
      this.keep(new THREE.MeshStandardMaterial({ color: 0xe8c063, roughness: 0.3, metalness: 0.9 })));
    coin.position.set(0.03, 0.41, -0.02);
    coin.rotation.set(0.9, 0, 0.3);
    const shadow = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(0.62, 0.62).rotateX(-Math.PI / 2)), this.keep(new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false })));
    shadow.position.y = 0.004;
    for (const m of [sack, cord, coin]) {
      m.userData = { seatButton: "extras" };
      m.castShadow = true;
    }
    group.add(shadow, sack, cord, coin);
    const [wx, wz] = mine.duel ? toWorld(mine, DUEL_MULLIGAN_X + 1.0, MAT_D / 2 + 0.62) : toWorld(mine, 0.3, MAT_D / 2 + 0.52);
    group.position.set(wx, 0, wz);
    group.rotation.y = mine.rot + 0.5;
    this.group.add(group);
    this.pouch = { group, leather, press: 0 };
  }

  private pouch: { group: THREE.Group; leather: THREE.MeshStandardMaterial; press: number } | null = null;

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
    const key = `${shown}|${h.roll.pending}|${h.hot}`;
    if (h.shown === key) return;
    h.shown = key;
    drawHeart(h.canvas, h.color, shown, h.roll.pending, h.hot);
    h.tex.needsUpdate = true;
  }

  /** The heart half under the pointer (null: none), lit so you see which way a click goes. */
  hoverHeart(player: string | null, side: -1 | 1 | undefined): void {
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
   * Each commander's tax counter beside its slot in the command zone (and a slot for a partner when there is one).
   * `commanders`: per seat, its commanders' keys in slot order, with their tax.
   */
  setCommanders(seats: Seat[], commanders: Record<string, { key: string; tax: number }[]>, colors: Record<string, string>, viewRot = 0): void {
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
            slot.rotation.z = viewRot; // its label upright from my seat
            const [sx, sz] = toWorld(seat, ...commandSlot(seat, i));
            slot.position.set(sx, 0.0034, sz); // as the other pile slots (TableScene SLOT_Y)
            slot.renderOrder = -1;
            this.group.add(slot);
            this.slots.push(slot);
          }
          const canvas = document.createElement("canvas");
          canvas.width = canvas.height = 128;
          const tex = this.keep(new THREE.CanvasTexture(canvas));
          tex.colorSpace = THREE.SRGBColorSpace;
          const mesh = new THREE.Mesh(this.keep(new THREE.CircleGeometry(0.27, 32).rotateX(-Math.PI / 2)),
            this.keep(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
          const [wx, wz] = toWorld(seat, ...taxSpot(i, seat));
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
    if (id === "extras" && this.pouch) this.pouch.press = performance.now();
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
    for (const h of this.hearts.values()) { // a life total rolling to its new value (only while one changes)
      const r = h.roll;
      if (r.at === null || r.at === r.to) continue;
      r.at = lifeRollAt(r, now);
      this.drawLife(h, r.at);
    }
    for (const [id, b] of this.buttons) {
      (b.top.material as THREE.MeshBasicMaterial).color.setScalar(id === this.hovered ? 1.35 : 1);
      const since = now - b.press;
      b.group.position.y = !b.flat && since < 160 ? -0.03 * Math.sin((since / 160) * Math.PI) : 0;
    }
    if (this.pouch) { // the pouch: warmer when hovered, a little hop as it is opened
      const hovered = this.hovered === "extras";
      this.pouch.leather.emissiveIntensity = hovered ? 0.9 : 0;
      const since = now - this.pouch.press;
      this.pouch.group.position.y = since < 220 ? 0.06 * Math.sin((since / 220) * Math.PI) : 0;
    }
  }

  /** What the pointer can hit. */
  targets(): THREE.Object3D[] {
    const out: THREE.Object3D[] = [];
    for (const h of this.hearts.values()) out.push(h.face);
    for (const t of this.taxes.values()) out.push(t.mesh);
    for (const b of this.buttons.values()) out.push(...b.group.children);
    if (this.pouch) out.push(...this.pouch.group.children.filter((c) => c.userData.seatButton));
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
    return p.clone().addScaledVector(right, side * HEART_W * 0.47).setY(HEART_Y + h.face.position.y);
  }

  buttonWorld(id: SeatActionId): THREE.Vector3 | null {
    if (id === "extras") return this.pouch ? this.pouch.group.position.clone().setY(0.25) : null;
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
    this.pouch = null;
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
  }

  dispose(): void {
    this.unskip();
    this.clear();
  }
}
