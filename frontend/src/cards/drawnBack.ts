/**
 * The card back Fyodor draws itself, only while the host hasn't the real one yet (offline before the first download;
 * see cards/cardBack.ts). Our own drawing in the spirit of the Magic back, with no wordmark: a dark border, a mottled
 * brown frame with four corner studs, a tan oval with a violet rim, the five colours' dots and a blank plaque. One
 * description, two renderers: an SVG for the 2D table (a CSS background) and a canvas for the 3D table's texture.
 */
type Stops = [number, string][];
type Paint = string | { radial: [cx: number, cy: number, r: number]; stops: Stops } | { linear: [x1: number, y1: number, x2: number, y2: number]; stops: Stops };
interface Shape { d: string; fill?: Paint; stroke?: string; width?: number; alpha?: number }

export const BACK_W = 630;
export const BACK_H = 880;

const rr = (x: number, y: number, w: number, h: number, r: number) =>
  `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`;
const ellipse = (cx: number, cy: number, rx: number, ry: number) => `M${cx - rx} ${cy}A${rx} ${ry} 0 1 0 ${cx + rx} ${cy}A${rx} ${ry} 0 1 0 ${cx - rx} ${cy}Z`;
const dot = (cx: number, cy: number, r: number) => ellipse(cx, cy, r, r);

// mottling from a fixed seed, so every back is the same: dark and gold flecks spread over the frame (one per cell of a
// jittered grid, so none clump), and faint ones over the oval
let seed = 7;
const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
const fleck = (cx: number, cy: number, rx: number, ry: number, fill: string, alpha: number): Shape =>
  ({ d: ellipse(Math.round(cx), Math.round(cy), Math.round(rx), Math.round(ry)), fill, alpha: Math.round(alpha * 100) / 100 });
const FRAME_FLECKS: Shape[] = [];
for (let row = 0; row < 10; row++) {
  for (let col = 0; col < 7; col++) {
    const dark = rnd() < 0.62;
    const rx = 10 + rnd() * (dark ? 34 : 24);
    const ry = 7 + rnd() * (dark ? 24 : 14);
    const cx = Math.min(Math.max(22 + (col + 0.15 + rnd() * 0.7) * 84, 24 + rx), 606 - rx); // inside the frame, off the border
    const cy = Math.min(Math.max(22 + (row + 0.15 + rnd() * 0.7) * 84, 24 + ry), 856 - ry);
    FRAME_FLECKS.push(fleck(cx, cy, rx, ry, dark ? "#1d170a" : "#bba34c", dark ? 0.16 + rnd() * 0.18 : 0.1 + rnd() * 0.12));
  }
}
const OVAL_FLECKS: Shape[] = Array.from({ length: 26 }, () => {
  const a = rnd() * Math.PI * 2;
  const r = Math.sqrt(rnd()) * 0.85;
  const dark = rnd() < 0.55;
  return fleck(315 + Math.cos(a) * r * 247, 440 + Math.sin(a) * r * 365, 12 + rnd() * 30, 9 + rnd() * 20, dark ? "#4a2d10" : "#b5813f", 0.05 + rnd() * 0.06);
});

const PIP_R = 70;
const PIPS = ["#efe2a2", "#3fa3b5", "#4e4540", "#c74a2c", "#7da834"].map((fill, i) => {
  const a = (i * 2 * Math.PI) / 5;
  return { cx: 315 + Math.sin(a) * PIP_R, cy: 492 - Math.cos(a) * PIP_R, fill };
});

const SHAPES: Shape[] = [
  { d: rr(0, 0, BACK_W, BACK_H, 34), fill: "#0d0b09" },
  // the frame: olive-brown, darker toward the bottom right, flecked
  { d: rr(22, 22, 586, 836, 8), fill: { linear: [22, 22, 608, 858], stops: [[0, "#76652b"], [0.5, "#5e4f21"], [1, "#443816"]] } },
  ...FRAME_FLECKS,
  // darker toward the edges, as worn card stock
  { d: rr(22, 22, 586, 836, 8), fill: { radial: [315, 440, 600], stops: [[0, "rgba(16,12,4,0)"], [0.62, "rgba(16,12,4,0)"], [1, "rgba(16,12,4,0.6)"]] } },
  { d: rr(38, 38, 554, 804, 5), stroke: "#231a0a", width: 3 },
  { d: rr(46, 46, 538, 788, 4), stroke: "#a89050", width: 2, alpha: 0.5 },
  ...[[64, 66], [566, 66], [64, 814], [566, 814]].map(([cx, cy]) => ({ d: dot(cx!, cy!, 10), fill: "#c9582d", stroke: "#2a1608", width: 3 })),
  // the oval: a thin violet rim on a dark line, a dull tan field lit softly from the top left
  { d: ellipse(315, 440, 255, 373), fill: "#241d3a" },
  { d: ellipse(315, 440, 252, 370), fill: "#7375bb" },
  { d: ellipse(315, 440, 247, 365), fill: { radial: [280, 380, 430], stops: [[0, "#9e6632"], [0.6, "#8c5927"], [1, "#774a1f"]] } },
  ...OVAL_FLECKS,
  // the five colours, white at the top and clockwise
  ...PIPS.map((p) => ({ d: dot(p.cx, p.cy, 14), fill: p.fill, stroke: "#2a1a0c", width: 3 })),
  ...PIPS.map((p) => ({ d: dot(p.cx - 4, p.cy - 4, 4.5), fill: "#ffffff", alpha: 0.45 })),
  // the plaque under the oval
  { d: rr(140, 706, 350, 50, 3), fill: "#a9c7bf", stroke: "#1f2a29", width: 4 },
  { d: rr(149, 715, 332, 32, 2), stroke: "#56716b", width: 2 },
];

function svgPaint(paint: Paint, id: string, defs: string[]): string {
  if (typeof paint === "string") return paint;
  const stops = paint.stops.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join("");
  if ("radial" in paint) {
    const [cx, cy, r] = paint.radial;
    defs.push(`<radialGradient id="${id}" gradientUnits="userSpaceOnUse" cx="${cx}" cy="${cy}" r="${r}">${stops}</radialGradient>`);
  } else {
    const [x1, y1, x2, y2] = paint.linear;
    defs.push(`<linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}">${stops}</linearGradient>`);
  }
  return `url(#${id})`;
}

/** The drawn back as an SVG document. */
export function drawnBackSvg(): string {
  const defs: string[] = [];
  const body = SHAPES.map((s, i) => {
    const fill = s.fill ? svgPaint(s.fill, `g${i}`, defs) : "none";
    const stroke = s.stroke ? ` stroke="${s.stroke}" stroke-width="${s.width ?? 1}"` : "";
    const alpha = s.alpha != null ? ` opacity="${s.alpha}"` : "";
    return `<path d="${s.d}" fill="${fill}"${stroke}${alpha}/>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${BACK_W} ${BACK_H}" preserveAspectRatio="none"><defs>${defs.join("")}</defs>${body}</svg>`;
}

/** The drawn back as a data URL (a CSS background, an image source). */
export function drawnBackUrl(): string {
  return `data:image/svg+xml,${encodeURIComponent(drawnBackSvg())}`;
}

/** Draws the back over a w×h canvas. */
export function drawBack(g: CanvasRenderingContext2D, w: number, h: number): void {
  g.save();
  g.scale(w / BACK_W, h / BACK_H);
  for (const s of SHAPES) {
    const path = new Path2D(s.d);
    g.globalAlpha = s.alpha ?? 1;
    if (s.fill) {
      const p = s.fill;
      if (typeof p === "string") g.fillStyle = p;
      else {
        const grad = "radial" in p ? g.createRadialGradient(p.radial[0], p.radial[1], 0, p.radial[0], p.radial[1], p.radial[2])
          : g.createLinearGradient(...p.linear);
        for (const [o, c] of p.stops) grad.addColorStop(o, c);
        g.fillStyle = grad;
      }
      g.fill(path);
    }
    if (s.stroke) {
      g.strokeStyle = s.stroke;
      g.lineWidth = s.width ?? 1;
      g.stroke(path);
    }
  }
  g.restore();
}
