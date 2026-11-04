/**
 * The card back Fyodor draws itself, only while the host hasn't the real one yet (offline before the first download;
 * see cards/cardBack.ts). Our own drawing in the spirit of the Magic back, with no wordmark or logo: a black border, a
 * dark umber frame with a fine printed grain and four corner studs, a tan oval with a violet rim, the five colours'
 * dots and a dim engraved plaque. Drawn once on a canvas, at the size asked: the 3D table uses the canvas as its texture,
 * the 2D table the same picture as a JPEG (a CSS background).
 */
export const BACK_W = 630; // the design's units: 63 × 88 mm, ten to the millimetre
export const BACK_H = 880;

/** The five colours' dots, white at the top and clockwise (as on the printed back). */
export const PIP_COLOURS = ["#efe2a2", "#3fa3b5", "#4e4540", "#c74a2c", "#7da834"] as const;
const PIP_R = 70;
const PIPS = PIP_COLOURS.map((fill, i) => {
  const a = (i * 2 * Math.PI) / 5;
  return { cx: 315 + Math.sin(a) * PIP_R, cy: 492 - Math.cos(a) * PIP_R, fill };
});
const OVAL = { cx: 315, cy: 440, rx: 247, ry: 365 };
const FRAME = { x: 22, y: 22, w: 586, h: 836 };

/** How strong the printed grain is at a point of the design: coarse on the frame, finer on the oval, faint elsewhere. */
export function grainAt(x: number, y: number): number {
  const o = ((x - OVAL.cx) / (OVAL.rx + 6)) ** 2 + ((y - OVAL.cy) / (OVAL.ry + 6)) ** 2;
  if (o < 1) return 9;
  if (x > FRAME.x && x < FRAME.x + FRAME.w && y > FRAME.y && y < FRAME.y + FRAME.h) return 20;
  return 4;
}

function rr(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}
function oval(g: CanvasRenderingContext2D, rx: number, ry: number): void {
  g.beginPath();
  g.ellipse(OVAL.cx, OVAL.cy, rx, ry, 0, 0, Math.PI * 2);
}

/** Soft patches of wear, blurred so they read as worn ink, not shapes (skipped where canvas filters aren't supported). */
function mottle(g: CanvasRenderingContext2D, rnd: () => number, n: number, area: (r: () => number) => [number, number], dark: string, light: string, alpha: number): void {
  g.filter = "blur(10px)";
  if (g.filter !== "blur(10px)") return;
  for (let i = 0; i < n; i++) {
    const [cx, cy] = area(rnd);
    g.globalAlpha = alpha * (0.5 + rnd() * 0.5);
    g.fillStyle = rnd() < 0.6 ? dark : light;
    g.beginPath();
    g.ellipse(cx, cy, 14 + rnd() * 42, 10 + rnd() * 30, rnd() * Math.PI, 0, Math.PI * 2);
    g.fill();
  }
  g.filter = "none";
  g.globalAlpha = 1;
}

/** Draws the back over a w×h canvas (any size; the design scales to it). */
export function drawBack(g: CanvasRenderingContext2D, w: number, h: number): void {
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646; // a fixed seed: every back is the same
  g.save();
  g.scale(w / BACK_W, h / BACK_H);
  g.fillStyle = "#0d0b09";
  rr(g, 0, 0, BACK_W, BACK_H, 34);
  g.fill();
  // the frame: dark umber with olive-gold wear, darker toward its edges
  g.save();
  rr(g, FRAME.x, FRAME.y, FRAME.w, FRAME.h, 8);
  g.clip();
  const base = g.createLinearGradient(FRAME.x, FRAME.y, FRAME.x + FRAME.w, FRAME.y + FRAME.h);
  base.addColorStop(0, "#4d3d1c");
  base.addColorStop(0.5, "#423417");
  base.addColorStop(1, "#302512");
  g.fillStyle = base;
  g.fillRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h);
  mottle(g, rnd, 110, (r) => [FRAME.x + r() * FRAME.w, FRAME.y + r() * FRAME.h], "#16100a", "#8f7a37", 0.6);
  const edge = g.createRadialGradient(315, 440, 0, 315, 440, 600);
  edge.addColorStop(0.6, "rgba(12, 9, 4, 0)");
  edge.addColorStop(1, "rgba(12, 9, 4, 0.55)");
  g.fillStyle = edge;
  g.fillRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h);
  g.restore();
  // the frame's inner rules and its four studs
  g.lineWidth = 3;
  g.strokeStyle = "#140e05";
  rr(g, 38, 38, 554, 804, 5);
  g.stroke();
  g.lineWidth = 2;
  g.globalAlpha = 0.35;
  g.strokeStyle = "#a08848";
  rr(g, 46, 46, 538, 788, 4);
  g.stroke();
  g.globalAlpha = 1;
  for (const [cx, cy] of [[64, 66], [566, 66], [64, 814], [566, 814]] as const) {
    g.beginPath();
    g.arc(cx, cy, 12, 0, Math.PI * 2);
    g.fillStyle = "#c45a2c";
    g.fill();
    g.lineWidth = 3;
    g.strokeStyle = "#1e1006";
    g.stroke();
  }
  // the oval: a dark line, a thin violet rim, a dull tan field lit softly from the top left
  oval(g, OVAL.rx + 8, OVAL.ry + 8);
  g.fillStyle = "#1a1528";
  g.fill();
  oval(g, OVAL.rx + 5, OVAL.ry + 5);
  g.fillStyle = "#5e5ea4";
  g.fill();
  g.save();
  oval(g, OVAL.rx, OVAL.ry);
  g.clip();
  const field = g.createRadialGradient(285, 380, 0, 285, 380, 430);
  field.addColorStop(0, "#946336");
  field.addColorStop(0.6, "#84592f");
  field.addColorStop(1, "#6c4622");
  g.fillStyle = field;
  g.fillRect(OVAL.cx - OVAL.rx, OVAL.cy - OVAL.ry, OVAL.rx * 2, OVAL.ry * 2);
  mottle(g, rnd, 40, (r) => [OVAL.cx + (r() * 2 - 1) * OVAL.rx * 0.9, OVAL.cy + (r() * 2 - 1) * OVAL.ry * 0.9], "#5a3a17", "#a8743f", 0.3);
  g.restore();
  // the five colours
  for (const p of PIPS) {
    g.beginPath();
    g.arc(p.cx, p.cy, 14, 0, Math.PI * 2);
    g.fillStyle = p.fill;
    g.fill();
    g.lineWidth = 3;
    g.strokeStyle = "#24160a";
    g.stroke();
    g.beginPath();
    g.arc(p.cx - 4, p.cy - 4, 4.5, 0, Math.PI * 2);
    g.globalAlpha = 0.4;
    g.fillStyle = "#fff";
    g.fill();
    g.globalAlpha = 1;
  }
  // the plaque under the oval: dim teal, sunk into the card (a dark edge above and left, a light one below and right)
  const plaque = g.createLinearGradient(0, 706, 0, 756);
  plaque.addColorStop(0, "#344a45");
  plaque.addColorStop(1, "#283a36");
  g.fillStyle = plaque;
  rr(g, 140, 706, 350, 50, 3);
  g.fill();
  g.lineWidth = 3;
  g.strokeStyle = "#0c1211";
  g.stroke();
  g.lineWidth = 2;
  g.strokeStyle = "rgba(0, 0, 0, 0.55)";
  g.beginPath();
  g.moveTo(144, 752);
  g.lineTo(144, 710);
  g.lineTo(486, 710);
  g.stroke();
  g.strokeStyle = "rgba(160, 196, 186, 0.28)";
  g.beginPath();
  g.moveTo(486, 710);
  g.lineTo(486, 752);
  g.lineTo(144, 752);
  g.stroke();
  g.restore();
  grain(g, w, h, rnd);
}

/**
 * A fine printed grain: one small tile of noise (per pixel, with a slightly coarser layer), laid over the back as a pattern
 * in overlay, strongest on the frame, finer on the oval, faint on the border. (A tile keeps it cheap: no per-pixel pass
 * over the whole back on the page's thread.)
 */
function grain(g: CanvasRenderingContext2D, w: number, h: number, rnd: () => number): void {
  const T = 128;
  const tile = document.createElement("canvas");
  tile.width = tile.height = T;
  const t = tile.getContext("2d")!;
  const img = t.createImageData(T, T);
  const coarse = Array.from({ length: (T / 2) * (T / 2) }, () => rnd() * 2 - 1);
  for (let y = 0; y < T; y++) {
    for (let x = 0; x < T; x++) {
      const n = (rnd() * 2 - 1) * 0.65 + coarse[(y >> 1) * (T / 2) + (x >> 1)]! * 0.35;
      const k = (y * T + x) * 4;
      img.data[k] = img.data[k + 1] = img.data[k + 2] = 128 + n * 60;
      img.data[k + 3] = 255;
    }
  }
  t.putImageData(img, 0, 0);
  const pattern = g.createPattern(tile, "repeat")!;
  const regions: [number, (c: CanvasRenderingContext2D) => void][] = [
    [grainAt(5, 5), (c) => { c.roundRect(0, 0, BACK_W, BACK_H, 34); }],
    [grainAt(30, 440), (c) => { c.roundRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h, 8); c.ellipse(OVAL.cx, OVAL.cy, OVAL.rx, OVAL.ry, 0, 0, Math.PI * 2); }],
    [grainAt(OVAL.cx, OVAL.cy), (c) => { c.ellipse(OVAL.cx, OVAL.cy, OVAL.rx, OVAL.ry, 0, 0, Math.PI * 2); }],
  ];
  for (const [strength, path] of regions) {
    g.save();
    g.scale(w / BACK_W, h / BACK_H);
    g.beginPath();
    path(g);
    g.clip("evenodd");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "overlay";
    g.globalAlpha = Math.min(1, strength / 36);
    g.fillStyle = pattern;
    g.fillRect(0, 0, w, h);
    g.restore();
  }
}

const rendered = new Map<string, HTMLCanvasElement>();

/** The drawn back on a canvas of this size, drawn once (the 3D table's texture). Needs a page. */
export function drawnBackCanvas(w = 504, h = 704): HTMLCanvasElement {
  const key = `${w}x${h}`;
  let c = rendered.get(key);
  if (!c) {
    c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    drawBack(c.getContext("2d")!, w, h);
    rendered.set(key, c);
  }
  return c;
}

/** The drawn back as an image URL, for the 2D table's CSS (a JPEG: the rounded corners are clipped by each card). */
export function drawnBackUrl(): string {
  return drawnBackCanvas(378, 528).toDataURL("image/jpeg", 0.86);
}
