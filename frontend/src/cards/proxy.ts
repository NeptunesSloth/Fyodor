/**
 * The printed proxy drawn for a card whose art isn't cached: one model shared by the DOM card
 * (CardFace's TextCard) and the 3D table's canvas texture (table3d/textures.ts), so both draw the
 * same card. Everything is measured in card units: the card is 100 wide and CARD_H tall (63 × 88 mm),
 * which the DOM maps to `cqw` and the canvas to pixels, so a fit computed once holds at every size.
 */
import type { CardData } from "../types/cards";

export const CARD_H = (88 / 63) * 100;

// ------------------------------------------------------------------ what the card says

export type FrameKey = "W" | "U" | "B" | "R" | "G" | "M" | "A" | "C" | "L";
export type GlyphKind = "creature" | "planeswalker" | "battle" | "land" | "instant" | "sorcery" | "artifact" | "enchantment" | "other";

export interface ProxyFace {
  name: string;
  cost: string;
  type: string;
  text: string;
  /** "4/4", a loyalty or a defense, and which of the three it is. */
  stat: { text: string; kind: "pt" | "loyalty" | "defense" } | null;
  frame: FrameKey;
  /** The colours the art window shows: a land's basic types / identity, otherwise the card's colours. */
  field: string[];
  kind: GlyphKind;
}

export interface CustomProxy {
  name: string;
  type_line?: string | null;
  oracle_text?: string | null;
  power?: string | null;
  toughness?: string | null;
  colors?: string[] | null;
}

const COLOURS = ["W", "U", "B", "R", "G"];
const BASICS: Record<string, string> = { Plains: "W", Island: "U", Swamp: "B", Mountain: "R", Forest: "G" };

function wubrg(cs: readonly string[] | null | undefined): string[] {
  const set = new Set((cs ?? []).map((c) => c.toUpperCase()));
  return COLOURS.filter((c) => set.has(c));
}

/** The frame a printed card of this type and colour has: a colour, gold for two or more, artifact, colourless or land. */
export function frameKey(type: string, colors: readonly string[] | null | undefined): FrameKey {
  if (/\bLand\b/.test(type)) return "L";
  const cs = wubrg(colors);
  if (cs.length > 1) return "M";
  if (cs.length === 1) return cs[0] as FrameKey;
  return /\bArtifact\b/.test(type) ? "A" : "C";
}

/** Which icon stands for the card in its art window (the most telling of its types). */
export function glyphKind(type: string): GlyphKind {
  const t = type.split(/\s+[—–-]\s+|\s\/\/\s/)[0] ?? type; // the card types, not the subtypes
  if (/\bPlaneswalker\b/.test(t)) return "planeswalker";
  if (/\bBattle\b/.test(t)) return "battle";
  if (/\bCreature\b/.test(t)) return "creature";
  if (/\bLand\b/.test(t)) return "land";
  if (/\bInstant\b/.test(t)) return "instant";
  if (/\bSorcery\b/.test(t)) return "sorcery";
  if (/\bArtifact\b/.test(t)) return "artifact";
  if (/\bEnchantment\b/.test(t)) return "enchantment";
  return "other";
}

/** The colours shown in the art window. A land shows what it makes (its basic types, else its colour identity). */
export function fieldColours(type: string, colors: readonly string[] | null | undefined, identity?: readonly string[] | null): string[] {
  if (/\bLand\b/.test(type)) {
    const basics = [...type.matchAll(/\b(Plains|Island|Swamp|Mountain|Forest)\b/g)].map((m) => BASICS[m[1]!]!);
    return wubrg(basics.length ? basics : identity ?? colors);
  }
  return wubrg(colors);
}

/** Everything a proxy prints for one face of a card (a double-faced card's face; a split card's halves together). */
export function proxyFace(card: CardData | undefined, face = 0, custom?: CustomProxy, fallbackName = ""): ProxyFace {
  const f = card?.faces?.length ? card.faces[Math.min(face, card.faces.length - 1)] : undefined;
  // a double-faced card prints one face; a split / adventure card prints all its halves on one card
  const own = card?.double_faced ? f : undefined;
  const halves = card && !card.double_faced && !card.oracle_text && (card.faces?.length ?? 0) > 1 ? card.faces : null;
  const name = own?.name ?? card?.name ?? custom?.name ?? fallbackName;
  const cost = (own ? own.mana_cost : card?.mana_cost) ?? "";
  const type = own?.type_line ?? card?.type_line ?? custom?.type_line ?? "";
  const text = halves
    ? halves.map((h) => `${h.name}${h.mana_cost ? ` ${h.mana_cost}` : ""}\n${h.oracle_text ?? ""}`.trim()).join("\n")
    : own?.oracle_text ?? card?.oracle_text ?? custom?.oracle_text ?? "";
  const power = own ? own.power : card?.power ?? custom?.power;
  const toughness = own ? own.toughness : card?.toughness ?? custom?.toughness;
  const loyalty = own ? own.loyalty : card?.loyalty;
  const defense = own ? own.defense : card?.defense;
  const colors = own?.colors ?? card?.colors ?? custom?.colors ?? [];
  const stat: ProxyFace["stat"] = power != null && toughness != null ? { text: `${power}/${toughness}`, kind: "pt" }
    : loyalty != null ? { text: loyalty, kind: "loyalty" }
    : defense != null ? { text: defense, kind: "defense" } : null;
  return { name, cost, type, text, stat, frame: frameKey(type, colors), field: fieldColours(type, colors, card?.color_identity), kind: glyphKind(type) };
}

// ------------------------------------------------------------------ colour

/** Frame inks: matte, a little desaturated, so a proxy sits on the dark table without shouting. */
export const PALETTE: Record<FrameKey, { frame: string; dark: string; field: string }> = {
  W: { frame: "#d9d2bf", dark: "#8b826a", field: "#bbb196" },
  U: { frame: "#31618f", dark: "#183450", field: "#3f709e" },
  B: { frame: "#3d3736", dark: "#141110", field: "#55494a" },
  R: { frame: "#a5472d", dark: "#5a2011", field: "#b85a3a" },
  G: { frame: "#3f6c48", dark: "#1b3822", field: "#517f57" },
  M: { frame: "#c29a47", dark: "#6c4f17", field: "#cba556" },
  A: { frame: "#8b9095", dark: "#454a50", field: "#7b8289" },
  C: { frame: "#a29b91", dark: "#57524b", field: "#8d867c" },
  L: { frame: "#8a7156", dark: "#463625", field: "#9b8468" },
};
export const PAPER = "#f3ecdc";
export const INK = "#1f1a15";
export const BORDER = "#171310";

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function hex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("")}`;
}
/** `a` mixed with `t` of `b`. */
export function mix(a: string, b: string, t: number): string {
  const x = rgb(a);
  const y = rgb(b);
  return hex([x[0] + (y[0] - x[0]) * t, x[1] + (y[1] - x[1]) * t, x[2] + (y[2] - x[2]) * t]);
}
/** Relative luminance (WCAG), 0 … 1. */
export function luminance(c: string): number {
  const lin = (v: number) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = rgb(c);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export interface ProxyColours {
  frame: string; dark: string; bar: string; paper: string;
  /** The art window: one tone, or two halves for a two-colour card. */
  field: [string, string];
  /** The debossed icon and its lit lower edge. */
  glyph: string; glyphLit: string;
}

export function proxyColours(p: Pick<ProxyFace, "frame" | "field">): ProxyColours {
  const base = PALETTE[p.frame];
  const tone = (c: string) => (PALETTE[c as FrameKey] ?? base).field;
  const field: [string, string] = p.field.length === 1 ? [tone(p.field[0]!), tone(p.field[0]!)]
    : p.field.length === 2 ? [tone(p.field[0]!), tone(p.field[1]!)]
    : p.field.length > 2 ? [PALETTE.M.field, PALETTE.M.field]
    : [base.field, base.field];
  const mid = mix(field[0], field[1], 0.5);
  const dark = luminance(mid) < 0.09;
  return {
    frame: base.frame, dark: base.dark,
    bar: mix(PAPER, base.frame, 0.26), paper: mix(PAPER, base.frame, 0.14),
    field,
    glyph: dark ? mix(mid, "#000000", 0.42) : mix(mid, "#000000", 0.3),
    glyphLit: mix(mid, "#ffffff", dark ? 0.16 : 0.24),
  };
}

// ------------------------------------------------------------------ type icons (24 × 24 SVG paths, shared with the canvas via Path2D)

function slash(dx: number, dy: number, len: number): string {
  const p = (x: number, y: number) => `${(x + dx).toFixed(2)} ${(y * len + dy).toFixed(2)}`;
  return `M${p(9.4, 0)} C${p(11.4, 0.32)} ${p(10.2, 0.72)} ${p(4.6, 1)} C${p(7.4, 0.68)} ${p(8.4, 0.34)} ${p(9.4, 0)}Z`;
}

function gear(teeth: number, rOut: number, rIn: number, hole: number): string {
  const pts: string[] = [];
  const step = (Math.PI * 2) / teeth;
  for (let i = 0; i < teeth; i++) {
    const a = i * step - Math.PI / 2;
    for (const [da, r] of [[-0.3, rIn], [-0.17, rOut], [0.17, rOut], [0.3, rIn]] as const) {
      pts.push(`${(12 + Math.cos(a + da * step * 1.6) * r).toFixed(2)} ${(12 + Math.sin(a + da * step * 1.6) * r).toFixed(2)}`);
    }
  }
  const ring = `M${pts.join(" L")}Z`;
  const h = `M${12 + hole} 12 A${hole} ${hole} 0 1 0 ${12 - hole} 12 A${hole} ${hole} 0 1 0 ${12 + hole} 12Z`;
  return `${ring} ${h}`;
}

/** Each icon is one even-odd path in a 24 × 24 box. */
export const GLYPHS: Record<GlyphKind, string> = {
  // three claw marks
  creature: [slash(-1.6, 3.4, 17.4), slash(3.4, 2.2, 19.6), slash(8.4, 3.4, 17.4)].join(" "),
  // the planeswalker's spark: a spire between two rising arcs
  planeswalker: "M12 1.4 L14.7 9 L13.5 22.4 H10.5 L9.3 9Z M2.6 4.6 C3.4 12.6 6.9 16.8 10.3 17.4 L10.1 13.9 C7.5 13.1 4.6 10.2 2.6 4.6Z M21.4 4.6 C20.6 12.6 17.1 16.8 13.7 17.4 L13.9 13.9 C16.5 13.1 19.4 10.2 21.4 4.6Z",
  // a shield with a notch
  battle: "M12 1.8 L20.6 5 C20.6 13.2 17.2 18.8 12 22.2 C6.8 18.8 3.4 13.2 3.4 5Z M12 6.2 L15.8 12 L12 17.8 L8.2 12Z",
  // two peaks
  land: "M1.4 20.6 L8.9 6.4 L12.7 13.4 L15.7 8.8 L22.6 20.6Z M8.9 9.6 L6.8 13.6 L8.9 12.4 L10.7 13.3Z",
  // a lightning bolt
  instant: "M13.8 1.4 L4.4 13.6 H11 L9.4 22.6 L19.6 9.6 H12.9Z",
  // a flame
  sorcery: "M12 1.6 C12.7 6 18 8.7 18 14.8 C18 19 15.3 22.4 12 22.4 C8.7 22.4 6 19.6 6 15.7 C6 12.6 7.7 10.5 9.4 9.3 C9.3 11.6 10.3 13 11.5 13.7 C10.4 9.6 11.2 5.3 12 1.6Z M12 15.2 C13.6 16.4 14.4 17.7 14 19.2 C13.7 20.3 12.9 21 12 21 C11.1 21 10.3 20.3 10 19.2 C9.6 17.7 10.4 16.4 12 15.2Z",
  // a gear
  artifact: gear(8, 10.6, 7.9, 3.4),
  // a four-point star and a small one
  enchantment: "M11 2 C11.7 8 14.6 10.9 20.6 11.6 C14.6 12.3 11.7 15.2 11 21.2 C10.3 15.2 7.4 12.3 1.4 11.6 C7.4 10.9 10.3 8 11 2Z M19 1.6 C19.3 3.7 20.3 4.7 22.4 5 C20.3 5.3 19.3 6.3 19 8.4 C18.7 6.3 17.7 5.3 15.6 5 C17.7 4.7 18.7 3.7 19 1.6Z",
  // a plain lozenge
  other: "M12 2.6 L20.4 12 L12 21.4 L3.6 12Z M12 7.4 L16.2 12 L12 16.6 L7.8 12Z",
};

// ------------------------------------------------------------------ text: tokens, wrapping, fitting

export type Token = { t: "word"; s: string; rem: boolean } | { t: "sym"; s: string; rem: boolean } | { t: "space"; rem: boolean };

/** Splits one paragraph into words, spaces and `{X}` symbols; text inside (…) is reminder text. */
export function tokenize(line: string): Token[] {
  const out: Token[] = [];
  let depth = 0;
  for (const part of line.split(/(\{[^}]+\}|\s+)/)) {
    if (!part) continue;
    if (/^\s+$/.test(part)) { out.push({ t: "space", rem: depth > 0 }); continue; }
    if (/^\{[^}]+\}$/.test(part)) { out.push({ t: "sym", s: part.slice(1, -1), rem: depth > 0 }); continue; }
    // a word belongs to reminder text if it opens, is inside, or closes a parenthesis
    const opens = (part.match(/\(/g) ?? []).length;
    const closes = (part.match(/\)/g) ?? []).length;
    const rem = depth > 0 || opens > 0;
    depth = Math.max(0, depth + opens - closes);
    out.push({ t: "word", s: part, rem });
  }
  return out;
}

/** Removes reminder text, the first thing a crowded proxy gives up. */
export function stripReminders(text: string): string {
  return text.split("\n").map((l) => l.replace(/\s*\([^()]*\)/g, "").trim()).filter(Boolean).join("\n");
}

export type FontRole = "name" | "type" | "text" | "stat";
/** Width of `s` in ems for a font role. */
export type Measure = (s: string, role: FontRole) => number;

/** Mana symbols are 1.15em circles at 0.82 of the text size, with a hair of space either side. */
export const SYM_EM = 0.82 * 1.15 + 0.1;

/** A width table close to Inter / Cinzel Bold, for tests and for the first paint before the fonts load. */
export const estimateMeasure: Measure = (s, role) => {
  let w = 0;
  const caps = role === "name" || role === "stat";
  for (const ch of s) {
    if (ch === " ") w += caps ? 0.26 : 0.27;
    else if (/[0-9]/.test(ch)) w += caps ? 0.62 : 0.6;
    else if (/[A-Z]/.test(ch)) w += caps ? 0.8 : 0.68;
    else if (/[a-z]/.test(ch)) w += caps ? 0.64 : /[iljt]/.test(ch) ? 0.3 : /[mw]/.test(ch) ? 0.82 : 0.55;
    else w += 0.32;
  }
  return w * (role === "type" ? 1.02 : 1);
};

export interface Line { tokens: Token[]; width: number }

/**
 * Greedy word wrap of one paragraph at `size` (units), where line i may be `widths[i]` wide (the last
 * width repeats), e.g. a name's first line runs beside the mana cost.
 */
export function wrap(tokens: Token[], size: number, widths: number[], measure: Measure, role: FontRole = "text"): Line[] {
  const lines: Line[] = [];
  let cur: Token[] = [];
  let w = 0;
  let pendingSpace = 0;
  const space = measure(" ", role) * size;
  const room = () => widths[Math.min(lines.length, widths.length - 1)]!;
  for (const tok of tokens) {
    if (tok.t === "space") { if (cur.length) pendingSpace = space; continue; }
    const tw = (tok.t === "sym" ? SYM_EM : measure(tok.s, role)) * size;
    if (cur.length && w + pendingSpace + tw > room()) {
      lines.push({ tokens: cur, width: w });
      cur = [];
      w = 0;
      pendingSpace = 0;
    }
    if (cur.length && pendingSpace) { cur.push({ t: "space", rem: tok.rem }); w += pendingSpace; }
    cur.push(tok);
    w += tw;
    pendingSpace = 0;
  }
  if (cur.length) lines.push({ tokens: cur, width: w });
  return lines;
}

export interface TextFit { size: number; box: number; lines: Line[][]; fits: boolean; reminders: boolean }

export interface TextBox {
  /** Inner width for text (units). */
  width: number;
  /** The text box's usual height, and the most it may grow into the art window. */
  base: number;
  max: number;
  /** Padding above and below the text inside the box, and what the P/T plate covers at its foot. */
  padY: number;
  foot: number;
  /** Largest, comfortable and smallest text size; line height; paragraph gap (ems). */
  sizes: { max: number; comfort: number; min: number };
  lh: number;
  gap: number;
}

/** Height of wrapped paragraphs (units). */
export function textHeight(paras: Line[][], size: number, lh: number, gap: number): number {
  const n = paras.reduce((s, p) => s + Math.max(1, p.length), 0);
  return n * size * lh + Math.max(0, paras.length - 1) * size * gap;
}

/**
 * Chooses the rules text size and the text box height: the largest size that fits the usual box; below
 * the comfortable size the box grows into the art window instead; then reminder text goes; then it
 * shrinks to the minimum and the overflow fades out.
 */
export function fitText(text: string, box: TextBox, measureRaw: Measure): TextFit {
  const measure = memoMeasure(measureRaw);
  const sizes = steps(box.sizes.max, box.sizes.min);
  const attempt = (src: string, reminders: boolean): TextFit | null => {
    const paras = src.split("\n").filter((p) => p.trim()).map(tokenize);
    const at = new Map<number, { lines: Line[][]; need: number }>();
    const get = (s: number) => {
      let r = at.get(s);
      if (!r) {
        const lines = paras.map((p) => wrap(p, s, [box.width], measure));
        at.set(s, (r = { lines, need: textHeight(lines, s, box.lh, box.gap) + box.padY * 2 + box.foot }));
      }
      return r;
    };
    // the largest size that fits the usual box; below the comfortable size the box may grow instead
    const s1 = largest(sizes, (s) => get(s).need <= box.base);
    if (s1 !== null && s1 > box.sizes.comfort + 1e-6) return { size: s1, box: box.base, lines: get(s1).lines, fits: true, reminders };
    const s2 = largest(sizes.filter((s) => s <= box.sizes.comfort + 1e-6), (s) => get(s).need <= box.max);
    if (s2 === null) return null;
    const { lines, need } = get(s2);
    return { size: s2, box: Math.max(box.base, Math.ceil(need * 10) / 10), lines, fits: true, reminders };
  };
  const full = attempt(text, true);
  if (full) return full;
  const bare = stripReminders(text);
  const short = bare !== text ? attempt(bare, false) : null;
  if (short) return short;
  const paras = bare.split("\n").filter((p) => p.trim()).map(tokenize);
  return { size: box.sizes.min, box: box.max, lines: paras.map((p) => wrap(p, box.sizes.min, [box.width], measure)), fits: false, reminders: false };
}

/** The largest size (down to `min`) at which a one-paragraph label fits in `lines` lines; `fits` false means it is clipped. */
export function fitLabel(text: string, widths: number[], lines: number, max: number, min: number, measureRaw: Measure, role: FontRole): { size: number; lines: Line[]; fits: boolean } {
  const measure = memoMeasure(measureRaw);
  const tokens = tokenize(text).map((t) => (t.t === "word" ? { ...t, rem: false } : t));
  const at = (s: number) => wrap(tokens, s, widths, measure, role);
  const ok = (out: Line[]) => out.length <= lines && out.every((l, i) => l.width <= widths[Math.min(i, widths.length - 1)]! + 1e-6);
  const s = largest(steps(max, min), (x) => ok(at(x)));
  return s === null ? { size: min, lines: at(min), fits: false } : { size: s, lines: at(s), fits: true };
}

/** Sizes from `max` down to `min` in 0.1 steps. */
function steps(max: number, min: number): number[] {
  const out: number[] = [];
  for (let s = max; s >= min - 1e-6; s = Math.round((s - 0.1) * 100) / 100) out.push(s);
  return out;
}

/** The first (largest) of `sizes` that passes `ok`, by bisection: whatever fits at one size fits at every smaller one. */
function largest(sizes: number[], ok: (s: number) => boolean): number | null {
  let lo = 0;
  let hi = sizes.length; // sizes[hi] is the first known to pass
  if (!sizes.length || !ok(sizes[sizes.length - 1]!)) return null;
  hi = sizes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (ok(sizes[mid]!)) hi = mid;
    else lo = mid + 1;
  }
  return sizes[hi]!;
}

/** A measure that remembers each word it has measured (one fit measures the same words at many sizes). */
function memoMeasure(m: Measure): Measure {
  const seen = new Map<string, number>();
  return (s, role) => {
    const k = `${role}\u0000${s}`;
    let w = seen.get(k);
    if (w === undefined) seen.set(k, (w = m(s, role)));
    return w;
  };
}

// ------------------------------------------------------------------ layout

/**
 * The proxy's geometry at one level of detail (units; card = 100 × CARD_H). "full" is the large card
 * (inspect, deck preview, card browser), "small" the hand / deck tile size and the 3D table texture.
 * The tiny level (battlefield, thumbnails) keeps only the name, the icon and the P/T (CSS only).
 */
export interface Tier {
  border: number; pad: number; gap: number;
  /** A one-line name shrinks to `shrink` before it may wrap (up to `lines`) and shrink on to `min`. */
  name: { max: number; shrink: number; min: number; lines: number; lh: number; padX: number; padY: number };
  type: { max: number; min: number; h: number };
  text: { padX: number; padY: number; base: number; minField: number; sizes: TextBox["sizes"]; lh: number; gap: number };
  /** Frame below the text box (where the P/T plate overhangs). */
  bottom: number;
  stat: { w: number; h: number; size: number; inset: number };
}

export const TIERS: Record<"full" | "small", Tier> = {
  full: {
    border: 3.6, pad: 2.6, gap: 1.4,
    name: { max: 6.4, shrink: 5.2, min: 4.6, lines: 2, lh: 1.12, padX: 2.4, padY: 2 },
    type: { max: 5, min: 3.7, h: 8.2 },
    text: { padX: 3, padY: 2.4, base: 50, minField: 24, sizes: { max: 5.4, comfort: 4.5, min: 3.5 }, lh: 1.3, gap: 0.32 },
    bottom: 5.4,
    stat: { w: 22, h: 9.6, size: 6.2, inset: 1.4 },
  },
  small: {
    border: 3.8, pad: 2.4, gap: 1.4,
    name: { max: 8.4, shrink: 8.4, min: 6.2, lines: 2, lh: 1.06, padX: 2.2, padY: 1.9 },
    type: { max: 6.2, min: 4.8, h: 9.6 },
    text: { padX: 2.6, padY: 2, base: 40, minField: 30, sizes: { max: 6.6, comfort: 5.8, min: 5.2 }, lh: 1.18, gap: 0.25 },
    bottom: 5.2,
    stat: { w: 27, h: 12, size: 8.6, inset: 1.2 },
  },
};

/**
 * The 3D table's texture, mostly seen ~60px wide from the seat camera: the small tier with a bigger name
 * and art window, and a tighter text box whose text may shrink further (a focused card is seen up close;
 * the hover preview has the full text).
 */
export const CANVAS_TIER: Tier = {
  ...TIERS.small,
  name: { ...TIERS.small.name, max: 9, shrink: 9 },
  text: { ...TIERS.small.text, base: 32, minField: 36, sizes: { max: 5.6, comfort: 4.6, min: 3.8 } },
};

export interface ProxyLayout {
  name: { size: number; lines: Line[]; fits: boolean; barH: number };
  type: { size: number; fits: boolean };
  text: TextFit;
  /** Top of the art window and its height (units). */
  field: { top: number; h: number };
  inner: { x: number; w: number };
}

/** Width the mana cost takes on the name line (units). */
export function costWidth(cost: string, size: number): number {
  const n = (cost.match(/\{[^}]+\}/g) ?? []).length;
  const rest = cost.replace(/\{[^}]+\}/g, "").replace(/\s+/g, " ").length; // a split card's " // "
  return n || rest ? (n * SYM_EM + rest * 0.42) * size + size * 0.3 : 0;
}

/** Lays out a proxy at one tier: name and type sizes, rules text fit, and the art window between them. */
export function layoutProxy(p: ProxyFace, tier: Tier, measure: Measure): ProxyLayout {
  const x = tier.border + tier.pad;
  const w = 100 - x * 2;
  const nameW = w - tier.name.padX * 2;
  // the name's first line runs beside the cost; a second line has the full width
  const m = memoMeasure(measure);
  const nameAt = (s: number, lines: number) => fitLabel(p.name, [nameW - costWidth(p.cost, s), nameW], lines, s, s, m, "name");
  const one = largest(steps(tier.name.max, tier.name.shrink), (s) => nameAt(s, 1).fits);
  const wrapped = one === null ? largest(steps(tier.name.max, tier.name.min), (s) => nameAt(s, tier.name.lines).fits) : null;
  const name = one !== null ? nameAt(one, 1) : wrapped !== null ? nameAt(wrapped, tier.name.lines) : nameAt(tier.name.min, tier.name.lines);
  const barH = Math.max(1, Math.min(name.lines.length, tier.name.lines)) * name.size * tier.name.lh + tier.name.padY * 2;
  const type = fitLabel(p.type, [w - tier.name.padX * 2], 1, tier.type.max, tier.type.min, m, "type");
  const top = tier.border + tier.pad;
  const textBottom = CARD_H - tier.border - tier.bottom;
  const fieldTop = top + barH + tier.gap;
  const fieldAt = (box: number) => textBottom - box - tier.gap - tier.type.h - tier.gap - fieldTop;
  // a card without rules text (a vanilla creature, a token) gives the art window the room
  const base = p.text.trim() ? tier.text.base : Math.round(tier.text.base * 0.4);
  const box: TextBox = {
    width: w - tier.text.padX * 2, base, max: base + Math.max(0, fieldAt(base) - tier.text.minField),
    padY: tier.text.padY, foot: p.stat ? tier.stat.h - tier.bottom + tier.stat.inset : 0,
    sizes: tier.text.sizes, lh: tier.text.lh, gap: tier.text.gap,
  };
  const text = p.text.trim() ? fitText(p.text, box, m) : { size: tier.text.sizes.max, box: base, lines: [], fits: true, reminders: true };
  return { name: { ...name, barH }, type, text, field: { top: fieldTop, h: fieldAt(text.box) }, inner: { x, w } };
}
