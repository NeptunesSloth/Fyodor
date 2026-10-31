/**
 * The seat buttons' faces, after the Oops I Baked a Pie table's buttons: glossy black discs, each with one bold
 * coloured symbol — a yellow U-turn arrow (Untap), a green open hand (Draw), a blue eye (Scry), a red skull
 * (Mill), a beige magnifying glass (Reveal) — and Mulligan's grey cards around a cyan arrow loop. Drawn here
 * (plain canvas shapes, nothing copied) so the 3D buttons' texture and the 2D buttons' images are the same picture.
 */
import type { SeatActionId } from "./seatActions";

export type SeatIconId = SeatActionId | "mulligan" | "importer";

const OUTLINE = "#0b0907";

/** The black disc (or, for Mulligan, nothing: its cards sit on the table). */
function disc(g: CanvasRenderingContext2D): void {
  const grad = g.createRadialGradient(40, 34, 4, 50, 50, 50);
  grad.addColorStop(0, "#3a3835");
  grad.addColorStop(0.55, "#141312");
  grad.addColorStop(1, "#050505");
  g.fillStyle = grad;
  g.beginPath();
  g.arc(50, 50, 48, 0, Math.PI * 2);
  g.fill();
  g.lineWidth = 2;
  g.strokeStyle = "rgba(255, 255, 255, 0.12)";
  g.beginPath();
  g.arc(50, 50, 46.5, Math.PI * 1.05, Math.PI * 1.75);
  g.stroke();
}

function outlined(g: CanvasRenderingContext2D, path: Path2D, fill: string, width = 3.2): void {
  g.lineJoin = "round";
  g.lineCap = "round";
  g.lineWidth = width;
  g.strokeStyle = OUTLINE;
  g.stroke(path);
  g.fillStyle = fill;
  g.fill(path);
}

/** Untap: a thick yellow U-turn arrow, its head at the top of the left arm. */
function untap(g: CanvasRenderingContext2D): void {
  const shaft = new Path2D();
  shaft.moveTo(68, 30);
  shaft.lineTo(68, 52);
  shaft.bezierCurveTo(68, 70, 56, 76, 47, 76);
  shaft.bezierCurveTo(37, 76, 30, 69, 31, 57);
  g.lineCap = "round";
  g.lineJoin = "round";
  g.lineWidth = 17;
  g.strokeStyle = OUTLINE;
  g.stroke(shaft);
  g.lineWidth = 11;
  g.strokeStyle = "#f3d52c";
  g.stroke(shaft);
  const head = new Path2D("M31 34 L46 54 L17 55 Z");
  outlined(g, head, "#f3d52c");
}

/** Draw: a green open hand, fingers spread up and to the right. */
function hand(g: CanvasRenderingContext2D): void {
  g.save();
  g.translate(50, 54);
  g.rotate(0.32);
  const p = new Path2D();
  // palm
  p.moveTo(-17, 22);
  p.bezierCurveTo(-24, 10, -22, -2, -16, -7);
  p.lineTo(16, -7);
  p.bezierCurveTo(20, 2, 18, 16, 10, 22);
  p.closePath();
  // fingers
  const finger = (x: number, len: number, w = 7.5) => {
    p.moveTo(x - w / 2, -4);
    p.lineTo(x - w / 2, -4 - len);
    p.arc(x, -4 - len, w / 2, Math.PI, 0);
    p.lineTo(x + w / 2, -4);
    p.closePath();
  };
  finger(-12, 20);
  finger(-3.5, 27);
  finger(5, 25);
  finger(13.5, 18);
  // thumb, out to the left
  p.moveTo(-15, 8);
  p.bezierCurveTo(-24, 2, -32, -6, -35, -11);
  p.bezierCurveTo(-37, -15, -32, -18, -29, -15);
  p.bezierCurveTo(-24, -10, -18, -6, -12, -2);
  p.closePath();
  g.lineJoin = "round";
  g.lineWidth = 3.4;
  g.strokeStyle = OUTLINE;
  g.stroke(p);
  g.fillStyle = "#3fb43a";
  g.fill(p, "nonzero");
  g.restore();
}

/** Scry: a blue eye, its iris filled, a pale highlight. */
function eye(g: CanvasRenderingContext2D): void {
  const lid = new Path2D();
  lid.moveTo(14, 50);
  lid.bezierCurveTo(26, 30, 74, 30, 86, 50);
  lid.bezierCurveTo(74, 70, 26, 70, 14, 50);
  lid.closePath();
  g.lineWidth = 9;
  g.lineJoin = "round";
  g.strokeStyle = OUTLINE;
  g.stroke(lid);
  g.lineWidth = 5;
  g.strokeStyle = "#2f80e6";
  g.stroke(lid);
  g.fillStyle = OUTLINE;
  g.beginPath();
  g.arc(50, 49, 15, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#2f80e6";
  g.beginPath();
  g.arc(50, 49, 12.5, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#9fd0ff";
  g.beginPath();
  g.ellipse(45, 43.5, 5, 3.4, -0.5, 0, Math.PI * 2);
  g.fill();
}

/** Mill: a red skull, turned a little to the right, its sockets and nose black. */
function skull(g: CanvasRenderingContext2D): void {
  const p = new Path2D();
  p.moveTo(26, 50);
  p.bezierCurveTo(22, 30, 36, 18, 52, 18);
  p.bezierCurveTo(70, 18, 82, 31, 79, 49);
  p.bezierCurveTo(78, 56, 74, 59, 71, 61);
  p.lineTo(71, 74);
  p.bezierCurveTo(71, 79, 67, 81, 62, 81);
  p.lineTo(44, 81);
  p.bezierCurveTo(39, 81, 36, 78, 36, 73);
  p.lineTo(36, 64);
  p.bezierCurveTo(30, 61, 27, 57, 26, 50);
  p.closePath();
  outlined(g, p, "#e8262c", 3.4);
  g.fillStyle = OUTLINE;
  g.beginPath();
  g.ellipse(45, 47, 8, 9, 0.2, 0, Math.PI * 2);
  g.ellipse(66, 47, 6.5, 8.5, -0.15, 0, Math.PI * 2);
  g.fill();
  g.beginPath();
  g.moveTo(56, 56);
  g.lineTo(60, 64);
  g.lineTo(52, 64);
  g.closePath();
  g.fill();
  g.lineWidth = 2.6;
  g.strokeStyle = OUTLINE;
  for (const x of [47, 54, 61]) {
    g.beginPath();
    g.moveTo(x, 71);
    g.lineTo(x, 81);
    g.stroke();
  }
}

/** Reveal: a magnifying glass, its beige rim and handle, the lens dark with a glint. */
function glass(g: CanvasRenderingContext2D): void {
  g.lineCap = "round";
  g.lineWidth = 15;
  g.strokeStyle = OUTLINE;
  g.beginPath();
  g.moveTo(41, 61);
  g.lineTo(24, 80);
  g.stroke();
  g.lineWidth = 9;
  g.strokeStyle = "#d9c4ad";
  g.beginPath();
  g.moveTo(41, 61);
  g.lineTo(24, 80);
  g.stroke();
  g.fillStyle = OUTLINE;
  g.beginPath();
  g.arc(57, 43, 24, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#d9c4ad";
  g.beginPath();
  g.arc(57, 43, 21, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "#26231f";
  g.beginPath();
  g.arc(57, 43, 15, 0, Math.PI * 2);
  g.fill();
  g.strokeStyle = "rgba(255, 255, 255, 0.55)";
  g.lineWidth = 3;
  g.beginPath();
  g.arc(57, 43, 10, Math.PI * 1.1, Math.PI * 1.55);
  g.stroke();
}

/** Mulligan: a fanned hand of grey cards, a cyan arrow loop, a squared pile. */
function mulligan(g: CanvasRenderingContext2D): void {
  const card = (x: number, y: number, r: number) => {
    g.save();
    g.translate(x, y);
    g.rotate(r);
    g.fillStyle = "#b9b2a6";
    g.strokeStyle = OUTLINE;
    g.lineWidth = 2;
    g.beginPath();
    g.roundRect(-7, -10, 14, 20, 2);
    g.fill();
    g.stroke();
    g.restore();
  };
  card(14, 52, -0.5);
  card(20, 50, -0.2);
  card(26, 50, 0.1);
  for (let i = 0; i < 4; i++) {
    g.fillStyle = i % 2 ? "#a29b8f" : "#bdb6aa";
    g.strokeStyle = OUTLINE;
    g.lineWidth = 1.6;
    g.beginPath();
    g.roundRect(70, 58 - i * 4, 22, 12, 2);
    g.fill();
    g.stroke();
  }
  g.lineWidth = 5;
  g.strokeStyle = "#35d0d0";
  g.lineCap = "round";
  g.beginPath();
  g.arc(50, 50, 12, Math.PI * 1.15, Math.PI * 2.05);
  g.stroke();
  g.beginPath();
  g.arc(50, 50, 12, Math.PI * 0.15, Math.PI * 1.05);
  g.stroke();
  g.fillStyle = "#35d0d0";
  for (const [x, y, r] of [[61, 47, 1.2], [39, 53, -1.95]] as const) {
    g.save();
    g.translate(x, y);
    g.rotate(r);
    g.beginPath();
    g.moveTo(-5, -1);
    g.lineTo(5, -1);
    g.lineTo(0, 6);
    g.closePath();
    g.fill();
    g.restore();
  }
}

/** The card importer: a dark board, a deck with a card coming in, IMPORT under it (the Oops importer boards). */
function importer(g: CanvasRenderingContext2D): void {
  g.fillStyle = "#15171d";
  g.strokeStyle = "#8a6a3f";
  g.lineWidth = 3;
  g.beginPath();
  g.roundRect(6, 10, 88, 80, 8);
  g.fill();
  g.stroke();
  for (let i = 0; i < 3; i++) {
    g.fillStyle = i === 2 ? "#3c4a6b" : "#2b3247";
    g.strokeStyle = "#0b0907";
    g.lineWidth = 1.6;
    g.beginPath();
    g.roundRect(36 - i * 3, 34 - i * 3, 24, 32, 3);
    g.fill();
    g.stroke();
  }
  g.strokeStyle = "#35d0d0";
  g.lineWidth = 5;
  g.lineCap = "round";
  g.beginPath();
  g.moveTo(68, 20);
  g.lineTo(68, 44);
  g.stroke();
  g.fillStyle = "#35d0d0";
  g.beginPath();
  g.moveTo(59, 40);
  g.lineTo(77, 40);
  g.lineTo(68, 52);
  g.closePath();
  g.fill();
  g.fillStyle = "#d9c4ad";
  g.font = "800 14px Inter, Arial, sans-serif";
  g.textAlign = "center";
  g.fillText("IMPORT", 50, 83);
}

const GLYPH: Record<SeatIconId, (g: CanvasRenderingContext2D) => void> = { untap, draw: hand, scry: eye, mill: skull, reveal: glass, mulligan, importer };

/** Draw a seat button's face into a square canvas (any size). `count` is a number being typed over it. */
export function drawSeatIcon(canvas: HTMLCanvasElement, id: SeatIconId, count = ""): void {
  const g = canvas.getContext("2d")!;
  g.save();
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.scale(canvas.width / 100, canvas.height / 100);
  if (id !== "mulligan" && id !== "importer") disc(g);
  GLYPH[id](g);
  if (count) {
    g.fillStyle = "rgba(10, 8, 6, 0.86)";
    g.beginPath();
    g.arc(50, 50, 27, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#f1d58e";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.font = `800 ${count.length > 2 ? 26 : 34}px Inter, Arial, sans-serif`;
    g.fillText(count, 50, 52);
  }
  g.restore();
}

const urls = new Map<SeatIconId, string>();
/** The face as an image URL (for the 2D buttons), drawn once. */
export function seatIconUrl(id: SeatIconId): string {
  const known = urls.get(id);
  if (known) return known;
  const c = document.createElement("canvas");
  c.width = c.height = 96;
  drawSeatIcon(c, id);
  const url = c.toDataURL("image/png");
  urls.set(id, url);
  return url;
}
