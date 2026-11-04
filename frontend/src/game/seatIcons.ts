/**
 * The table's icon family: stamped brass glyphs on bevelled medallions (the candlelit card room). Drawn here with canvas
 * paths, so a 3D button's texture and the 2D table's image are the same picture:
 * - one light, from the top left: a lit upper edge and a cast shadow to the lower right on every raised part;
 * - one stroke weight (STROKE, 8 units of the 100-unit icon) with round caps and joins;
 * - one brass, on a blackened-steel field inside a bevelled brass rim.
 * The seat buttons (Untap, Draw, Scry, Mill, Reveal, Mulligan, the Bag of Extras, the importer), the Bag of Extras'
 * counters and dice, and the commander-tax medallion all come from these parts.
 */
import type { SeatActionId } from "./seatActions";

export type SeatIconId = SeatActionId | "mulligan" | "importer";
/** The Bag of Extras' counters (game/bags.ts CARD_COUNTERS, PLAYER_COUNTERS) and its token search. */
export type ToyIconId = "+1/+1" | "-1/-1" | "loyalty" | "charge" | "shield" | "stun" | "energy" | "experience" | "search";
export type DieIconId = 4 | 6 | 8 | 10 | 12 | 20;

/** The glyph's stroke, in units of the 100-unit icon (8%). */
export const STROKE = 8;

const BRASS = { hi: "#fff0c4", light: "#e8c57c", mid: "#c49553", dark: "#8c632f", deep: "#3e2a12" };
const INK = "#140f0a";
const FONT = '"Inter Variable", Inter';

// -- the parts ------------------------------------------------------------------------------------------------------

/**
 * One part of a glyph, painted in order: a stroked line, a filled shape, or a cut back to the field (`knock`, a wide
 * stroke, or the whole shape with `solid`), so a later line passes over an earlier one.
 */
type Part = { stroke: Path2D; w?: number } | { fill: Path2D } | { knock: Path2D; w?: number; solid?: boolean };

const P = (d: string) => new Path2D(d);

/** The brass of a raised part: bright at the top left, darker toward the lower right. */
function brass(g: CanvasRenderingContext2D, x0 = 24, y0 = 22, x1 = 76, y1 = 80): CanvasGradient {
  const gr = g.createLinearGradient(x0, y0, x1, y1);
  gr.addColorStop(0, BRASS.hi);
  gr.addColorStop(0.28, BRASS.light);
  gr.addColorStop(0.68, BRASS.mid);
  gr.addColorStop(1, BRASS.dark);
  return gr;
}

/** The medallion's sunken field: blackened steel, a little lighter where the light falls. */
function field(g: CanvasRenderingContext2D): CanvasGradient {
  const gr = g.createRadialGradient(40, 34, 2, 50, 50, 40);
  gr.addColorStop(0, "#3a332b");
  gr.addColorStop(0.55, "#1b1714");
  gr.addColorStop(1, "#0b0907");
  return gr;
}

function paint(g: CanvasRenderingContext2D, part: Exclude<Part, { knock: Path2D }>, style: string | CanvasGradient): void {
  g.lineCap = "round";
  g.lineJoin = "round";
  if ("stroke" in part) {
    g.strokeStyle = style;
    g.lineWidth = part.w ?? STROKE;
    g.stroke(part.stroke);
  } else {
    g.fillStyle = style;
    g.fill(part.fill);
    g.strokeStyle = style; // the same round corners as a stroke's
    g.lineWidth = 2.4;
    g.stroke(part.fill);
  }
}

/**
 * Stamp a glyph in brass, raised from the surface under it: for each part a soft shadow cast to the lower right, a
 * lit edge to the upper left, then the brass face.
 */
function stamp(g: CanvasRenderingContext2D, parts: Part[], scale: number, under: string | CanvasGradient): void {
  const metal = brass(g);
  for (const part of parts) {
    if ("knock" in part) {
      g.lineCap = "round";
      g.lineJoin = "round";
      g.strokeStyle = g.fillStyle = under;
      if (part.solid) g.fill(part.knock);
      g.lineWidth = part.w ?? STROKE + 5;
      g.stroke(part.knock);
      continue;
    }
    g.save();
    g.shadowColor = "rgba(0, 0, 0, 0.85)";
    g.shadowBlur = 2.2 * scale;
    g.shadowOffsetX = 1.3 * scale;
    g.shadowOffsetY = 1.9 * scale;
    paint(g, part, "rgba(0, 0, 0, 0.9)");
    g.restore();
    g.save();
    g.translate(-0.7, -0.9);
    paint(g, part, "rgba(255, 244, 214, 0.7)");
    g.restore();
    paint(g, part, metal);
  }
}

/**
 * The medallion: a bevelled brass rim (its outer slope lit at the top left, its inner slope shaded there) around a
 * sunken field.
 */
function medallion(g: CanvasRenderingContext2D): void {
  const ring = (rad: number, style: string | CanvasGradient) => {
    g.fillStyle = style;
    g.beginPath();
    g.arc(50, 50, rad, 0, Math.PI * 2);
    g.fill();
  };
  const slope = (a: string, b: string, c: string) => {
    const gr = g.createLinearGradient(14, 14, 86, 86);
    gr.addColorStop(0, a);
    gr.addColorStop(0.5, b);
    gr.addColorStop(1, c);
    return gr;
  };
  ring(49.5, "#1a1108"); // the edge, dark against any table
  ring(48, slope(BRASS.hi, BRASS.mid, BRASS.deep)); // the outer slope
  ring(45, slope(BRASS.light, BRASS.mid, BRASS.dark)); // the rim's flat top
  ring(42.5, slope(BRASS.deep, BRASS.dark, BRASS.light)); // the inner slope, down into the field
  ring(40.2, field(g));
  // the field sits below the rim: shadow just inside its upper-left edge
  const inner = g.createLinearGradient(20, 20, 60, 60);
  inner.addColorStop(0, "rgba(0, 0, 0, 0.65)");
  inner.addColorStop(1, "rgba(0, 0, 0, 0)");
  g.strokeStyle = inner;
  g.lineWidth = 3;
  g.beginPath();
  g.arc(50, 50, 38.7, 0, Math.PI * 2);
  g.stroke();
  // a fine highlight where the outer slope meets the light
  g.strokeStyle = "rgba(255, 246, 220, 0.6)";
  g.lineWidth = 1;
  g.beginPath();
  g.arc(50, 50, 47.3, Math.PI * 1.02, Math.PI * 1.62);
  g.stroke();
}

// -- the glyphs (centred on 50,50, inside a circle of radius ~28) -------------------------------------------------------

/** An arrowhead: a filled, round-cornered triangle with its tip at (x, y), pointing along `angle`. */
function head(x: number, y: number, angle: number, len = 13, half = 9): Path2D {
  const [c, s] = [Math.cos(angle), Math.sin(angle)];
  const bx = x - c * len, by = y - s * len;
  return P(`M${x} ${y} L${bx - s * half} ${by + c * half} L${bx + s * half} ${by - c * half} Z`);
}

/**
 * An arc with an arrowhead at its end, travelling counterclockwise (`ccw`) or clockwise: the head's tip lies on the circle
 * a head's length further round, so it follows the curve.
 */
function arcArrow(cx: number, cy: number, r: number, from: number, to: number, ccw: boolean, len = 17, half = 9): Part[] {
  const arc = new Path2D();
  arc.arc(cx, cy, r, from, to, ccw);
  const sweep = (len / r) * (ccw ? -1 : 1);
  const [bx, by] = [cx + r * Math.cos(to), cy + r * Math.sin(to)];
  const [tx, ty] = [cx + r * Math.cos(to + sweep), cy + r * Math.sin(to + sweep)];
  const dir = Math.atan2(ty - by, tx - bx);
  const back = 2; // the head's base just behind the line's end, so they join
  return [{ stroke: arc }, { fill: head(tx, ty, dir, Math.hypot(tx - bx, ty - by) + back, half) }];
}

const deg = (d: number) => (d * Math.PI) / 180;
const rect = (x: number, y: number, w: number, h: number, r: number) => {
  const p = new Path2D();
  p.roundRect(x, y, w, h, r);
  return p;
};

/** Untap: an open ring turning back (counterclockwise), its head at the top right. */
const untapGlyph = (): Part[] => arcArrow(50, 52, 20, deg(236), deg(-30), true);

/** Draw: a card, and one more. */
function drawGlyph(): Part[] {
  const plus = P("M65 24 V48 M53 36 H77");
  return [{ stroke: rect(28, 38, 27, 37, 4.5) }, { knock: plus, w: STROKE + 7 }, { stroke: plus }];
}

/** Scry: an open eye. */
const scryGlyph = (): Part[] => [
  { stroke: P("M21 51 Q50 19 79 51 Q50 83 21 51 Z") },
  { fill: P("M50 41.5 a9.5 9.5 0 1 1 -0.01 0 Z") },
];

/** Mill: a gravestone with a cross cut in it, standing on the ground. */
const millGlyph = (): Part[] => [
  { fill: P("M34 71 V44 a16 16 0 0 1 32 0 V71 Z") },
  { knock: P("M50 39 V61 M42.5 47.5 H57.5"), w: 5.5 },
  { stroke: P("M23 74 H77") },
];

/** Reveal: a card held up for the table to see, light all round it. */
const revealGlyph = (): Part[] => [
  { stroke: rect(37, 39, 26, 36, 4.5) },
  { stroke: P("M50 18 V25 M28.5 27.5 L33.5 32.5 M71.5 27.5 L66.5 32.5 M21.5 49 H27.5 M78.5 49 H72.5"), w: 6.5 },
];

/** Mulligan: the shuffle, two paths crossing. */
function mulliganGlyph(): Part[] {
  const a = P("M24 35 H33 C46 35 50 65 63 65 H66");
  const b = P("M24 65 H33 C46 65 50 35 63 35 H66");
  return [
    { stroke: b },
    { fill: head(78, 35, 0, 13, 9) },
    { knock: a, w: STROKE + 6 },
    { stroke: a },
    { fill: head(78, 65, 0, 13, 9) },
  ];
}

/** The Bag of Extras: a drawstring pouch, its mouth gathered and tied. */
const pouchGlyph = (): Part[] => [
  { fill: P("M41 45 C24 51 22 78 50 78 C78 78 76 51 59 45 Z") },
  { knock: P("M38 43.5 Q50 48 62 43.5"), w: 4 },
  { fill: P("M35 27 Q50 35 65 27 Q63.5 34 59 40.5 Q50 43.5 41 40.5 Q36.5 34 35 27 Z") },
];

/** The importer: an arrow down into a tray. */
const importerGlyph = (): Part[] => [
  { stroke: P("M27 58 V72 H73 V58") },
  { stroke: P("M50 24 V50") },
  { fill: head(50, 63, Math.PI / 2, 14, 10) },
];

const SEAT_GLYPHS: Record<SeatIconId, () => Part[]> = {
  untap: untapGlyph, draw: drawGlyph, scry: scryGlyph, mill: millGlyph, reveal: revealGlyph, mulligan: mulliganGlyph, extras: pouchGlyph, importer: importerGlyph,
};

/** A star of `n` points. */
function star(cx: number, cy: number, r: number, inner: number, n = 5): Path2D {
  let d = "";
  for (let i = 0; i < n * 2; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / n;
    const rr = i % 2 ? inner : r;
    d += `${i ? "L" : "M"}${(cx + rr * Math.cos(a)).toFixed(2)} ${(cy + rr * Math.sin(a)).toFixed(2)} `;
  }
  return P(`${d}Z`);
}

/** A spiral, round and round (stun). */
function spiral(): Path2D {
  let d = "";
  for (let i = 0; i <= 72; i++) {
    const a = (i / 72) * Math.PI * 3.3 + Math.PI;
    const r = 3.5 + (i / 72) * 20;
    d += `${i ? "L" : "M"}${(50 + r * Math.cos(a)).toFixed(2)} ${(50 + r * Math.sin(a)).toFixed(2)} `;
  }
  return P(d);
}

const TOY_GLYPHS: Record<ToyIconId, () => Part[]> = {
  "+1/+1": () => [{ stroke: P("M50 30 V70 M30 50 H70") }],
  "-1/-1": () => [{ stroke: P("M30 50 H70") }],
  // a planeswalker's loyalty: the badge, an arrow up through it
  loyalty: () => [{ fill: P("M30 28 H70 V50 C70 63 61 71 50 77 C39 71 30 63 30 50 Z") }, { knock: P("M50 66 V41 M42 48.5 L50 40.5 L58 48.5"), w: 5.5 }],
  charge: () => [{ fill: star(50, 50, 27, 8, 4) }],
  shield: () => [{ stroke: P("M31 30 Q50 23 69 30 V50 C69 62 61 70 50 76 C39 70 31 62 31 50 Z") }, { fill: P("M50 44 a6 6 0 1 1 -0.01 0 Z") }],
  stun: () => [{ stroke: spiral(), w: 6.5 }],
  energy: () => [{ fill: P("M56 21 L33 54 H48 L43 79 L67 45 H52 Z") }],
  experience: () => [{ fill: star(50, 53, 26, 11) }],
  // find any token: a lens
  search: () => [{ stroke: P("M44 45 m-15 0 a15 15 0 1 0 30 0 a15 15 0 1 0 -30 0") }, { stroke: P("M55.5 56.5 L71 72") }],
};

// -- drawing --------------------------------------------------------------------------------------------------------

/** Start a square canvas in 100-unit icon space; returns the scale. */
function begin(canvas: HTMLCanvasElement): { g: CanvasRenderingContext2D; s: number } {
  const g = canvas.getContext("2d")!;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, canvas.width, canvas.height);
  const s = canvas.width / 100;
  g.setTransform(s, 0, 0, canvas.height / 100, 0, 0);
  return { g, s };
}

/** A number typed over a button, pressed into a dark well. */
function typedOver(g: CanvasRenderingContext2D, text: string): void {
  g.fillStyle = "rgba(8, 6, 4, 0.92)";
  g.beginPath();
  g.arc(50, 50, 33, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = BRASS.light;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${text.length > 2 ? 28 : 36}px ${FONT}, sans-serif`;
  g.fillText(text, 50, 52);
}

/** Draw a seat button's face into a square canvas (any size). `count` is a number being typed over it. */
export function drawSeatIcon(canvas: HTMLCanvasElement, id: SeatIconId, count = ""): void {
  const { g, s } = begin(canvas);
  medallion(g);
  stamp(g, SEAT_GLYPHS[id](), s, field(g));
  if (count) typedOver(g, count);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/** Draw one of the Bag of Extras' counters (or its token search): the same medallion, its own glyph. */
export function drawToyIcon(canvas: HTMLCanvasElement, id: ToyIconId): void {
  const { g, s } = begin(canvas);
  medallion(g);
  stamp(g, TOY_GLYPHS[id](), s, field(g));
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/** The facets of each die seen a little from above, [points, light]; the face with its number last (as DieGlyph). */
const DIE: Record<DieIconId, { facets: [string, number][]; text: [number, number, number] }> = {
  4: { facets: [["50,8 8,86 50,70", 1.18], ["50,8 92,86 50,70", 0.72], ["8,86 92,86 50,70", 0.55], ["50,22 22,78 78,78", 1]], text: [50, 63, 28] },
  6: { facets: [["14,26 30,12 92,12 76,26", 1.25], ["76,26 92,12 92,74 76,88", 0.66], ["14,26 76,26 76,88 14,88", 1]], text: [45, 59, 38] },
  8: { facets: [["50,4 6,50 50,96", 1.16], ["50,4 94,50 50,96", 0.7], ["50,10 14,50 50,60 86,50", 1.32], ["14,50 50,60 86,50 50,92", 0.86], ["50,14 18,54 82,54", 1]], text: [50, 42, 28] },
  10: { facets: [["50,4 6,46 16,62 50,96", 1.15], ["50,4 94,46 84,62 50,96", 0.68], ["16,62 50,96 84,62 50,72", 0.6], ["50,4 18,48 50,70 82,48", 1]], text: [50, 49, 25] },
  12: { facets: [["50,4 92,32 78,86 22,86 8,32", 0.7], ["50,4 8,32 26,40 50,22", 1.25], ["50,4 92,32 74,40 50,22", 1.05], ["8,32 22,86 32,74 26,40", 1.1], ["92,32 78,86 68,74 74,40", 0.6], ["22,86 78,86 68,74 32,74", 0.75], ["50,22 74,40 68,74 32,74 26,40", 1]], text: [50, 51, 26] },
  20: { facets: [["50,3 92,27 92,73 50,97 8,73 8,27", 0.72], ["50,3 8,27 22,62", 1.22], ["50,3 92,27 78,62", 0.9], ["8,27 8,73 22,62", 1.08], ["92,27 92,73 78,62", 0.58], ["8,73 50,97 22,62", 0.85], ["92,73 50,97 78,62", 0.55], ["22,62 78,62 50,97", 0.7], ["50,3 22,62 78,62", 1]], text: [50, 45, 26] },
};

const shade = (k: number) => {
  const base = [200, 152, 86];
  return `rgb(${base.map((v) => Math.round(k >= 1 ? v + (255 - v) * (k - 1) * 1.1 : v * (0.35 + 0.65 * k))).join(", ")})`;
};
const poly = (pts: string) => P(`M${pts.replace(/ /g, " L")} Z`);

/** A die in solid brass, its facets lit from the top left, its number engraved in the front face. */
export function drawDieIcon(canvas: HTMLCanvasElement, sides: DieIconId): void {
  const { g, s } = begin(canvas);
  const die = DIE[sides];
  g.setTransform(s * 0.9, 0, 0, s * 0.9, s * 4, s * 4); // a margin for the shadow
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.8)";
  g.shadowBlur = 3 * s;
  g.shadowOffsetX = 1.6 * s;
  g.shadowOffsetY = 2.4 * s;
  g.fillStyle = "#1a1108";
  for (const [pts] of die.facets) g.fill(poly(pts));
  g.restore();
  for (const [pts, k] of die.facets) {
    const f = poly(pts);
    g.fillStyle = shade(k);
    g.fill(f);
    g.strokeStyle = "rgba(48, 31, 10, 0.9)";
    g.lineWidth = 2.4;
    g.lineJoin = "round";
    g.stroke(f);
  }
  const [x, y, size] = die.text;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${size}px ${FONT}, sans-serif`;
  g.fillStyle = "rgba(255, 240, 205, 0.75)";
  g.fillText(String(sides), x + 0.9, y + 1.2);
  g.fillStyle = INK;
  g.fillText(String(sides), x, y);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/**
 * A commander's tax: a small medallion with a crown (the commander) over a generic-mana pip carrying the tax, as {2}
 * reads on a card. At 0 it waits, dim; once the commander has been cast it is lit, the number dark on a pale pip.
 */
export function drawTaxMedallion(canvas: HTMLCanvasElement, tax: number): void {
  const { g, s } = begin(canvas);
  const lit = tax > 0;
  medallion(g);
  stamp(g, [{ fill: P("M40.5 25 L42 15.5 L46.3 20.5 L50 13.5 L53.7 20.5 L58 15.5 L59.5 25 Z") }], s, field(g));
  const [px, py, pr] = [50, 56, 26.5];
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.8)";
  g.shadowBlur = 2.2 * s;
  g.shadowOffsetX = 0.9 * s;
  g.shadowOffsetY = 1.5 * s;
  const pip = g.createRadialGradient(px - 7, py - 8, 2, px, py, pr + 2);
  pip.addColorStop(0, lit ? "#f6f1e8" : "#4d463e");
  pip.addColorStop(1, lit ? "#b8ae9f" : "#27231e");
  g.fillStyle = pip;
  g.beginPath();
  g.arc(px, py, pr, 0, Math.PI * 2);
  g.fill();
  g.restore();
  g.strokeStyle = lit ? "rgba(60, 45, 25, 0.9)" : "rgba(0, 0, 0, 0.7)";
  g.lineWidth = 1.6;
  g.beginPath();
  g.arc(px, py, pr, 0, Math.PI * 2);
  g.stroke();
  const n = String(Math.max(0, Math.min(99, tax)));
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${n.length > 1 ? 32 : 42}px ${FONT}, sans-serif`;
  g.fillStyle = lit ? INK : "#a39a8d";
  g.fillText(n, px, py + 2.5);
  if (!lit) {
    // waiting: the whole medallion a step darker than a lit one
    g.globalCompositeOperation = "source-atop";
    g.fillStyle = "rgba(6, 5, 4, 0.34)";
    g.fillRect(0, 0, 100, 100);
    g.globalCompositeOperation = "source-over";
  }
  g.setTransform(1, 0, 0, 1, 0, 0);
}

// -- as images (the 2D table and the panels) ---------------------------------------------------------------------------

const urls = new Map<string, string>();
function cachedUrl(key: string, draw: (c: HTMLCanvasElement) => void): string {
  const known = urls.get(key);
  if (known) return known;
  const c = document.createElement("canvas");
  c.width = c.height = 128; // sharp at twice the size it is shown
  draw(c);
  const url = c.toDataURL("image/png");
  urls.set(key, url);
  return url;
}

/** The face as an image URL (for the 2D buttons), drawn once. */
export const seatIconUrl = (id: SeatIconId): string => cachedUrl(`seat:${id}`, (c) => drawSeatIcon(c, id));
export const toyIconUrl = (id: ToyIconId): string => cachedUrl(`toy:${id}`, (c) => drawToyIcon(c, id));
export const dieIconUrl = (sides: DieIconId): string => cachedUrl(`die:${sides}`, (c) => drawDieIcon(c, sides));
export const taxMedallionUrl = (tax: number): string => cachedUrl(`tax:${tax}`, (c) => drawTaxMedallion(c, tax));

/** The number font, once loaded: images with numbers drawn before it (tax, dice) are drawn again by whoever asks. */
export function whenIconFontReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts?.load) return Promise.resolve();
  return document.fonts.load(`800 20px ${FONT}`).then(() => {
    for (const k of [...urls.keys()]) if (k.startsWith("tax:") || k.startsWith("die:")) urls.delete(k);
  }, () => undefined);
}
