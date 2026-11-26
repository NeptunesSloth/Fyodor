/**
 * The table's icon family: stamped brass glyphs on bevelled medallions (the candlelit card room). Drawn here with canvas
 * paths, so a 3D button's texture and the 2D table's image are the same picture. One construction for every glyph:
 * - brass lines of one weight (STROKE, 8 units of the 100-unit icon), round caps and joins, open chevron arrowheads;
 *   no filled shapes, so no glyph reads heavier than another;
 * - one light, from the top left: a lit upper edge and a soft shadow cast to the lower right;
 * - one brass, on a blackened-steel field inside a bevelled brass rim.
 * The panels' close buttons and the commander-tax coin come from these parts (the Bag of Extras draws its own:
 * game/bagIcons.tsx). The seat buttons (Untap, Draw, Scry, Mill, Reveal, Mulligan, the Bag of Extras, the importer) are
 * round coloured chips instead, one jewel tone each (game/seatChips.ts), with the same glyphs in ivory.
 */
import type { SeatActionId } from "./seatActions";
import { GLYPH_BOX, SEAT_GLYPH_PATHS } from "./seatGlyphs";
import { ZONE_GLYPH_PATHS } from "./zoneGlyphs";
import { CHIP_INK, SEAT_CHIPS } from "./seatChips";

export type SeatIconId = SeatActionId | "mulligan" | "importer";
/** A panel's close button (the card preview's). */
export type ToyIconId = "close";

/** The glyph's stroke, in units of the 100-unit icon (8%). */
export const STROKE = 8;

const BRASS = { hi: "#fff0c4", light: "#e8c57c", mid: "#c49553", dark: "#8c632f", deep: "#3e2a12" };
const FONT = '"Inter Variable", Inter';

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

const TOY_GLYPHS: Record<ToyIconId, () => Part[]> = {
  close: () => [{ stroke: P("M35 35 L65 65 M65 35 L35 65") }],
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
 * A round gaming chip in the button's own colour (seatChips.ts), lit from the top left: a dark edge so it reads on any
 * table, a plain bevelled body, a fine brass inlay round a slightly sunken
 * face, and its glyph printed in ivory (seatGlyphs.ts: game-icons.net, CC BY 3.0).
 */
function chip(g: CanvasRenderingContext2D, id: SeatIconId): void {
  const c = SEAT_CHIPS[id];
  const disc = (r: number, style: string | CanvasGradient) => {
    g.fillStyle = style;
    g.beginPath();
    g.arc(50, 50, r, 0, Math.PI * 2);
    g.fill();
  };
  const slope = (a: string, b: string, d: string) => {
    const gr = g.createLinearGradient(14, 12, 86, 88);
    gr.addColorStop(0, a);
    gr.addColorStop(0.5, b);
    gr.addColorStop(1, d);
    return gr;
  };
  disc(49.5, "#100a05"); // the edge, dark against any table
  disc(48, slope(c.light, c.base, c.dark)); // the body, its rim lit at the top left
  // the brass inlay round the face, then the face a step down (its inner slope shaded at the top left)
  disc(38.6, slope(BRASS.light, BRASS.mid, BRASS.dark));
  disc(37, slope(c.dark, c.base, c.light));
  const face = g.createRadialGradient(42, 38, 3, 50, 50, 36);
  face.addColorStop(0, c.light);
  face.addColorStop(0.55, c.base);
  face.addColorStop(1, c.dark);
  disc(35.4, face);
  // a fine highlight where the rim meets the light
  g.strokeStyle = "rgba(255, 248, 228, 0.5)";
  g.lineWidth = 1;
  g.beginPath();
  g.arc(50, 50, 47.2, Math.PI * 1.05, Math.PI * 1.6);
  g.stroke();
}

/** A seat glyph in ivory, centred on the chip's face (`size`: its width in icon units), with a soft shadow under it. */
function inkGlyph(g: CanvasRenderingContext2D, id: SeatIconId, scale: number, size = 56): void {
  const k = size / GLYPH_BOX;
  g.save();
  g.translate(50 - size / 2, 50 - size / 2);
  g.scale(k, k);
  g.shadowColor = "rgba(0, 0, 0, 0.7)";
  g.shadowBlur = 1.6 * scale;
  g.shadowOffsetX = 0.6 * scale;
  g.shadowOffsetY = 1 * scale;
  g.fillStyle = CHIP_INK;
  g.fill(new Path2D(SEAT_GLYPH_PATHS[id].d));
  g.restore();
}

/** Draw a seat button's face into a square canvas (any size). `count`: a number being typed over it, which replaces the glyph. */
export function drawSeatIcon(canvas: HTMLCanvasElement, id: SeatIconId, count = ""): void {
  const { g, s } = begin(canvas);
  chip(g, id);
  if (count) {
    g.save();
    g.shadowColor = "rgba(0, 0, 0, 0.7)";
    g.shadowBlur = 1.6 * s;
    g.shadowOffsetY = 1 * s;
    g.fillStyle = CHIP_INK;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.font = `800 ${count.length > 2 ? 26 : 36}px ${FONT}, sans-serif`;
    g.fillText(count, 50, 52);
    g.restore();
  } else {
    inkGlyph(g, id, s);
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

/**
 * The top coin of a commander's tax stack (a square canvas): the struck coin with the tax to pay ("+4") struck large in
 * its field, dark and deep-cut so it reads from across the table. `stretch`: how much taller than wide the numerals are
 * drawn (the coin lies flat and is seen at a slant, so they read upright).
 */
export function drawTaxCoinTop(canvas: HTMLCanvasElement, tax: number, stretch = 1): void {
  const { g } = begin(canvas);
  coinFace(g, 50, 50, 48.5);
  const text = `+${tax}`;
  g.save();
  g.translate(50, 52);
  g.scale(1, stretch);
  g.textAlign = "center";
  g.textBaseline = "middle";
  const size = text.length > 2 ? 40 : 52;
  g.font = `900 ${size / Math.max(1, stretch * 0.75)}px ${FONT}, sans-serif`;
  // the cut: a highlight below and right of it, the numerals dark in the brass
  g.fillStyle = "rgba(255, 244, 214, 0.6)";
  g.fillText(text, 1.1, 1.3);
  g.fillStyle = "#3b2208";
  g.fillText(text, 0, 0);
  g.restore();
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
export const taxMedallionUrl = (tax: number): string => cachedUrl(`tax:${tax}`, (c) => drawTaxMedallion(c, tax));

/** The fonts, once loaded: images with text drawn before them (the tax) are drawn again by whoever asks. */
export function whenIconFontReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts?.load) return Promise.resolve();
  return Promise.all([document.fonts.load(`800 20px ${FONT}`), document.fonts.load(`600 15px Cinzel`)]).then(() => {
    for (const k of [...urls.keys()]) if (k.startsWith("tax:")) urls.delete(k);
  }, () => undefined);
}
