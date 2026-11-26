/**
 * Procedural textures, drawn on canvases: table surfaces for each plane, card fronts for cards
 * without a cached image (a readable text card), card backs / sleeves, and small labels.
 * Nothing is downloaded; everything is cached and disposed with the scene.
 */
import * as THREE from "three";
import type { Surface } from "../theme/planes";
import { BORDER, CARD_H, CANVAS_TIER, GLYPHS as TYPE_GLYPHS, INK, layoutProxy, proxyColours, proxyFace, SYM_EM } from "../cards/proxy";
import { drawnBackCanvas } from "../cards/drawnBack";
import { proxyFontsReady, textMeasure, whenProxyFontsReady } from "../cards/proxyMeasure";
import type { CardData } from "../types/cards";
import { countText } from "../game/piles";

/** Small deterministic PRNG so every table looks the same on every device. */
export function rng(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!];
}

let maxAnisotropy = 8;
/** The renderer's real limit (set once the WebGL context exists). */
export function setMaxAnisotropy(n: number): void {
  maxAnisotropy = Math.max(1, n);
}

function texture(c: HTMLCanvasElement, repeat = 1): THREE.CanvasTexture {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = maxAnisotropy;
  if (repeat !== 1) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repeat, repeat);
  }
  return t;
}

/** A smooth value-noise field in [0,1], for grain and veins. */
function noiseField(size: number, cells: number, rand: () => number): (x: number, y: number) => number {
  const g: number[] = [];
  for (let i = 0; i < (cells + 1) * (cells + 1); i++) g.push(rand());
  const at = (i: number, j: number) => g[((j % (cells + 1)) * (cells + 1)) + (i % (cells + 1))]!;
  const smooth = (t: number) => t * t * (3 - 2 * t);
  return (x, y) => {
    const fx = (x / size) * cells;
    const fy = (y / size) * cells;
    const i = Math.floor(fx);
    const j = Math.floor(fy);
    const tx = smooth(fx - i);
    const ty = smooth(fy - j);
    const a = at(i, j) + (at(i + 1, j) - at(i, j)) * tx;
    const b = at(i, j + 1) + (at(i + 1, j + 1) - at(i, j + 1)) * tx;
    return a + (b - a) * ty;
  };
}

const hex = (c: string) => new THREE.Color(c);

export interface SurfaceMaps { map: THREE.CanvasTexture; normalMap: THREE.CanvasTexture; roughnessMap: THREE.CanvasTexture }

const surfaceCache = new Map<string, { color: HTMLCanvasElement; normal: HTMLCanvasElement; rough: HTMLCanvasElement }>();

/**
 * Linear values written as if they were sRGB: this deepens every plane's surface colours (the tables
 * have always been tuned this way, and the brief wants a dark table that recedes behind the cards).
 */
const deep = (c: number) => Math.round(255 * Math.max(0, Math.min(1, c)));

/**
 * The table top for a plane (wood, marble, slate, stone…) as colour, normal and roughness maps from
 * one height field: dark grain sits slightly recessed, plank seams and tile joints are grooves, and
 * the raised grain is a touch glossier, so the surface catches the key light. Generated once per
 * plane and kept for later rebuilds.
 */
export function surfaceMaps(kind: Surface, base: string, grain: string, baseRoughness: number, seed = 7): SurfaceMaps {
  const key = `${kind}|${base}|${grain}|${baseRoughness}|${seed}`;
  let canvases = surfaceCache.get(key);
  if (!canvases) {
    canvases = drawSurface(kind, base, grain, baseRoughness, seed);
    surfaceCache.set(key, canvases);
  }
  const map = texture(canvases.color);
  const normalMap = texture(canvases.normal);
  normalMap.colorSpace = THREE.NoColorSpace;
  const roughnessMap = texture(canvases.rough);
  roughnessMap.colorSpace = THREE.NoColorSpace;
  return { map, normalMap, roughnessMap };
}

function drawSurface(kind: Surface, base: string, grain: string, baseRoughness: number, seed: number) {
  const size = 1024;
  const [c, g] = canvas(size, size);
  const rand = rng(seed);
  const A = hex(base);
  const B = hex(grain);
  const n1 = noiseField(size, 6, rand);
  const n2 = noiseField(size, 24, rand);
  const img = g.createImageData(size, size);
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let t: number;
      let groove = 0;
      switch (kind) {
        case "oak":
        case "weathered":
        case "lacquer": {
          // long planks with flowing grain lines
          // wide boards with slow, low-contrast figure: fine grain reads as moiré at a distance
          const plank = Math.floor(y / 256);
          const warp = n1(x, y + plank * 97) * 30;
          const line = Math.sin((y + warp) * 0.11 + plank * 3.1) * 0.5 + 0.5;
          const seam = y % 256 < 2;
          t = 0.22 * line + 0.4 * n2(x * 0.12, y * 1.6) + 0.12 * n1(x * 3, y * 3) + (seam ? 0.45 : 0);
          groove = seam ? 1 : 0;
          if (kind === "weathered") t += (n2(x * 1.5, y * 1.5) - 0.5) * 0.35;
          if (kind === "lacquer") t = t * 0.35 + 0.15;
          break;
        }
        case "marble": {
          const v = Math.abs(Math.sin((x * 0.006 + y * 0.002) + n1(x, y) * 4.5));
          t = 0.1 + Math.pow(1 - v, 16) * 0.45 + n2(x, y) * 0.12;
          break;
        }
        case "slate":
        case "oilmetal": {
          const tile = (x % 256 < 2 || y % 256 < 2) ? 1 : 0;
          t = 0.25 + n2(x, y) * 0.35 + n1(x, y) * 0.25 + tile * 0.6;
          groove = tile;
          if (kind === "oilmetal") t = 0.2 + n1(x * 2, y * 2) * 0.45 + tile * 0.4;
          break;
        }
        case "sandstone": {
          const band = Math.sin(y * 0.05 + n1(x, y) * 5) * 0.5 + 0.5;
          t = 0.25 + band * 0.3 + n2(x, y) * 0.3;
          break;
        }
        default: {
          // stone / jungle / meadow: cracked flagstones with soft variation
          const cellX = Math.floor((x + n1(x, y) * 40) / 200);
          const cellY = Math.floor((y + n1(y, x) * 40) / 200);
          const edge = ((x + n1(x, y) * 40) % 200 < 4 || (y + n1(y, x) * 40) % 200 < 4) ? 0.8 : 0;
          t = 0.2 + ((cellX * 13 + cellY * 7) % 5) * 0.05 + n2(x, y) * 0.35 + edge;
          groove = edge ? 1 : 0;
        }
      }
      const k = Math.max(0, Math.min(1, t));
      const i = (y * size + x) * 4;
      img.data[i] = deep(A.r + (B.r - A.r) * k);
      img.data[i + 1] = deep(A.g + (B.g - A.g) * k);
      img.data[i + 2] = deep(A.b + (B.b - A.b) * k);
      img.data[i + 3] = 255;
      height[y * size + x] = (1 - k) - groove * 0.8;
    }
  }
  g.putImageData(img, 0, 0);
  if (kind === "jungle" || kind === "meadow") {
    // moss patches
    for (let i = 0; i < 60; i++) {
      const x = rand() * size;
      const y = rand() * size;
      const r = 20 + rand() * 70;
      const grad = g.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, kind === "meadow" ? "rgba(120, 160, 70, 0.35)" : "rgba(70, 110, 50, 0.4)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      g.fillStyle = grad;
      g.fillRect(x - r, y - r, r * 2, r * 2);
    }
  }
  // normal map (central differences, wrapping) and roughness map (three reads its green channel)
  const [nc, ng] = canvas(size, size);
  const [rc, rg] = canvas(size, size);
  const nImg = ng.createImageData(size, size);
  const rImg = rg.createImageData(size, size);
  const strength = kind === "marble" || kind === "lacquer" ? 1.2 : 3.2;
  const h = (x: number, y: number) => height[((y + size) % size) * size + ((x + size) % size)]!;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = (h(x + 1, y) - h(x - 1, y)) * strength;
      const dy = (h(x, y + 1) - h(x, y - 1)) * strength;
      const inv = 1 / Math.sqrt(dx * dx + dy * dy + 1);
      const i = (y * size + x) * 4;
      nImg.data[i] = (-dx * inv * 0.5 + 0.5) * 255;
      nImg.data[i + 1] = (dy * inv * 0.5 + 0.5) * 255;
      nImg.data[i + 2] = (inv * 0.5 + 0.5) * 255;
      nImg.data[i + 3] = 255;
      const r = Math.max(0.05, Math.min(1, baseRoughness * (1.15 - h(x, y) * 0.35)));
      rImg.data[i] = rImg.data[i + 1] = rImg.data[i + 2] = r * 255;
      rImg.data[i + 3] = 255;
    }
  }
  ng.putImageData(nImg, 0, 0);
  rg.putImageData(rImg, 0, 0);
  return { color: c, normal: nc, rough: rc };
}

const matCache = new Map<string, HTMLCanvasElement>();

/**
 * A seat's playmat: cloth with a lighter nap under the lamp and a bound edge stitched in the seat's
 * colour; nothing else drawn in the play space. Opaque except the rounded corners.
 */
export function matTexture(felt: string, nap: string, playerColor: string): THREE.CanvasTexture {
  const key = `${felt}|${nap}|${playerColor}`;
  let c = matCache.get(key);
  if (!c) {
    c = drawMat(felt, nap, playerColor);
    matCache.set(key, c);
  }
  return texture(c);
}

function drawMat(felt: string, nap: string, playerColor: string): HTMLCanvasElement {
  const w = 1260;
  const h = 780;
  const r = 34;
  const [c, g] = canvas(w, h);
  roundRect(g, 0, 0, w, h, r);
  g.save();
  g.clip();
  g.fillStyle = felt;
  g.fillRect(0, 0, w, h);
  const lit = g.createRadialGradient(w / 2, h * 0.46, 40, w / 2, h / 2, w * 0.62);
  lit.addColorStop(0, nap);
  lit.addColorStop(1, felt);
  g.fillStyle = lit;
  g.fillRect(0, 0, w, h);
  // the weave: fine per-pixel fibre noise plus a soft cloudy variation, never a pattern
  const img = g.getImageData(0, 0, w, h);
  const rand = rng(w * 31 + felt.length);
  const cloud = noiseField(w, 9, rand);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const v = (rand() - 0.5) * 14 + (cloud(x, y) - 0.5) * 10;
      img.data[i] = img.data[i]! + v;
      img.data[i + 1] = img.data[i + 1]! + v;
      img.data[i + 2] = img.data[i + 2]! + v;
    }
  }
  g.putImageData(img, 0, 0);
  // the edge falls into shadow, then a bound hem
  g.lineWidth = 60;
  g.strokeStyle = "rgba(0, 0, 0, 0.18)";
  roundRect(g, 0, 0, w, h, r);
  g.stroke();
  g.lineWidth = 22;
  g.strokeStyle = "rgba(0, 0, 0, 0.42)";
  roundRect(g, 0, 0, w, h, r);
  g.stroke();
  g.restore();
  // its border, solid in the seat's colour (as on the Oops I Baked a Pie table: every seat's things in its colour)
  g.strokeStyle = playerColor;
  g.lineWidth = 7;
  roundRect(g, 12, 12, w - 24, h - 24, r - 8);
  g.stroke();
  return c;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

/** Mana symbol fills, as the DOM's `.mana` circles (styles.css --mana-*). */
const MANA: Record<string, string> = { W: "#f5efd9", U: "#9fcff0", B: "#b9aeb0", R: "#f2a07e", G: "#9ad3a6", C: "#ccc6c0", S: "#ccc6c0" };

/** One `{X}` symbol as a circle of diameter d centred at (cx, cy), drawn like ManaText. */
function manaSymbol(g: CanvasRenderingContext2D, sym: string, cx: number, cy: number, d: number): void {
  const up = sym.toUpperCase();
  const parts = up.split("/").map((p) => MANA[p]).filter(Boolean) as string[];
  g.save();
  g.beginPath();
  g.arc(cx, cy + d * 0.05, d / 2, 0, Math.PI * 2);
  g.fillStyle = "rgba(0, 0, 0, 0.45)";
  g.fill();
  g.beginPath();
  g.arc(cx, cy, d / 2, 0, Math.PI * 2);
  if (parts.length > 1) {
    const grad = g.createLinearGradient(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2);
    grad.addColorStop(0.5, parts[0]!);
    grad.addColorStop(0.5, parts[1]!);
    g.fillStyle = grad;
  } else g.fillStyle = up === "T" || up === "Q" ? "#d5d0c8" : parts[0] ?? MANA.C!;
  g.fill();
  g.fillStyle = "#111";
  g.textAlign = "center";
  g.textBaseline = "middle";
  const label = up === "T" ? "\u27f3" : up === "Q" ? "\u27f2" : up.replace("/P", "\u1d56").replace("/", "");
  g.font = `700 ${d * (label.length > 2 ? 0.48 : label.length > 1 ? 0.6 : 0.72)}px "Inter Variable", Inter, Arial, sans-serif`;
  g.fillText(label, cx, cy + d * 0.04);
  g.restore();
}

/** A filled bar like the proxy's name and type bars: pale frame tint, dark rule, lit top edge, a soft drop shadow. */
function bar(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number, u: number, fill: string, rule: string): void {
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.32)";
  g.shadowBlur = 0.9 * u;
  g.shadowOffsetY = 0.5 * u;
  roundRect(g, x, y, w, h, r);
  g.fillStyle = fill;
  g.fill();
  g.restore();
  g.save();
  roundRect(g, x, y, w, h, r);
  g.clip();
  g.fillStyle = "rgba(255, 255, 255, 0.55)";
  g.fillRect(x, y, w, 0.4 * u);
  g.restore();
  roundRect(g, x, y, w, h, r);
  g.strokeStyle = rule;
  g.lineWidth = 0.4 * u;
  g.stroke();
}

/** `text` cut with an ellipsis to fit `maxW` at the current font. */
function clip(g: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (g.measureText(text).width <= maxW) return text;
  let t = text;
  while (t.length > 1 && g.measureText(`${t}\u2026`).width > maxW) t = t.slice(0, -1);
  return `${t.trimEnd()}\u2026`;
}

/**
 * Draws the printed proxy (cards/proxy.ts, the small level of detail: a big name, the type's icon, a
 * big P/T) for a card without a cached image.
 */
function drawProxy(g: CanvasRenderingContext2D, W: number, H: number, card: CardData | undefined, face: number, fallbackName: string): void {
  const p = proxyFace(card, face, undefined, fallbackName);
  const c = proxyColours(p);
  const measure = textMeasure();
  const tier = CANVAS_TIER;
  const L = layoutProxy(p, tier, measure);
  const u = W / 100;
  const v = H / CARD_H; // px per vertical card unit (the canvas is not exactly 63:88)
  g.clearRect(0, 0, W, H);
  // black border and the frame's ink on linen stock
  g.fillStyle = BORDER;
  roundRect(g, 0, 0, W, H, 4.75 * u);
  g.fill();
  const b = tier.border * u;
  g.save();
  roundRect(g, b, b, W - b * 2, H - b * 2, 1.6 * u);
  g.clip();
  g.fillStyle = c.frame;
  g.fillRect(b, b, W - b * 2, H - b * 2);
  g.fillStyle = "rgba(0, 0, 0, 0.045)";
  for (let y = b; y < H - b; y += 3) g.fillRect(b, y, W - b * 2, 1);
  g.fillStyle = "rgba(255, 255, 255, 0.04)";
  for (let x = b; x < W - b; x += 3) g.fillRect(x, b, 1, H - b * 2);
  g.restore();
  roundRect(g, b + 0.22 * u, b + 0.22 * u, W - b * 2 - 0.44 * u, H - b * 2 - 0.44 * u, 1.4 * u);
  g.strokeStyle = c.dark;
  g.lineWidth = 0.45 * u;
  g.stroke();

  const x0 = L.inner.x * u;
  const iw = L.inner.w * u;
  const top = (tier.border + tier.pad) * v;
  // name bar: the cost on the right of the first line, the name wrapping under it
  const nb = L.name.barH * v;
  bar(g, x0, top, iw, nb, 1.1 * u, u, c.bar, c.dark);
  const ns = L.name.size * u;
  const lh = ns * tier.name.lh;
  const firstY = top + tier.name.padY * v + lh / 2;
  const syms = [...p.cost.matchAll(/\{([^}]+)\}|(\/\/)/g)];
  let cx = x0 + iw - tier.name.padX * u;
  const d = ns * 0.82 * 1.15;
  for (const m of syms.reverse()) {
    if (m[2]) {
      g.fillStyle = INK;
      g.font = `700 ${ns * 0.8}px "Inter Variable", Inter, Arial, sans-serif`;
      g.textAlign = "right";
      g.textBaseline = "middle";
      g.fillText("//", cx, firstY);
      cx -= g.measureText("//").width + 0.1 * ns;
      continue;
    }
    manaSymbol(g, m[1]!, cx - d / 2, firstY, d);
    cx -= d + 0.1 * ns;
  }
  g.fillStyle = INK;
  g.font = `700 ${ns}px Cinzel, Georgia, serif`;
  g.textAlign = "left";
  g.textBaseline = "middle";
  L.name.lines.slice(0, tier.name.lines).forEach((line, i) => {
    const s = line.tokens.map((t) => (t.t === "space" ? " " : t.t === "sym" ? `{${t.s}}` : t.s)).join("");
    const room = i === 0 ? cx - x0 - tier.name.padX * u : iw - tier.name.padX * 2 * u;
    const last = i === tier.name.lines - 1 && L.name.lines.length > tier.name.lines;
    g.fillText(last ? clip(g, `${s} ${L.name.lines.slice(i + 1).map((l) => l.tokens.map((t) => (t.t === "word" ? t.s : " ")).join("")).join(" ")}`, room) : clip(g, s, room), x0 + tier.name.padX * u, firstY + i * lh);
  });

  // the art window: the card's colours, engraved, the type's icon pressed in
  const fy = L.field.top * v;
  const fh = L.field.h * v;
  g.save();
  roundRect(g, x0, fy, iw, fh, 0.5 * u);
  g.clip();
  g.fillStyle = c.field[0];
  g.fillRect(x0, fy, iw, fh);
  if (c.field[1] !== c.field[0]) {
    // a two-colour field: the second colour beyond a seam at 118°, through the centre
    const k = Math.tan((28 * Math.PI) / 180) * (fh / 2);
    g.beginPath();
    g.moveTo(x0 + iw / 2 + k, fy);
    g.lineTo(x0 + iw, fy);
    g.lineTo(x0 + iw, fy + fh);
    g.lineTo(x0 + iw / 2 - k, fy + fh);
    g.closePath();
    g.fillStyle = c.field[1];
    g.fill();
  }
  g.strokeStyle = "rgba(255, 255, 255, 0.05)";
  g.lineWidth = 1;
  g.beginPath();
  for (let t = -fh; t < iw; t += 3) { g.moveTo(x0 + t, fy + fh); g.lineTo(x0 + t + fh, fy); }
  g.stroke();
  // recessed: darker toward the edges and under the top lip
  const edge = 4 * u;
  for (const [gx, gy, gw, gh, x1, y1, x2, y2] of [
    [x0, fy, iw, edge, 0, fy, 0, fy + edge], [x0, fy + fh - edge, iw, edge, 0, fy + fh, 0, fy + fh - edge],
    [x0, fy, edge, fh, x0, 0, x0 + edge, 0], [x0 + iw - edge, fy, edge, fh, x0 + iw, 0, x0 + iw - edge, 0],
  ] as const) {
    const gr = g.createLinearGradient(x1, y1, x2, y2);
    gr.addColorStop(0, "rgba(0, 0, 0, 0.26)");
    gr.addColorStop(1, "rgba(0, 0, 0, 0)");
    g.fillStyle = gr;
    g.fillRect(gx, gy, gw, gh);
  }
  const gs = Math.min(fh * 0.62, 40 * u) / 24;
  g.translate(x0 + iw / 2 - 12 * gs, fy + fh / 2 - 12 * gs);
  g.scale(gs, gs);
  const path = glyphPath(p.kind);
  g.translate(0, 0.7);
  g.fillStyle = c.glyphLit;
  g.fill(path, "evenodd");
  g.translate(0, -0.7);
  g.fillStyle = c.glyph;
  g.fill(path, "evenodd");
  g.restore();
  roundRect(g, x0, fy, iw, fh, 0.5 * u);
  g.strokeStyle = c.dark;
  g.lineWidth = 0.4 * u;
  g.stroke();

  // type bar
  const textBottom = H - (tier.border + tier.bottom) * v;
  const tb = L.text.box * v;
  const ty = textBottom - tb - (tier.gap + tier.type.h) * v;
  const th = tier.type.h * v;
  bar(g, x0, ty, iw, th, 1.1 * u, u, c.bar, c.dark);
  g.fillStyle = INK;
  g.font = `600 ${L.type.size * u}px "Inter Variable", Inter, Arial, sans-serif`;
  g.textBaseline = "middle";
  g.fillText(clip(g, p.type, iw - tier.name.padX * 2 * u), x0 + tier.name.padX * u, ty + th / 2 + 0.2 * u);

  // rules text, fitted (cards/proxy.ts fitText), reminder text lighter
  const tyTop = textBottom - tb;
  roundRect(g, x0, tyTop, iw, tb, 0.4 * u);
  g.fillStyle = c.paper;
  g.fill();
  g.strokeStyle = c.dark;
  g.lineWidth = 0.4 * u;
  g.stroke();
  const fs = L.text.size * u;
  const padX = tier.text.padX * u;
  g.save();
  roundRect(g, x0, tyTop, iw, tb, 0.4 * u);
  g.clip();
  g.font = `430 ${fs}px "Inter Variable", Inter, Arial, sans-serif`;
  g.textBaseline = "middle";
  g.textAlign = "left";
  const space = measure(" ", "text") * fs;
  let y = tyTop + tier.text.padY * v + (fs * tier.text.lh) / 2;
  for (const para of L.text.lines) {
    for (const line of para) {
      let x = x0 + padX;
      for (const t of line.tokens) {
        if (t.t === "space") { x += space; continue; }
        if (t.t === "sym") {
          const sd = fs * 0.82 * 1.15;
          manaSymbol(g, t.s, x + fs * 0.05 + sd / 2, y, sd);
          x += SYM_EM * fs;
          continue;
        }
        g.fillStyle = t.rem ? "rgba(31, 26, 21, 0.66)" : INK;
        g.font = `430 ${fs}px "Inter Variable", Inter, Arial, sans-serif`;
        g.textAlign = "left";
        g.fillText(t.s, x, y);
        x += measure(t.s, "text") * fs;
      }
      y += fs * tier.text.lh;
    }
    y += fs * tier.text.gap;
  }
  if (!L.text.fits) {
    const fade = g.createLinearGradient(0, textBottom - 7 * u, 0, textBottom - u);
    fade.addColorStop(0, "rgba(0, 0, 0, 0)");
    fade.addColorStop(1, c.paper);
    g.fillStyle = fade;
    g.fillRect(x0, textBottom - 7 * u, iw, 7 * u);
  }
  g.restore();

  // P/T, loyalty or defense
  if (p.stat) {
    g.font = `700 ${tier.stat.size * u}px Cinzel, Georgia, serif`;
    const pw = Math.max(tier.stat.w * u, g.measureText(p.stat.text).width + 4 * u);
    const ph = tier.stat.h * u;
    const px = W - b - tier.stat.inset * u - pw;
    const py = H - b - tier.stat.inset * u - ph;
    const dark = p.stat.kind !== "pt";
    bar(g, px, py, pw, ph, 1.1 * u, u, dark ? (p.stat.kind === "defense" ? "#4a231c" : "#24201c") : c.bar, c.dark);
    g.fillStyle = dark ? "#f1e8d4" : INK;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(p.stat.text, px + pw / 2, py + ph / 2 + 0.3 * u);
  }
  // the table's lights brighten the stock: one warm multiply brings it back to the printed card's tones
  g.save();
  roundRect(g, 0, 0, W, H, 4.75 * u);
  g.clip();
  g.globalCompositeOperation = "multiply";
  g.fillStyle = "#cfc8bd";
  g.fillRect(0, 0, W, H);
  g.restore();
}

const glyphPaths = new Map<string, Path2D>();
function glyphPath(kind: keyof typeof TYPE_GLYPHS): Path2D {
  let p = glyphPaths.get(kind);
  if (!p) glyphPaths.set(kind, (p = new Path2D(TYPE_GLYPHS[kind])));
  return p;
}

const PROXY_W = 488;
const PROXY_H = 680;

/** A readable printed proxy for cards without a cached image (offline, no art). */
export function textCardCanvas(card: CardData | undefined, face: number, fallbackName = ""): HTMLCanvasElement {
  const [c, g] = canvas(PROXY_W, PROXY_H);
  drawProxy(g, PROXY_W, PROXY_H, card, face, fallbackName);
  return c;
}

/**
 * The proxy as a texture, drawn once. If the proxy's fonts haven't loaded yet it is drawn with the
 * fallbacks now and once more, into the same canvas, when they arrive (never per frame).
 */
export function textCardTexture(card: CardData | undefined, face: number, fallbackName = ""): THREE.CanvasTexture {
  const c = textCardCanvas(card, face, fallbackName);
  const t = texture(c);
  if (!proxyFontsReady()) {
    void whenProxyFontsReady().then(() => {
      drawProxy(c.getContext("2d")!, PROXY_W, PROXY_H, card, face, fallbackName);
      t.needsUpdate = true;
    });
  }
  return t;
}

/** A triggered or activated ability on the stack (GameCard.ability), as the 2D table's `.ability-card`. */
export interface AbilityFace { kind: string; source_name: string | null; text: string }

/** Words wrapped to `maxW` at the current font; null when they need more than `maxLines`. */
function wrap(g: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] | null {
  const lines: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (line && g.measureText(next).width > maxW) {
        lines.push(line);
        line = word;
      } else line = next;
    }
    if (line) lines.push(line);
    if (lines.length > maxLines) return null;
  }
  return lines;
}

/**
 * An ability's card: its source's art (when cached) across the top, a brass rule, what kind of ability it is,
 * the source's name and the ability's text, fitted. Drawn at once and once more when the art arrives.
 */
export function abilityCardTexture(a: AbilityFace, artUrl: string | null): THREE.CanvasTexture {
  const [c, g] = canvas(PROXY_W, PROXY_H);
  const t = texture(c);
  const draw = (art: HTMLImageElement | null) => {
    const W = PROXY_W;
    const H = PROXY_H;
    const u = W / 100;
    g.clearRect(0, 0, W, H);
    g.fillStyle = BORDER;
    roundRect(g, 0, 0, W, H, 4.75 * u);
    g.fill();
    const b = 3.2 * u;
    const iw = W - b * 2;
    const artH = H * 0.42;
    g.save();
    roundRect(g, b, b, iw, H - b * 2, 1.6 * u);
    g.clip();
    const bg = g.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "#2a2622");
    bg.addColorStop(1, "#151311");
    g.fillStyle = bg;
    g.fillRect(b, b, iw, H - b * 2);
    if (art) {
      // a Scryfall "normal" scan: its art box is roughly 8–92% across and 11–55% down
      const sx = art.naturalWidth * 0.08;
      const sy = art.naturalHeight * 0.11;
      const sw = art.naturalWidth * 0.84;
      const sh = art.naturalHeight * 0.44;
      const scale = Math.max(iw / sw, artH / sh);
      const dw = iw / scale;
      const dh = artH / scale;
      g.drawImage(art, sx + (sw - dw) / 2, sy + (sh - dh) / 2, dw, dh, b, b, iw, artH);
      const fade = g.createLinearGradient(0, b + artH * 0.6, 0, b + artH);
      fade.addColorStop(0, "rgba(21, 19, 17, 0)");
      fade.addColorStop(1, "rgba(21, 19, 17, 0.85)");
      g.fillStyle = fade;
      g.fillRect(b, b, iw, artH);
    }
    g.restore();
    const ruleY = b + artH;
    g.fillStyle = "#b8945a";
    g.fillRect(b, ruleY, iw, 0.5 * u);
    const pad = 6 * u;
    const textW = iw - pad * 2 + 2 * b;
    let y = ruleY + 7 * u;
    g.textAlign = "left";
    g.textBaseline = "middle";
    g.fillStyle = "#c9a25c";
    g.font = `700 ${4.2 * u}px Cinzel, Georgia, serif`;
    g.fillText(clip(g, (a.kind === "other" ? "ability" : `${a.kind} ability`).toUpperCase(), textW), pad, y);
    if (a.source_name) {
      y += 7.5 * u;
      g.fillStyle = "#efe6d4";
      g.font = `700 ${6.2 * u}px Cinzel, Georgia, serif`;
      g.fillText(clip(g, a.source_name, textW), pad, y);
    }
    y += 6 * u;
    const bottom = H - b - 4 * u;
    // the largest size the whole text fits at, down to a floor (then it's cut with an ellipsis)
    let size = 6.4 * u;
    let lines: string[] | null = null;
    for (; size >= 3.6 * u; size -= 0.2 * u) {
      g.font = `430 ${size}px "Inter Variable", Inter, Arial, sans-serif`;
      lines = wrap(g, a.text, textW, Math.floor((bottom - y) / (size * 1.28)));
      if (lines) break;
    }
    if (!lines) {
      const max = Math.floor((bottom - y) / (size * 1.28));
      lines = (wrap(g, a.text, textW, 999) ?? []).slice(0, max);
      if (lines.length) lines[lines.length - 1] = clip(g, `${lines[lines.length - 1]}…`, textW);
    }
    g.fillStyle = "#e4dccb";
    lines.forEach((line, i) => g.fillText(line, pad, y + size * 0.64 + i * size * 1.28));
    t.needsUpdate = true;
  };
  draw(null);
  let loaded: HTMLImageElement | null = null;
  if (artUrl) {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => draw((loaded = img));
    img.src = artUrl;
  }
  if (!proxyFontsReady()) void whenProxyFontsReady().then(() => draw(loaded));
  return t;
}

/** The card back drawn here while the host hasn't the Magic card back yet (cards/drawnBack.ts, as the 2D table's). */
export function backCanvas(): HTMLCanvasElement {
  return drawnBackCanvas();
}

/**
 * A Scryfall card picture (the card back, a card's scan) as a texture, with its square white corners painted in the
 * border's black: trimmed corners alone still let the white bleed into the edge from a distance, through the mipmaps.
 * Returned at once and filled in when the picture has loaded (as three's TextureLoader does); `onError` if it can't be.
 */
export function cardImageTexture(url: string, onError?: () => void, onLoad?: (t: THREE.Texture) => void): THREE.Texture {
  const t = new THREE.Texture();
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = maxAnisotropy;
  const img = new Image();
  img.decoding = "async";
  img.onload = () => {
    const [c, g] = canvas(img.naturalWidth, img.naturalHeight);
    g.fillStyle = "#0b0a09";
    g.fillRect(0, 0, c.width, c.height);
    roundRect(g, 0, 0, c.width, c.height, c.width * 0.05);
    g.clip();
    g.drawImage(img, 0, 0);
    t.image = c;
    t.needsUpdate = true;
    onLoad?.(t);
  };
  img.onerror = () => onError?.();
  img.src = url;
  return t;
}

let cornerMask: THREE.CanvasTexture | null = null;

/**
 * An alpha map that trims a card picture to a card's rounded corners (with `alphaTest`): Scryfall's images, the card back
 * among them, have square white corners outside their black border. Shared by every card-shaped material; never disposed.
 */
export function cardCornerMask(): THREE.Texture {
  if (cornerMask) return cornerMask;
  const W = 252;
  const H = 352; // 63:88
  const [c, g] = canvas(W, H);
  g.fillStyle = "#000";
  g.fillRect(0, 0, W, H);
  g.fillStyle = "#fff";
  roundRect(g, 0, 0, W, H, W * 0.062);
  g.fill();
  cornerMask = new THREE.CanvasTexture(c); // a mask, not a colour: stays linear
  return cornerMask;
}

/** A soft blurred rounded-rect shadow for under a card: an alpha map (three reads its green channel). */
export function contactShadowTexture(): THREE.CanvasTexture {
  const W = 128;
  const H = 168;
  const [c, g] = canvas(W, H);
  g.fillStyle = "#000";
  g.fillRect(0, 0, W, H);
  // a soft ramp from nested translucent rounded rects (no reliance on canvas blur support)
  const steps = 16;
  for (let i = 0; i < steps; i++) {
    g.fillStyle = `rgba(255, 255, 255, ${0.12 + i * 0.01})`;
    const inset = 4 + i * 1.6;
    roundRect(g, inset, inset, W - inset * 2, H - inset * 2, 16);
    g.fill();
  }
  const t = new THREE.CanvasTexture(c);
  return t;
}

export { texture as canvasTexture };

/**
 * The count tag over another player's fan of backs when their hand is bigger than the fan draws (table3d/handFan.ts):
 * the hand's size in Cinzel on a walnut chip with a brass edge. A count only (public), never anything about the cards.
 */
export function handCountCanvas(n: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = 160;
  c.height = 96;
  const g = c.getContext("2d");
  if (!g) return c;
  roundRect(g, 6, 6, c.width - 12, c.height - 12, 30);
  g.fillStyle = "#2a1a10";
  g.fill();
  g.lineWidth = 5;
  g.strokeStyle = "#b8914f";
  g.stroke();
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = "700 50px Cinzel, Georgia, serif";
  g.fillStyle = "#efe3c6";
  g.fillText(String(n), c.width / 2, c.height / 2 + 3);
  return c;
}

// ------------------------------------------------------------------ card badges (Arena-style)

export interface CardOverlay {
  /** Current power/toughness, and whether each is above (+1) or below (−1) the printed value. */
  pt?: { text: string; dir: -1 | 0 | 1 };
  damage?: number;
  /** Keyword abilities from counters or effects, with a count for stacked counters. */
  keywords: { kind: string; n: number }[];
  /** Other counters (loyalty, charge, oil…). */
  counters: { label: string; n: number }[];
  /** On the stack: its chain number, and whether it resolves next. */
  chain?: { no: number; next: boolean };
  /** Arena-style ×N: this card tops a pile of identical lands, or is a stack of N tokens (game/piles.ts countMark). */
  pile?: number;
  /** The encoder's owner gem: someone else owns this card (their initial, in their seat colour). */
  owner?: { initial: string; color: string };
  /**
   * -- attached elsewhere -- another player's attachment tucked under a permanent here (game/attachments.ts guests): a frame in
   * their seat colour and their initial on a tab in the corner that peeks out (the right edge, at the `front` end: the edge toward
   * the middle of the table).
   */
  guest?: { initial: string; color: string; front: "top" | "bottom" };
  /**
   * -- playtest (nov 18) -- combat read physically: whom this attacker attacks ("→" and the defender's initial on their seat colour; a
   * dashed rim while only planned in the declare-attackers prompt), and how many attackers a blocker blocks when it blocks several.
   */
  combat?: { to?: { initial: string; color: string; planned: boolean }; blocks?: number; planned?: boolean };
}

/** The combat chip (CardOverlay.combat) at (x, y), `h` tall, on any overlay canvas: "→ (B)" for an attacker, "blocks 2" for a blocker. */
export function drawCombatChip(g: CanvasRenderingContext2D, x: number, y: number, h: number, combat: NonNullable<CardOverlay["combat"]>): void {
  const to = combat.to;
  // (a block planned in the declare-blockers prompt: "blocks" — "blocks 2" for several — on a dashed rim until declared)
  const label = to ? "→" : combat.planned && (combat.blocks ?? 1) <= 1 ? "blocks" : `blocks ${combat.blocks ?? ""}`;
  g.save();
  g.font = `800 ${Math.round(h * 0.62)}px Inter, Arial, sans-serif`;
  const tw = g.measureText(label).width;
  const w = tw + h * (to ? 1.35 : 0.55);
  g.fillStyle = "#16110c";
  roundRect(g, x, y, w, h, h * 0.3);
  g.fill();
  g.lineWidth = Math.max(2, h * 0.07);
  g.strokeStyle = to ? "#e0645c" : "#5fa8ff";
  if (to?.planned || combat.planned) g.setLineDash([h * 0.16, h * 0.1]);
  g.stroke();
  g.setLineDash([]);
  g.textAlign = "left";
  g.textBaseline = "middle";
  g.fillStyle = "#f6ead8";
  g.fillText(label, x + h * 0.22, y + h / 2 + 1);
  if (to) {
    const r = h * 0.36;
    const cx = x + h * 0.32 + tw + r;
    g.beginPath();
    g.arc(cx, y + h / 2, r, 0, Math.PI * 2);
    g.fillStyle = to.color;
    g.fill();
    g.fillStyle = "#0e0b08";
    g.textAlign = "center";
    g.font = `800 ${Math.round(h * 0.46)}px Inter, Arial, sans-serif`;
    g.fillText(to.initial, cx, y + h / 2 + 1);
  }
  g.restore();
}

/** The guest frame and tab (CardOverlay.guest) on a W × H overlay. */
export function drawGuestMark(g: CanvasRenderingContext2D, W: number, H: number, guest: NonNullable<CardOverlay["guest"]>): void {
  const lw = Math.max(3, W * 0.028);
  g.save();
  g.strokeStyle = guest.color;
  g.lineWidth = lw;
  roundRect(g, lw / 2, lw / 2, W - lw, H - lw, W * 0.045);
  g.stroke();
  // the tab: inside the strip a tucked card shows (12% of the width), a notched flag hanging from the front edge
  const tw = W * 0.115;
  const th = W * 0.17;
  const x = W - tw;
  const down = guest.front === "top";
  const y0 = down ? 0 : H;
  const y1 = down ? th : H - th;
  const notch = down ? th * 0.82 : H - th * 0.82;
  g.beginPath();
  g.moveTo(x, y0);
  g.lineTo(W, y0);
  g.lineTo(W, y1);
  g.lineTo(x + tw / 2, notch);
  g.lineTo(x, y1);
  g.closePath();
  g.fillStyle = guest.color;
  g.fill();
  g.lineWidth = Math.max(2, W * 0.008);
  g.strokeStyle = "rgba(14, 11, 8, 0.8)";
  g.stroke();
  g.fillStyle = "#0e0b08";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `800 ${Math.round(tw * 0.78)}px Inter, Arial, sans-serif`;
  g.fillText(guest.initial, x + tw / 2, down ? th * 0.4 : H - th * 0.4);
  g.restore();
}

export const OVERLAY_W = 512;
export const OVERLAY_H = 714;
const BRASS = "#d8ae62";
const PLATE = "#16110c";

/** Small line-art glyphs for keyword badges, drawn in a box of radius r around (0, 0). */
const GLYPHS: Record<string, (g: CanvasRenderingContext2D, r: number) => void> = {
  flying(g, r) { // a wing
    g.beginPath();
    g.moveTo(-r * 0.8, r * 0.35);
    g.quadraticCurveTo(-r * 0.2, -r * 0.9, r * 0.85, -r * 0.55);
    g.quadraticCurveTo(r * 0.3, -r * 0.25, r * 0.55, -r * 0.05);
    g.quadraticCurveTo(r * 0.05, 0, r * 0.3, r * 0.3);
    g.quadraticCurveTo(-r * 0.2, r * 0.25, -r * 0.8, r * 0.35);
    g.fill();
  },
  "first strike"(g, r) { sword(g, r, 0); },
  "double strike"(g, r) { sword(g, r * 0.9, -r * 0.32); sword(g, r * 0.9, r * 0.32); },
  deathtouch(g, r) { // a skull
    g.beginPath();
    g.arc(0, -r * 0.15, r * 0.62, Math.PI * 0.85, Math.PI * 2.15);
    g.lineTo(r * 0.35, r * 0.7);
    g.lineTo(-r * 0.35, r * 0.7);
    g.closePath();
    g.fill();
    g.globalCompositeOperation = "destination-out";
    for (const x of [-0.25, 0.25]) { g.beginPath(); g.arc(x * r, -r * 0.1, r * 0.17, 0, Math.PI * 2); g.fill(); }
    g.globalCompositeOperation = "source-over";
  },
  hexproof(g, r) { shield(g, r); g.globalCompositeOperation = "destination-out"; shield(g, r * 0.55); g.globalCompositeOperation = "source-over"; },
  indestructible(g, r) { // a solid shield with a bar
    shield(g, r);
    g.globalCompositeOperation = "destination-out";
    g.fillRect(-r * 0.12, -r * 0.5, r * 0.24, r * 0.95);
    g.globalCompositeOperation = "source-over";
  },
  lifelink(g, r) { // a heart
    g.beginPath();
    g.moveTo(0, r * 0.75);
    g.bezierCurveTo(-r * 1.1, 0, -r * 0.55, -r * 0.85, 0, -r * 0.3);
    g.bezierCurveTo(r * 0.55, -r * 0.85, r * 1.1, 0, 0, r * 0.75);
    g.fill();
  },
  menace(g, r) { // two horns
    for (const s of [-1, 1]) {
      g.beginPath();
      g.moveTo(s * r * 0.15, r * 0.6);
      g.quadraticCurveTo(s * r * 0.95, r * 0.3, s * r * 0.75, -r * 0.8);
      g.quadraticCurveTo(s * r * 0.6, 0, s * r * 0.15, r * 0.15);
      g.fill();
    }
  },
  reach(g, r) { // an arrow pointing up
    g.beginPath();
    g.moveTo(0, -r * 0.85); g.lineTo(r * 0.55, -r * 0.2); g.lineTo(r * 0.18, -r * 0.2); g.lineTo(r * 0.18, r * 0.8);
    g.lineTo(-r * 0.18, r * 0.8); g.lineTo(-r * 0.18, -r * 0.2); g.lineTo(-r * 0.55, -r * 0.2);
    g.closePath(); g.fill();
  },
  trample(g, r) { // three chevrons
    g.lineWidth = r * 0.22;
    for (const y of [-0.5, 0, 0.5]) {
      g.beginPath(); g.moveTo(-r * 0.6, y * r - r * 0.2); g.lineTo(0, y * r + r * 0.2); g.lineTo(r * 0.6, y * r - r * 0.2); g.stroke();
    }
  },
  vigilance(g, r) { // an eye
    g.beginPath();
    g.moveTo(-r * 0.9, 0); g.quadraticCurveTo(0, -r * 0.85, r * 0.9, 0); g.quadraticCurveTo(0, r * 0.85, -r * 0.9, 0);
    g.fill();
    g.globalCompositeOperation = "destination-out";
    g.beginPath(); g.arc(0, 0, r * 0.32, 0, Math.PI * 2); g.fill();
    g.globalCompositeOperation = "source-over";
    g.beginPath(); g.arc(0, 0, r * 0.16, 0, Math.PI * 2); g.fill();
  },
  haste(g, r) { // a lightning bolt
    g.beginPath();
    g.moveTo(r * 0.25, -r * 0.9); g.lineTo(-r * 0.5, r * 0.1); g.lineTo(-r * 0.02, r * 0.1); g.lineTo(-r * 0.25, r * 0.9);
    g.lineTo(r * 0.5, -r * 0.15); g.lineTo(r * 0.02, -r * 0.15);
    g.closePath(); g.fill();
  },
};

function sword(g: CanvasRenderingContext2D, r: number, dx: number) {
  g.save();
  g.translate(dx, 0);
  g.rotate(-Math.PI / 4);
  g.fillRect(-r * 0.09, -r * 0.95, r * 0.18, r * 1.25); // blade
  g.fillRect(-r * 0.36, r * 0.28, r * 0.72, r * 0.14); // guard
  g.fillRect(-r * 0.08, r * 0.42, r * 0.16, r * 0.4); // grip
  g.restore();
}

function shield(g: CanvasRenderingContext2D, r: number) {
  g.beginPath();
  g.moveTo(0, -r * 0.85); g.lineTo(r * 0.72, -r * 0.55); g.quadraticCurveTo(r * 0.7, r * 0.45, 0, r * 0.9);
  g.quadraticCurveTo(-r * 0.7, r * 0.45, -r * 0.72, -r * 0.55);
  g.closePath(); g.fill();
}

function plate(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, edge = BRASS) {
  g.fillStyle = PLATE;
  roundRect(g, x, y, w, h, h * 0.3);
  g.fill();
  g.strokeStyle = edge;
  g.lineWidth = 4;
  g.stroke();
}

/** The pile badge's canvas height; its width follows the figure (pileBadgeCanvas). */
export const PILE_BADGE_H = 96;

/**
 * The ×N of a token pile or land pile on the 3D table, as its own badge (TableScene sizes it to stay readable at any camera
 * distance): the figure in heavy bone type on a near-black plate with a brass rim, wide enough for "×131,072".
 */
export function pileBadgeCanvas(n: number): HTMLCanvasElement {
  const text = countText(n);
  const h = PILE_BADGE_H;
  const font = "900 68px Inter, Arial, sans-serif";
  const [, mg] = canvas(4, 4);
  mg.font = font;
  const w = Math.ceil(Math.max(h * 1.45, mg.measureText(text).width + 40));
  const [c, g] = canvas(w, h);
  g.fillStyle = "rgba(0, 0, 0, 0.5)"; // a soft drop, so the plate stands off a pale card frame or the felt
  roundRect(g, 2, 7, w - 4, h - 8, (h - 8) * 0.32);
  g.fill();
  g.fillStyle = "#120d08";
  roundRect(g, 4, 3, w - 8, h - 10, (h - 10) * 0.32);
  g.fill();
  g.strokeStyle = BRASS;
  g.lineWidth = 5;
  g.stroke();
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = font;
  g.fillStyle = "#fff6e2";
  g.fillText(text, w / 2, h / 2 - 2);
  return c;
}

/** Transparent overlay drawn on top of a card face: P/T plate, damage, keyword badges, counters. */
export function cardOverlayCanvas(o: CardOverlay): HTMLCanvasElement {
  const W = OVERLAY_W;
  const H = OVERLAY_H;
  const [c, g] = canvas(W, H);
  g.textAlign = "center";
  g.textBaseline = "middle";
  // pile count, top right, clear of the name line's mana cost (lands have none)
  if (o.pile) {
    // (an engine token stack can be "×131,072": the plate widens to the left and the figure shrinks to fit)
    const text = countText(o.pile);
    g.font = "800 76px Inter, Arial, sans-serif";
    const size = Math.max(40, Math.min(76, Math.floor((76 * 330) / Math.max(1, g.measureText(text).width))));
    g.font = `800 ${size}px Inter, Arial, sans-serif`;
    const pw = Math.max(172, Math.min(360, g.measureText(text).width + 36));
    plate(g, W - 14 - pw, 96, pw, 110);
    g.fillStyle = "#f4ead6";
    g.fillText(text, W - 14 - pw / 2, 154);
  }
  // owner gem, top left, over the art's corner
  if (o.owner) {
    g.beginPath();
    g.arc(78, 150, 50, 0, Math.PI * 2);
    g.fillStyle = o.owner.color;
    g.fill();
    g.lineWidth = 8;
    g.strokeStyle = PLATE;
    g.stroke();
    g.fillStyle = "#0e0b08";
    g.font = "800 58px Inter, Arial, sans-serif";
    g.fillText(o.owner.initial, 78, 154);
  }
  if (o.combat) drawCombatChip(g, 14, 232, 120, o.combat); // (under the owner gem, over the art's left edge)
  // P/T plate, bottom right; a modified value says so with ▲/▼ as well as colour
  if (o.pt) {
    const w = 380;
    const h = 170;
    const x = W - w - 14;
    const y = H - h - 14;
    plate(g, x, y, w, h);
    g.fillStyle = o.pt.dir > 0 ? "#b6f09a" : o.pt.dir < 0 ? "#ffa08f" : "#f4ead6";
    g.font = "800 116px Inter, Arial, sans-serif";
    g.fillText(o.pt.text, x + w / 2 + (o.pt.dir ? 22 : 0), y + h / 2 + 6);
    if (o.pt.dir) {
      g.font = "800 50px Inter, Arial, sans-serif";
      g.fillText(o.pt.dir > 0 ? "▲" : "▼", x + 44, y + h / 2 + 4);
    }
  }
  if (o.damage) {
    const w = 380;
    const h = 150;
    const x = W - w - 14;
    const y = H - (o.pt ? 170 + 14 : 0) - h - 24;
    plate(g, x, y, w, h, "#e0574a");
    g.fillStyle = "#ffb3a8";
    g.font = "800 100px Inter, Arial, sans-serif";
    g.fillText(`${o.damage} dmg`, x + w / 2, y + h / 2 + 2);
  }
  // keyword badges, bottom left (at most 4 + an overflow chip, clear of the P/T plate)
  const R = 56;
  // a row of keyword badges above the P/T plate (two per row at this size)
  const shown = o.keywords.slice(0, o.keywords.length > 4 ? 3 : 4);
  shown.forEach(({ kind, n }, i) => {
    const cx = 14 + R + (i % 2) * (R * 2 + 10);
    const cy = H - 14 - R - Math.floor(i / 2) * (R * 2 + 10);
    g.fillStyle = PLATE;
    g.beginPath();
    g.arc(cx, cy, R, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = BRASS;
    g.lineWidth = 4;
    g.stroke();
    g.save();
    g.translate(cx, cy);
    g.fillStyle = g.strokeStyle = "#f4ead6";
    const glyph = GLYPHS[kind.toLowerCase()];
    if (glyph) glyph(g, R * 0.62);
    else {
      g.font = "800 30px Inter, Arial, sans-serif";
      g.fillText(kind.slice(0, 2).replace(/^./, (ch) => ch.toUpperCase()), 0, 2);
    }
    g.restore();
    if (n > 1) {
      plate(g, cx + R * 0.2, cy - R - 18, 74, 50);
      g.fillStyle = "#f4ead6";
      g.font = "800 36px Inter, Arial, sans-serif";
      g.fillText(`×${n}`, cx + R * 0.2 + 37, cy - R + 8);
    }
  });
  if (o.keywords.length > shown.length) {
    const cx = 14 + R + (shown.length % 2) * (R * 2 + 10);
    const cy = H - 14 - R - Math.floor(shown.length / 2) * (R * 2 + 10);
    plate(g, cx - R, cy - R * 0.6, R * 2, R * 1.2);
    g.fillStyle = "#f4ead6";
    g.font = "800 32px Inter, Arial, sans-serif";
    g.fillText(`+${o.keywords.length - shown.length}`, cx, cy + 2);
  }
  // chain number (bottom left) and the "Resolves next" plate (bottom right): clear of the name
  if (o.chain) {
    const R2 = 58;
    const cy = H - 18 - R2;
    g.fillStyle = o.chain.next ? "#d8ae62" : PLATE;
    g.beginPath();
    g.arc(18 + R2, cy, R2, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = BRASS;
    g.lineWidth = 5;
    g.stroke();
    g.fillStyle = o.chain.next ? "#231605" : "#f4ead6";
    g.font = "800 64px Cinzel, Georgia, serif";
    g.fillText(String(o.chain.no), 18 + R2, cy + 4);
    if (o.chain.next) {
      const w = 320;
      const h = 84;
      const x = W - w - 18;
      const y = H - h - 34;
      plate(g, x, y, w, h);
      g.fillStyle = "#f0c97d";
      g.font = "700 42px Inter, Arial, sans-serif";
      g.fillText("Resolves next", x + w / 2, y + h / 2 + 3);
    }
  }
  // other counters, top right, stacked
  o.counters.slice(0, 3).forEach(({ label, n }, i) => {
    g.font = "800 34px Inter, Arial, sans-serif";
    const text = `${label} ${n}`;
    const w = Math.min(W - 40, g.measureText(text).width + 40);
    const h = 60;
    const x = W - w - 14;
    const y = 96 + i * (h + 10);
    plate(g, x, y, w, h);
    g.fillStyle = "#f4ead6";
    g.fillText(text, x + w / 2, y + h / 2 + 2);
  });
  if (o.guest) drawGuestMark(g, W, H, o.guest);
  return c;
}
