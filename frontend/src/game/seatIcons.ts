/**
 * The table's icon family: stamped brass glyphs on bevelled medallions (the candlelit card room). Drawn here with canvas
 * paths, so a 3D button's texture and the 2D table's image are the same picture. One construction for every glyph:
 * - brass lines of one weight (STROKE, 8 units of the 100-unit icon), round caps and joins, open chevron arrowheads;
 *   no filled shapes, so no glyph reads heavier than another;
 * - one light, from the top left: a lit upper edge and a soft shadow cast to the lower right;
 * - one brass, on a blackened-steel field inside a bevelled brass rim.
 * The seat buttons (Untap, Draw, Scry, Mill, Reveal, Mulligan, the Bag of Extras, the importer), the Bag of Extras'
 * counters, dice, close button and token emblem cards, and the commander-tax coin all come from these parts.
 */
import type { SeatActionId } from "./seatActions";
import { GLYPH_BOX, SEAT_GLYPH_PATHS } from "./seatGlyphs";
import { ZONE_GLYPH_PATHS } from "./zoneGlyphs";

export type SeatIconId = SeatActionId | "mulligan" | "importer";
/** The Bag of Extras' counters (game/bags.ts CARD_COUNTERS, PLAYER_COUNTERS), its token search (the book) and the close button. */
export type ToyIconId = "+1/+1" | "-1/-1" | "loyalty" | "charge" | "shield" | "stun" | "energy" | "experience" | "search" | "book" | "close";
export type DieIconId = 4 | 6 | 8 | 10 | 12 | 20;
/** The common tokens' emblems (game/bags.ts COMMON_TOKENS), for a token whose art isn't cached. */
export type TokenEmblemId = "treasure" | "clue" | "food" | "blood" | "soldier" | "spirit" | "goblin" | "saproling" | "thopter";

/** The glyph's stroke, in units of the 100-unit icon (8%). */
export const STROKE = 8;

const BRASS = { hi: "#fff0c4", light: "#e8c57c", mid: "#c49553", dark: "#8c632f", deep: "#3e2a12" };
const INK = "#140f0a";
/** The seat chits' printing ink: a warm near-black. */
const INK_PRINT = "#1e140b";
const FONT = '"Inter Variable", Inter';
const DISPLAY = "Cinzel, Georgia, serif";

// -- the parts ------------------------------------------------------------------------------------------------------

/** One part of a glyph, painted in order: a brass line, or a cut back to the surface under it (so a later line passes over). */
type Part = { stroke: Path2D } | { knock: Path2D; w?: number; solid?: boolean };

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

const line = (g: CanvasRenderingContext2D, path: Path2D, style: string | CanvasGradient) => {
  g.lineCap = "round";
  g.lineJoin = "round";
  g.lineWidth = STROKE;
  g.strokeStyle = style;
  g.stroke(path);
};

/**
 * Stamp a glyph in brass, raised from the surface under it: for each line a soft shadow cast to the lower right, a lit
 * edge to the upper left, then the brass face.
 */
function stamp(g: CanvasRenderingContext2D, parts: Part[], scale: number, under: string | CanvasGradient): void {
  const metal = brass(g);
  for (const part of parts) {
    if ("knock" in part) {
      g.lineCap = "round";
      g.lineJoin = "round";
      g.strokeStyle = g.fillStyle = under;
      if (part.solid) g.fill(part.knock);
      g.lineWidth = part.w ?? STROKE + 6;
      g.stroke(part.knock);
      continue;
    }
    g.save();
    g.shadowColor = "rgba(0, 0, 0, 0.85)";
    g.shadowBlur = 2.2 * scale;
    g.shadowOffsetX = 1.3 * scale;
    g.shadowOffsetY = 1.9 * scale;
    line(g, part.stroke, "rgba(0, 0, 0, 0.9)");
    g.restore();
    g.save();
    g.translate(-0.7, -0.9);
    line(g, part.stroke, "rgba(255, 244, 214, 0.72)");
    g.restore();
    line(g, part.stroke, metal);
  }
}

/** The medallion: a bevelled brass rim (its outer slope lit at the top left, its inner slope shaded there) around a sunken field. */
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

// -- the glyphs (centred on 50,50, inside a circle of radius ~29) -------------------------------------------------------

const rect = (x: number, y: number, w: number, h: number, r: number) => {
  const p = new Path2D();
  p.roundRect(x, y, w, h, r);
  return p;
};

/** A star of `n` points, as an outline. */
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
    const a = (i / 72) * Math.PI * 3.1 + Math.PI;
    const r = 4 + (i / 72) * 20;
    d += `${i ? "L" : "M"}${(50 + r * Math.cos(a)).toFixed(2)} ${(50 + r * Math.sin(a)).toFixed(2)} `;
  }
  return P(d);
}

const lens = (): Part[] => [{ stroke: P("M44 45 m-15 0 a15 15 0 1 0 30 0 a15 15 0 1 0 -30 0") }, { stroke: P("M55.5 56.5 L71 72") }];

const TOY_GLYPHS: Record<ToyIconId, () => Part[]> = {
  "+1/+1": () => [{ stroke: P("M50 29 V71 M29 50 H71") }],
  "-1/-1": () => [{ stroke: P("M29 50 H71") }],
  // a planeswalker's loyalty going up: two chevrons
  loyalty: () => [{ stroke: P("M32 52 L50 34 L68 52") }, { stroke: P("M32 70 L50 52 L68 70") }],
  // charge: a spark
  charge: () => [{ stroke: P("M50 25 V75 M25 50 H75") }, { stroke: P("M39 39 L61 61 M61 39 L39 61") }],
  shield: () => [{ stroke: P("M31 31 Q50 23 69 31 V50 C69 62 61 70 50 76 C39 70 31 62 31 50 Z") }, { stroke: P("M50 36 V64") }],
  stun: () => [{ stroke: spiral() }],
  // energy: the bolt
  energy: () => [{ stroke: P("M58 22 L38 52 L62 49 L42 79") }],
  experience: () => [{ stroke: star(50, 53, 25, 12) }],
  search: lens,
  // find any token: the catalogue, an open book (the lens is Clue's)
  book: () => [{ stroke: P("M50 33 C42 27 31 27 23 31 V70 C31 66 42 66 50 72 C58 66 69 66 77 70 V31 C69 27 58 27 50 33 Z") }, { stroke: P("M50 33 V72") }],
  close: () => [{ stroke: P("M35 35 L65 65 M65 35 L35 65") }],
};

/** The common tokens' emblems, in the same lines. */
const EMBLEMS: Record<TokenEmblemId, () => Part[]> = {
  treasure: () => [{ stroke: P("M27 49 H73 V73 H27 Z") }, { stroke: P("M27 49 V44 Q27 31 50 31 Q73 31 73 44 V49") }, { stroke: P("M50 45 V57") }],
  clue: lens,
  food: () => [{ stroke: P("M22 68 C22 38 78 38 78 68 Z") }, { stroke: P("M38 49 L43 57 M52 46 L57 54 M64 51 L67 57") }],
  blood: () => [{ stroke: P("M42 25 V64 a8 8 0 0 0 16 0 V25") }, { stroke: P("M37 25 H63") }, { stroke: P("M42 50 H58") }],
  soldier: () => [{ stroke: P("M50 22 V64") }, { stroke: P("M37 56 H63") }, { stroke: P("M50 64 V77") }],
  spirit: () => [{ stroke: P("M50 78 C35 73 31 58 40 48 C46 41 44 33 50 22 C61 34 68 45 64 59 C61 70 56 75 50 78 Z") }, { stroke: P("M50 66 C45 62 46 55 50 50") }],
  goblin: () => [{ stroke: P("M50 57 m-15 0 a15 15 0 1 0 30 0 a15 15 0 1 0 -30 0") }, { stroke: P("M36 53 L17 45 L37 63 M64 53 L83 45 L63 63") }, { stroke: P("M44 55 h0.01 M56 55 h0.01") }],
  saproling: () => [{ stroke: P("M50 78 V48") }, { stroke: P("M50 55 C38 55 29 47 29 36 C40 36 50 43 50 55") }, { stroke: P("M50 49 C50 37 58 28 71 28 C71 40 62 49 50 49") }],
  thopter: () => [{ stroke: P("M50 40 C56 46 56 66 50 74 C44 66 44 46 50 40 Z") }, { stroke: P("M45 50 C35 36 21 34 16 42 C24 50 35 54 45 56 M55 50 C65 36 79 34 84 42 C76 50 65 54 55 56") }],
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

/**
 * An ivory gaming chit (the bone counters of an old card room): a rounded square of warm ivory, lit from the top left,
 * a fine engraved line inside its edge, and its glyph printed in ink (seatGlyphs.ts: game-icons.net, CC BY 3.0).
 */
function chit(g: CanvasRenderingContext2D): void {
  const face = new Path2D();
  face.roundRect(3, 3, 94, 94, 20);
  g.fillStyle = "#2a1c10"; // its dark edge, so it reads on any table
  g.fill(face);
  const body = new Path2D();
  body.roundRect(5, 5, 90, 90, 18);
  const ivory = g.createLinearGradient(10, 8, 90, 92);
  ivory.addColorStop(0, "#fbf4e2");
  ivory.addColorStop(0.55, "#eadcbc");
  ivory.addColorStop(1, "#c9b48a");
  g.fillStyle = ivory;
  g.fill(body);
  // the light catching its top-left edge, the shade along its lower right
  g.save();
  g.clip(body);
  g.lineWidth = 3;
  g.strokeStyle = "rgba(255, 253, 244, 0.85)";
  const lit = new Path2D();
  lit.roundRect(6.5, 6.5, 90, 90, 18);
  g.stroke(lit);
  g.strokeStyle = "rgba(92, 64, 30, 0.45)";
  const shade = new Path2D();
  shade.roundRect(3.5, 3.5, 90, 90, 18);
  g.stroke(shade);
  g.restore();
  // the engraved line inside the edge
  g.strokeStyle = "rgba(90, 62, 30, 0.55)";
  g.lineWidth = 1.2;
  const line = new Path2D();
  line.roundRect(12, 12, 76, 76, 12);
  g.stroke(line);
}

/** A seat glyph in ink, centred in the chit (`size`: its width in icon units). */
function inkGlyph(g: CanvasRenderingContext2D, id: SeatIconId, size = 68): void {
  const k = size / GLYPH_BOX;
  g.save();
  g.translate(50 - size / 2, 50 - size / 2);
  g.scale(k, k);
  g.fillStyle = INK_PRINT;
  g.fill(new Path2D(SEAT_GLYPH_PATHS[id].d));
  g.restore();
}

/** Draw a seat button's face into a square canvas (any size). `count`: a number being typed over it, which replaces the glyph. */
export function drawSeatIcon(canvas: HTMLCanvasElement, id: SeatIconId, count = ""): void {
  const { g } = begin(canvas);
  chit(g);
  if (count) {
    g.fillStyle = INK_PRINT;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.font = `800 ${count.length > 2 ? 34 : 46}px ${FONT}, sans-serif`;
    g.fillText(count, 50, 53);
  } else {
    inkGlyph(g, id);
  }
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/** Draw one of the Bag of Extras' counters (or its search, or a close button): the same medallion, its own glyph. */
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

/** How many times a commander has been cast from the command zone, for a tax of `tax` ({2} a cast). */
export function taxCasts(tax: number): number {
  return Math.ceil(Math.max(0, tax) / 2);
}

/** The commander-tax tooltip's first line: "Commander tax: +4 (cast 2 times from the command zone)". */
export function taxSentence(tax: number): string {
  const n = taxCasts(tax);
  if (!n) return "Commander tax: none yet (not cast from the command zone)";
  return `Commander tax: +${tax} (cast ${n === 1 ? "once" : `${n} times`} from the command zone)`;
}

/** The crown (game-icons.net, lorc/crown: zoneGlyphs.ts), fitted to a box `w` wide centred on (cx, cy). */
function crownPath(g: CanvasRenderingContext2D, cx: number, cy: number, w: number): Path2D {
  const k = w / 480;
  const p = new Path2D();
  p.addPath(new Path2D(ZONE_GLYPH_PATHS.command.d), new DOMMatrix([k, 0, 0, k, cx - 256 * k, cy - 255 * k]));
  void g;
  return p;
}

/** A brass coin's face seen from above, centred on (cx, cy): a dark edge, a reeded rim lit from the top left, a struck field. */
function coinFace(g: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
  const disc = (rad: number, style: string | CanvasGradient) => {
    g.fillStyle = style;
    g.beginPath();
    g.arc(cx, cy, rad, 0, Math.PI * 2);
    g.fill();
  };
  const lin = (a: string, b: string, c: string) => {
    const gr = g.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    gr.addColorStop(0, a);
    gr.addColorStop(0.5, b);
    gr.addColorStop(1, c);
    return gr;
  };
  disc(r + 1.4, "#1c1206");
  disc(r, lin(BRASS.hi, BRASS.mid, BRASS.dark)); // the rim
  // the reeding: fine ticks round the rim
  g.save();
  g.strokeStyle = "rgba(60, 38, 12, 0.55)";
  g.lineWidth = r / 40;
  for (let i = 0; i < 60; i++) {
    const a = (i / 60) * Math.PI * 2;
    g.beginPath();
    g.moveTo(cx + Math.cos(a) * r * 0.86, cy + Math.sin(a) * r * 0.86);
    g.lineTo(cx + Math.cos(a) * r * 0.97, cy + Math.sin(a) * r * 0.97);
    g.stroke();
  }
  g.restore();
  disc(r * 0.84, lin(BRASS.dark, BRASS.mid, BRASS.light)); // the rim's inner slope, shaded at the top left
  const field = g.createRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 0.05, cx, cy, r * 0.8);
  field.addColorStop(0, "#e9c985");
  field.addColorStop(0.6, "#c39552");
  field.addColorStop(1, "#9a6d34");
  disc(r * 0.79, field);
}

/** An empty coin socket, sunk into the wood: a dark round hollow with a fine brass ring, the crown pressed faintly in. */
function coinSocket(g: CanvasRenderingContext2D, cx: number, cy: number, r: number): void {
  const hollow = g.createRadialGradient(cx + r * 0.2, cy + r * 0.25, r * 0.1, cx, cy, r);
  hollow.addColorStop(0, "#2a2018");
  hollow.addColorStop(1, "#0c0806");
  g.fillStyle = hollow;
  g.beginPath();
  g.arc(cx, cy, r, 0, Math.PI * 2);
  g.fill();
  // the lip's shadow inside its upper-left edge, and light caught on its lower-right one
  g.lineWidth = r * 0.1;
  g.strokeStyle = "rgba(0, 0, 0, 0.7)";
  g.beginPath();
  g.arc(cx, cy, r * 0.93, Math.PI * 0.9, Math.PI * 1.85);
  g.stroke();
  g.lineWidth = r * 0.05;
  g.strokeStyle = "rgba(201, 160, 90, 0.75)";
  g.beginPath();
  g.arc(cx, cy, r, 0, Math.PI * 2);
  g.stroke();
  g.fillStyle = "rgba(255, 226, 170, 0.13)";
  g.fill(crownPath(g, cx, cy + r * 0.04, r * 1.05));
}

/**
 * A commander's tax, for the 2D table (and the same language as the 3D table's coin column): a brass coin with the
 * tax to pay struck on it ("+4"), with a coin edge peeking from under it for each earlier cast (two at most). At 0 an
 * empty coin socket, quiet.
 */
export function drawTaxMedallion(canvas: HTMLCanvasElement, tax: number): void {
  const { g, s } = begin(canvas);
  const casts = taxCasts(tax);
  if (!casts) {
    coinSocket(g, 50, 50, 44);
    g.setTransform(1, 0, 0, 1, 0, 0);
    return;
  }
  const under = Math.min(2, casts - 1);
  const r = 40;
  const cy = 46 - under * 2.5;
  // the coins under it: their edges, a sliver each, lower down
  for (let i = under; i >= 1; i--) {
    const y = cy + i * 5;
    g.fillStyle = "#1c1206";
    g.beginPath();
    g.arc(50, y, r + 1.4, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = i === 1 ? BRASS.dark : "#6e4c22";
    g.beginPath();
    g.arc(50, y, r, 0, Math.PI * 2);
    g.fill();
  }
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.6)";
  g.shadowBlur = 2 * s;
  g.shadowOffsetY = 1.2 * s;
  g.fillStyle = "#1c1206";
  g.beginPath();
  g.arc(50, cy, r + 1.4, 0, Math.PI * 2);
  g.fill();
  g.restore();
  coinFace(g, 50, cy, r);
  // the tax, struck into the field: dark, with a lit edge under it
  const n = `+${Math.min(99, Math.max(0, tax))}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${n.length > 2 ? 34 : 42}px ${FONT}, sans-serif`;
  g.fillStyle = "rgba(255, 240, 200, 0.6)";
  g.fillText(n, 50.6, cy + 3.4);
  g.fillStyle = "#2a1906";
  g.fillText(n, 50, cy + 2.4);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/** The 3D table's tax coin, its top face (a square canvas): the coin with the crown struck in its field. */
export function drawTaxCoinFace(canvas: HTMLCanvasElement): void {
  const { g } = begin(canvas);
  coinFace(g, 50, 50, 48.5);
  const crown = crownPath(g, 50, 51, 58);
  g.fillStyle = "rgba(255, 244, 214, 0.55)";
  g.save();
  g.translate(-0.6, -0.8);
  g.fill(crown);
  g.restore();
  g.fillStyle = "#6a4518";
  g.fill(crown);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/** The 3D table's empty tax socket (a square canvas). */
export function drawTaxSocket(canvas: HTMLCanvasElement): void {
  const { g } = begin(canvas);
  coinSocket(g, 50, 50, 46);
  g.setTransform(1, 0, 0, 1, 0, 0);
}

/**
 * The 3D table's tax tag (a canvas 5:3): a small engraved brass tag with the tax to pay ("+4"), its corners clipped, a
 * fine engraved line inside its edge. `stretch`: how much taller than wide its numerals are drawn (a tag seen at a
 * slant reads upright).
 */
export function drawTaxTag(canvas: HTMLCanvasElement, tax: number, stretch = 1): void {
  const g = canvas.getContext("2d")!;
  const W = canvas.width;
  const H = canvas.height;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, W, H);
  const c = H * 0.2;
  const tag = new Path2D(`M${c} 3 H${W - c} L${W - 3} ${c} V${H - c} L${W - c} ${H - 3} H${c} L3 ${H - c} V${c} Z`);
  const face = g.createLinearGradient(0, 0, W * 0.6, H * 1.4);
  face.addColorStop(0, BRASS.hi);
  face.addColorStop(0.3, BRASS.light);
  face.addColorStop(0.75, BRASS.mid);
  face.addColorStop(1, BRASS.dark);
  g.fillStyle = "#1c1206";
  g.fill(tag);
  g.save();
  g.translate(W / 2, H / 2);
  g.scale(1 - 6 / W, 1 - 6 / H);
  g.translate(-W / 2, -H / 2);
  g.fillStyle = face;
  g.fill(tag);
  g.restore();
  g.save();
  g.translate(W / 2, H / 2);
  g.scale(0.86, 0.78);
  g.translate(-W / 2, -H / 2);
  g.strokeStyle = "rgba(70, 44, 14, 0.7)";
  g.lineWidth = 2.5;
  g.stroke(tag);
  g.restore();
  const n = `+${Math.min(99, Math.max(0, tax))}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  const px = Math.min(H * 0.62 / stretch, (W * 0.62) / (n.length * 0.62));
  g.font = `800 ${px}px ${FONT}, sans-serif`;
  g.save();
  g.translate(W / 2, H / 2 + H * 0.03);
  g.scale(1, stretch);
  g.fillStyle = "rgba(255, 244, 214, 0.7)";
  g.fillText(n, 1, 1.5);
  g.fillStyle = "#24160a";
  g.fillText(n, 0, 0);
  g.restore();
}

/** A token's colour as the tint of its emblem card's name band. */
const BAND: Record<string, string> = { W: "#5b5341", U: "#2c4a63", B: "#2e2730", R: "#6a2c22", G: "#2f4d2a", C: "#45403a" };

/**
 * A common token whose art isn't cached, as a card of the room: a walnut card in a brass frame, its name on a band in
 * the token's colour, its emblem in brass lines, its type, and its power and toughness in a brass box.
 * The canvas is card-shaped (63:88).
 */
export function drawTokenCard(canvas: HTMLCanvasElement, emblem: TokenEmblemId, face: { name: string; type: string; pt?: string; colors?: string[] }): void {
  const g = canvas.getContext("2d")!;
  const s = canvas.width / 160;
  g.setTransform(s, 0, 0, s, 0, 0);
  g.clearRect(0, 0, 160, 224);
  const wood = g.createLinearGradient(0, 0, 0, 224);
  wood.addColorStop(0, "#3a2617");
  wood.addColorStop(1, "#1b110a");
  g.fillStyle = wood;
  g.fill(rect(0, 0, 160, 223.5, 8));
  // the grain: a few faint lines across the wood
  g.strokeStyle = "rgba(255, 214, 160, 0.05)";
  g.lineWidth = 1;
  for (let y = 9; y < 224; y += 7.5) {
    g.beginPath();
    g.moveTo(0, y);
    g.bezierCurveTo(50, y + 2.5, 110, y - 2.5, 160, y + 1);
    g.stroke();
  }
  const frame = g.createLinearGradient(0, 0, 160, 224);
  frame.addColorStop(0, BRASS.hi);
  frame.addColorStop(0.5, BRASS.mid);
  frame.addColorStop(1, BRASS.dark);
  g.strokeStyle = frame;
  g.lineWidth = 2.5;
  g.stroke(rect(5, 5, 150, 213.5, 6));
  // the name band
  const tint = BAND[(face.colors?.length ?? 0) > 1 ? "C" : face.colors?.[0] ?? "C"] ?? BAND.C!;
  g.fillStyle = tint;
  g.fill(rect(11, 11, 138, 24, 3));
  g.strokeStyle = "rgba(255, 230, 180, 0.35)";
  g.lineWidth = 1;
  g.stroke(rect(11, 11, 138, 24, 3));
  g.fillStyle = "#f2dca6";
  g.font = `600 15px ${DISPLAY}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(face.name, 80, 24);
  // the emblem's field
  const f = g.createRadialGradient(70, 80, 6, 80, 95, 70);
  f.addColorStop(0, "#2f281f");
  f.addColorStop(1, "#0e0b08");
  g.fillStyle = f;
  g.fill(rect(11, 40, 138, 112, 3));
  g.save();
  g.translate(80 - 55, 96 - 55);
  g.scale(1.1, 1.1);
  stamp(g, EMBLEMS[emblem](), s * 1.1, f);
  g.restore();
  // the type line and the P/T box
  g.fillStyle = "rgba(242, 220, 166, 0.75)";
  g.font = `600 10.5px ${FONT}, sans-serif`;
  g.textAlign = "left";
  g.fillText(face.type.replace(/^Token /, ""), 14, 166);
  g.strokeStyle = "rgba(196, 149, 83, 0.6)";
  g.beginPath();
  g.moveTo(14, 176);
  g.lineTo(146, 176);
  g.stroke();
  if (face.pt) {
    g.fillStyle = "#120c08";
    g.fill(rect(104, 188, 44, 26, 4));
    g.strokeStyle = frame;
    g.lineWidth = 2;
    g.stroke(rect(104, 188, 44, 26, 4));
    g.fillStyle = "#f2dca6";
    g.font = `800 16px ${FONT}, sans-serif`;
    g.textAlign = "center";
    g.fillText(face.pt, 126, 202);
  }
  g.setTransform(1, 0, 0, 1, 0, 0);
}

// -- as images (the 2D table and the panels) ---------------------------------------------------------------------------

const urls = new Map<string, string>();
function cachedUrl(key: string, draw: (c: HTMLCanvasElement) => void, w = 128, h = w): string {
  const known = urls.get(key);
  if (known) return known;
  const c = document.createElement("canvas");
  c.width = w; // sharp at twice the size it is shown
  c.height = h;
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
export const tokenCardUrl = (emblem: TokenEmblemId, face: { name: string; type: string; pt?: string; colors?: string[] }): string =>
  cachedUrl(`token:${emblem}:${face.name}`, (c) => drawTokenCard(c, emblem, face), 160, 224);

/** The fonts, once loaded: images with text drawn before them (tax, dice, token cards) are drawn again by whoever asks. */
export function whenIconFontReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts?.load) return Promise.resolve();
  return Promise.all([document.fonts.load(`800 20px ${FONT}`), document.fonts.load(`600 15px Cinzel`)]).then(() => {
    for (const k of [...urls.keys()]) if (k.startsWith("tax:") || k.startsWith("die:") || k.startsWith("token:")) urls.delete(k);
  }, () => undefined);
}
