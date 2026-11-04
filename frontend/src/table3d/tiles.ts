/**
 * The arranged 3D boards' cards (table3d/arrange3d.ts): art tiles, as MTG Arena and the 2D board (game/BoardTile.tsx,
 * game/board.css) draw a permanent. The art crop large, the name on a dark bar across the top, the printed P/T on a
 * parchment plate, the frame's colour inked round the edge; a token's name in italics after a hollow coin, a
 * commander's crown and brass rim. A card without cached art shows the proxy's art window (its colours and its type's
 * icon), so the two read as the same card. The full card is a hover away (the card preview).
 *
 * One texture per distinct tile, shared by every card that shows it (six Goblin tokens: one texture), and a tile
 * canvas is a third the size of the card scan it replaces. Its badges (a changed P/T, damage, keywords, counters, ×N)
 * are a separate overlay, drawn only for a card that has some.
 */
import * as THREE from "three";
import { GLYPHS, PALETTE, proxyColours, proxyFace, type CustomProxy } from "../cards/proxy";
import { proxyFontsReady, whenProxyFontsReady } from "../cards/proxyMeasure";
import type { CardData } from "../types/cards";
import type { CardOverlay } from "./textures";

/** Tile canvas width (px); its height is 1.12 times that (game/arrange.ts TILE_RATIO). */
export const TILE_PX = 320;
const RATIO = 1.12;
const UI = '"Inter Variable", Inter, Arial, sans-serif';
const DISPLAY = "Cinzel, Georgia, serif";
const NAME_INK = "#f3ead6";
const PARCHMENT = "#ece2cb";
const INK = "#1f1a15";
const BRASS = "#e2c27a";
const PLATE = "#16110c";

/** What a tile shows (everything in its texture's key). */
export interface TileSpec {
  data: CardData | undefined;
  face: number;
  name: string;
  /** A token made without a card (its own name, type and P/T). */
  custom?: CustomProxy;
  /** The card scan to crop the art from (null: the proxy's art window). */
  art: string | null;
  token: boolean;
  commander: boolean;
  /** How its name is drawn for the view it's seen in (FLAT_LOOK when left out). */
  look?: TileLook;
}

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!];
}

function rounded(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function clip(g: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (g.measureText(text).width <= maxW) return text;
  let t = text;
  while (t.length > 1 && g.measureText(`${t}…`).width > maxW) t = t.slice(0, -1);
  return `${t.trimEnd()}…`;
}

/**
 * How a tile's name is drawn for the view it's seen in (part of its texture's key): `stretch`, drawn that much taller
 * than wide, since the table is seen at a slant and the name should read upright; `min`, the smallest it may be drawn
 * (a fraction of the tile's width), so it is never tiny on screen. A smaller tile gets one shorter line, cut short with
 * an ellipsis, rather than tiny text (the full name is a hover away).
 */
export interface TileLook {
  stretch: number;
  min: number;
}
/** Seen from above, on a tile about 200 px wide (the default). */
export const FLAT_LOOK: TileLook = { stretch: 1, min: 0.05 };
/** The name's largest size, and the smallest one line shrinks to before it splits in two (fractions of the width). */
const NAME_FULL = 0.115;
const NAME_ONE = 0.09;
/** The name's letters are drawn this narrow (a condensed face, as Arena's): more of a long name fits. */
export const NAME_CONDENSE = 0.9;
/** A line's glyphs, above its baseline (capitals, accents) and below it (descenders), in ems. */
export const NAME_ASC = 0.78;
export const NAME_DESC = 0.24;
/** The smallest a name's em may be on screen (CSS px, its height as seen): a capital stays about 7.5 px tall. */
export const NAME_MIN_SCREEN = 10;

/**
 * The look for a tile `screenW` CSS px wide in the seat view, on a table whose depth is seen foreshortened to `squash`
 * of its width there. Rounded to a few steps, so the textures don't change with every pixel of a window's resize.
 */
export function tileLook(screenW: number, squash: number): TileLook {
  const stretch = Math.min(2.2, Math.max(1, Math.round((1 / Math.max(0.3, squash)) * 5) / 5));
  // (1% steps; at 5% or less a tile is large enough for anything, two lines included)
  const min = Math.min(NAME_FULL, Math.max(0.05, Math.ceil((NAME_MIN_SCREEN / Math.max(1, screenW)) * 100) / 100));
  return { stretch, min };
}

/** The name bar's height on a tile W px wide, and the band inside it the name's lines are drawn in. */
function nameBand(W: number, look: TileLook): { bar: number; top: number; inner: number } {
  const top = Math.max(3, W * 0.03) + W * 0.015; // under the frame's ring
  const inner = W * NAME_FULL * look.stretch * (NAME_ASC + NAME_DESC);
  return { bar: top + inner + W * 0.025, top, inner };
}

/** A tile's name fitted to its bar: the lines, their size (canvas px) and each line's baseline (canvas px). */
export interface NameFit {
  lines: string[];
  px: number;
  base: number[];
}

/**
 * A tile's name, fitted to the bar: one line, shrunk as far as NAME_ONE of the width; else, when two lines would still
 * be at least `look.min`, two lines broken where they come out most even; else one line shrunk to `look.min` and then
 * cut short. Every line's glyphs lie inside the bar's band (under the frame's ring, above the bar's foot).
 */
export function fitName(g: CanvasRenderingContext2D, text: string, maxW: number, W: number, font: (px: number) => string, look: TileLook = FLAT_LOOK): NameFit {
  const { top, inner } = nameBand(W, look);
  const s = look.stretch;
  const min = Math.min(Math.round(W * NAME_FULL), Math.ceil(look.min * W));
  const fits = (t: string) => g.measureText(t).width * NAME_CONDENSE <= maxW;
  // a glyph box centred at y has its baseline this far below y
  const baseAt = (y: number, px: number) => y + ((NAME_ASC - NAME_DESC) / 2) * px * s;
  const one = (line: string, px: number): NameFit => ({ lines: [line], px, base: [baseAt(top + inner / 2, px)] });
  const full = Math.round(W * NAME_FULL);
  const floor = Math.max(min, Math.round(W * NAME_ONE));
  for (let px = full; px >= floor; px--) {
    g.font = font(px);
    if (fits(text)) return one(text, px);
  }
  // two lines, each a little under half the band, with a hairline between them
  const gap = 0.06;
  const px2 = Math.floor(inner / (s * (2 * (NAME_ASC + NAME_DESC) + gap)));
  const words = text.split(" ");
  if (words.length > 1 && px2 >= min) {
    g.font = font(px2);
    let best: [string, string, number] | null = null;
    for (let i = 1; i < words.length; i++) {
      const a = words.slice(0, i).join(" ");
      const b = words.slice(i).join(" ");
      const w = Math.max(g.measureText(a).width, g.measureText(b).width);
      if (!best || w < best[2]) best = [a, b, w];
    }
    const [a, b] = best!;
    const step = px2 * s * (NAME_ASC + NAME_DESC + gap);
    const mid = top + inner / 2;
    return { lines: [clip(g, a, maxW / NAME_CONDENSE), clip(g, b, maxW / NAME_CONDENSE)], px: px2, base: [baseAt(mid - step / 2, px2), baseAt(mid + step / 2, px2)] };
  }
  // one shorter line: shrunk as far as it may be, then cut short
  for (let px = floor - 1; px >= min; px--) {
    g.font = font(px);
    if (fits(text)) return one(text, px);
  }
  const px = Math.min(floor, Math.max(min, 1));
  g.font = font(px);
  return one(clip(g, text, maxW / NAME_CONDENSE), px);
}

const paths = new Map<string, Path2D>();
function path(d: string): Path2D {
  let p = paths.get(d);
  if (!p) paths.set(d, (p = new Path2D(d)));
  return p;
}
const CROWN = "M3.5 8l4 4 4.5-6.5 4.5 6.5 4-4-1.5 10h-14z";

/** The name bar's height and the P/T plate's box on a tile W px wide (the overlay draws a changed P/T over it). */
export function tileMetrics(W: number, look: TileLook = FLAT_LOOK): { bar: number; top: number; inner: number; pt: { x: number; y: number; w: number; h: number } } {
  const H = Math.round(W * RATIO);
  const w = W * 0.44;
  const h = W * 0.25;
  return { ...nameBand(W, look), pt: { x: W - w - W * 0.045, y: H - h - W * 0.045, w, h } };
}

function ptPlate(g: CanvasRenderingContext2D, W: number, text: string, ink: string, edge: string, arrow = ""): void {
  const { pt } = tileMetrics(W);
  g.font = `700 ${Math.round(W * 0.19)}px ${DISPLAY}`;
  const tw = g.measureText(text).width + (arrow ? W * 0.1 : 0);
  const w = Math.max(pt.w, tw + W * 0.1);
  const x = pt.x + pt.w - w;
  g.fillStyle = "rgba(0, 0, 0, 0.5)";
  rounded(g, x + 1, pt.y + 3, w, pt.h, W * 0.02);
  g.fill();
  g.fillStyle = PARCHMENT;
  rounded(g, x, pt.y, w, pt.h, W * 0.02);
  g.fill();
  g.lineWidth = Math.max(2, W * 0.008);
  g.strokeStyle = edge;
  g.stroke();
  g.fillStyle = ink;
  g.textAlign = "center";
  g.textBaseline = "middle";
  const cx = x + w / 2 + (arrow ? W * 0.04 : 0);
  g.fillText(text, cx, pt.y + pt.h / 2 + W * 0.012);
  if (arrow) {
    g.font = `800 ${Math.round(W * 0.09)}px ${UI}`;
    g.fillText(arrow, x + W * 0.075, pt.y + pt.h / 2 + W * 0.005);
  }
}

/** Draw a tile (with the art when `img` has loaded). */
function drawTile(c: HTMLCanvasElement, spec: TileSpec, img: HTMLImageElement | null): void {
  const g = c.getContext("2d")!;
  const W = c.width;
  const H = c.height;
  const p = proxyFace(spec.data, spec.face, spec.custom, spec.name);
  const colours = proxyColours(p);
  const frame = PALETTE[p.frame].frame;
  const r = W * 0.06;
  g.clearRect(0, 0, W, H);
  g.save();
  rounded(g, 0, 0, W, H, r);
  g.clip();
  if (img && img.naturalWidth) {
    // the scan cropped to its art window (modern frames: 5–55% of the card's height), as the 2D tile does
    const iw = img.naturalWidth;
    const ih = img.naturalHeight;
    g.drawImage(img, iw * 0.185, ih * 0.05, iw * 0.63, ih * 0.506, 0, 0, W, H);
  } else {
    // the proxy's art window: its colours split on a slant, and its type's icon
    const grad = g.createLinearGradient(0, H * 0.2, W, H * 0.8);
    grad.addColorStop(0, colours.field[0]);
    grad.addColorStop(0.5, colours.field[0]);
    grad.addColorStop(0.5, colours.field[1]);
    grad.addColorStop(1, colours.field[1]);
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);
    const vig = g.createRadialGradient(W / 2, H * 0.55, W * 0.2, W / 2, H * 0.55, W * 0.8);
    vig.addColorStop(0, "rgba(0, 0, 0, 0)");
    vig.addColorStop(1, "rgba(0, 0, 0, 0.35)");
    g.fillStyle = vig;
    g.fillRect(0, 0, W, H);
    const s = (H * 0.44) / 24;
    g.save();
    g.translate(W / 2 - 12 * s, H * 0.58 - 12 * s);
    g.scale(s, s);
    g.fillStyle = colours.glyphLit;
    g.translate(0, 0.7);
    g.fill(path(GLYPHS[p.kind]), "evenodd");
    g.translate(0, -0.7);
    g.fillStyle = colours.glyph;
    g.fill(path(GLYPHS[p.kind]), "evenodd");
    g.restore();
  }
  // the name, across the top on an opaque bar (the scan's own printed name, at the top of its art crop, never shows
  // through), in the frame's colour's dark ink
  const look = spec.look ?? FLAT_LOOK;
  const { bar, top, inner } = tileMetrics(W, look);
  const s = look.stretch;
  const shade = g.createLinearGradient(0, 0, 0, bar);
  shade.addColorStop(0, "#1b140e");
  shade.addColorStop(1, "#110d09");
  g.fillStyle = shade;
  g.fillRect(0, 0, W, bar);
  g.fillStyle = spec.commander ? BRASS : frame;
  g.globalAlpha = spec.commander ? 1 : 0.6;
  g.fillRect(0, bar, W, Math.max(2, W * 0.008));
  g.globalAlpha = 1;
  let x = W * 0.055;
  const cy = top + inner / 2;
  if (spec.commander) {
    // the crown, as tall as a capital (drawn tall with the name)
    const k = (W * NAME_FULL * 0.95) / 24;
    g.save();
    g.translate(x - 2 * k, cy - 13 * k * s);
    g.scale(k, k * s);
    g.fillStyle = BRASS;
    g.fill(path(CROWN));
    g.restore();
    x += W * NAME_FULL * 0.95;
  } else if (spec.token) {
    const rr = W * NAME_FULL * 0.36;
    g.beginPath();
    g.ellipse(x + rr, cy, rr, rr * s, 0, 0, Math.PI * 2);
    g.lineWidth = Math.max(2, W * 0.012);
    g.strokeStyle = "#d9d0bd";
    g.stroke();
    x += rr * 2 + W * 0.03;
  }
  const name = fitName(g, p.name || spec.name, W - x - W * 0.045, W, (px) => `${spec.token ? "italic " : ""}650 ${px}px ${UI}`, look);
  g.fillStyle = NAME_INK;
  g.textAlign = "left";
  g.textBaseline = "alphabetic";
  g.shadowColor = "rgba(0, 0, 0, 0.8)";
  g.shadowOffsetY = 1;
  // the whole name when it fits (else one line cut short), condensed and drawn tall: the table is seen at a slant, so
  // it reads upright (as the pile labels do)
  name.lines.forEach((line, i) => {
    g.save();
    g.translate(x, name.base[i]!);
    g.scale(NAME_CONDENSE, s);
    g.fillText(line, 0, 0);
    g.restore();
  });
  g.shadowColor = "transparent";
  g.shadowOffsetY = 0;
  // power and toughness on a parchment plate, as on the proxy card
  if (p.stat?.kind === "pt") ptPlate(g, W, p.stat.text, INK, "#2a2219");
  g.restore();
  // the frame: a dark edge and the card's colour inked inside it (a commander: a brass rim outside its colour)
  const ring = Math.max(3, W * 0.03);
  g.lineWidth = ring;
  g.strokeStyle = frame;
  rounded(g, ring / 2 + 1, ring / 2 + 1, W - ring - 2, H - ring - 2, r - ring / 2);
  g.stroke();
  g.lineWidth = 2;
  g.strokeStyle = spec.commander ? BRASS : "rgba(8, 6, 4, 0.9)";
  rounded(g, 1, 1, W - 2, H - 2, r);
  g.stroke();
  g.lineWidth = 1.5;
  g.strokeStyle = "rgba(8, 6, 4, 0.55)";
  rounded(g, ring + 1.5, ring + 1.5, W - ring * 2 - 3, H - ring * 2 - 3, Math.max(1, r - ring));
  g.stroke();
}

const loading = new Map<string, Promise<HTMLImageElement | null>>();
/** The card scan, once (nothing keeps it after the tiles that wanted it are drawn). */
function loadImage(url: string): Promise<HTMLImageElement | null> {
  let p = loading.get(url);
  if (!p) {
    p = new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = url;
    });
    loading.set(url, p);
    void p.then(() => loading.delete(url));
  }
  return p;
}

/**
 * A tile as a texture: drawn now (the proxy's art window while the scan loads), again when the art arrives and once
 * more if the fonts weren't ready (never per frame).
 */
export function tileTexture(spec: TileSpec, px: number, anisotropy: number): THREE.CanvasTexture {
  const [c] = canvas(px, Math.round(px * RATIO));
  let art: HTMLImageElement | null = null;
  drawTile(c, spec, null);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = anisotropy;
  if (spec.art) {
    void loadImage(spec.art).then((img) => {
      if (!img) return;
      art = img;
      drawTile(c, spec, art);
      t.needsUpdate = true;
    });
  }
  if (!proxyFontsReady()) {
    void whenProxyFontsReady().then(() => {
      drawTile(c, spec, art);
      t.needsUpdate = true;
    });
  }
  return t;
}

/** A tile's badges: a changed P/T over the printed one, damage, keywords, counters, ×N and the owner's gem. */
export function tileOverlayCanvas(o: CardOverlay, px = 256, look: TileLook = FLAT_LOOK): HTMLCanvasElement {
  const W = px;
  const H = Math.round(W * RATIO);
  const [c, g] = canvas(W, H);
  const { bar, pt } = tileMetrics(W, look);
  const chip = (x: number, y: number, w: number, h: number, edge: string) => {
    g.fillStyle = PLATE;
    rounded(g, x, y, w, h, h * 0.3);
    g.fill();
    g.strokeStyle = edge;
    g.lineWidth = Math.max(2, W * 0.012);
    g.stroke();
  };
  g.textBaseline = "middle";
  g.textAlign = "center";
  let left = bar + W * 0.04;
  // ×N, at the left under the name bar, where a stack's edges are
  if (o.pile) {
    g.font = `800 ${Math.round(W * 0.13)}px ${UI}`;
    const text = `×${o.pile}`;
    const w = g.measureText(text).width + W * 0.09;
    const h = W * 0.19;
    chip(W * 0.04, left, w, h, BRASS);
    g.fillStyle = NAME_INK;
    g.fillText(text, W * 0.04 + w / 2, left + h / 2 + 1);
    left += h + W * 0.03;
  }
  if (o.owner) {
    const rr = W * 0.075;
    g.beginPath();
    g.arc(W * 0.04 + rr, left + rr, rr, 0, Math.PI * 2);
    g.fillStyle = o.owner.color;
    g.fill();
    g.lineWidth = Math.max(2, W * 0.015);
    g.strokeStyle = PLATE;
    g.stroke();
    g.fillStyle = "#0e0b08";
    g.font = `800 ${Math.round(W * 0.09)}px ${UI}`;
    g.fillText(o.owner.initial, W * 0.04 + rr, left + rr + 1);
  }
  // other counters, top right under the name bar (as many as fit above the P/T plate)
  const room = Math.max(1, Math.floor((pt.y - bar - W * 0.04) / (W * 0.185)));
  o.counters.slice(0, Math.min(3, room)).forEach(({ label, n }, i) => {
    g.font = `800 ${Math.round(W * 0.11)}px ${UI}`;
    const text = `${label} ${n}`;
    const w = Math.min(W * 0.6, g.measureText(text).width + W * 0.08);
    const h = W * 0.16;
    const x = W - w - W * 0.04;
    const y = bar + W * 0.04 + i * (h + W * 0.025);
    chip(x, y, w, h, BRASS);
    g.fillStyle = NAME_INK;
    g.fillText(clip(g, text, w - W * 0.04), x + w / 2, y + h / 2 + 1);
  });
  if (o.pt) {
    const up = o.pt.dir > 0;
    const down = o.pt.dir < 0;
    ptPlate(g, W, o.pt.text, up ? "#155228" : down ? "#8c1f17" : INK, up ? "#2f8a52" : down ? "#b33c32" : "#2a2219", up ? "▲" : down ? "▼" : "");
  }
  if (o.damage) {
    g.font = `800 ${Math.round(W * 0.12)}px ${UI}`;
    const text = `${o.damage} dmg`;
    const w = g.measureText(text).width + W * 0.1;
    const h = W * 0.17;
    const x = pt.x + pt.w - w;
    const y = pt.y - h - W * 0.03;
    chip(x, y, w, h, "#e0574a");
    g.fillStyle = "#ffb3a8";
    g.fillText(text, x + w / 2, y + h / 2 + 1);
  }
  // keywords from counters or effects: initials on small coins along the bottom left (at most 3, then +N)
  const kw = o.keywords;
  const shown = kw.slice(0, kw.length > 3 ? 2 : 3);
  const R = W * 0.075;
  shown.forEach(({ kind, n }, i) => {
    const cx = W * 0.05 + R + i * (R * 2 + W * 0.02);
    const cy = H - W * 0.05 - R;
    g.beginPath();
    g.arc(cx, cy, R, 0, Math.PI * 2);
    g.fillStyle = PLATE;
    g.fill();
    g.strokeStyle = BRASS;
    g.lineWidth = Math.max(2, W * 0.01);
    g.stroke();
    g.fillStyle = NAME_INK;
    g.font = `800 ${Math.round(R * (n > 1 ? 0.8 : 1))}px ${UI}`;
    g.fillText(`${kind.slice(0, 2).replace(/^./, (ch) => ch.toUpperCase())}${n > 1 ? n : ""}`, cx, cy + 1);
  });
  if (kw.length > shown.length) {
    const cx = W * 0.05 + R + shown.length * (R * 2 + W * 0.02);
    const cy = H - W * 0.05 - R;
    chip(cx - R, cy - R * 0.7, R * 2, R * 1.4, BRASS);
    g.fillStyle = NAME_INK;
    g.font = `800 ${Math.round(R * 0.85)}px ${UI}`;
    g.fillText(`+${kw.length - shown.length}`, cx, cy + 1);
  }
  return c;
}
