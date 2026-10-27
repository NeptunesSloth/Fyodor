/**
 * Procedural textures, drawn on canvases: table surfaces for each plane, card fronts for cards
 * without a cached image (a readable text card), card backs / sleeves, and small labels.
 * Nothing is downloaded; everything is cached and disposed with the scene.
 */
import * as THREE from "three";
import type { Surface } from "../theme/planes";
import type { CardData } from "../types/cards";

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
 * A seat's playmat: cloth with a lighter nap under the lamp, a bound edge stitched in the seat's
 * colour, and a faint compass worked into the weave. Opaque except the rounded corners.
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
  // a faint compass worked into the cloth, centred where nothing important lies
  g.strokeStyle = "rgba(255, 255, 255, 0.03)";
  g.lineWidth = 3;
  for (const rr of [150, 168]) {
    g.beginPath();
    g.arc(w / 2, h / 2, rr, 0, Math.PI * 2);
    g.stroke();
  }
  g.beginPath();
  for (let k = 0; k < 4; k++) {
    const a = (k * Math.PI) / 2;
    g.moveTo(w / 2 + Math.cos(a) * 196, h / 2 + Math.sin(a) * 196);
    g.lineTo(w / 2 + Math.cos(a + Math.PI / 4) * 40, h / 2 + Math.sin(a + Math.PI / 4) * 40);
    g.lineTo(w / 2 + Math.cos(a + Math.PI / 2) * 196, h / 2 + Math.sin(a + Math.PI / 2) * 196);
  }
  g.stroke();
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
  // the stitching, in the seat's colour
  g.strokeStyle = playerColor;
  g.globalAlpha = 0.75;
  g.lineWidth = 3;
  g.setLineDash([13, 9]);
  roundRect(g, 17, 17, w - 34, h - 34, r - 12);
  g.stroke();
  g.setLineDash([]);
  g.globalAlpha = 1;
  return c;
}

/** Outline slot for a zone pile. */
export function slotTexture(label: string, color: string): THREE.CanvasTexture {
  const [c, g] = canvas(168, 234);
  g.fillStyle = "rgba(0, 0, 0, 0.28)";
  roundRect(g, 6, 6, 156, 222, 12);
  g.fill();
  g.strokeStyle = color;
  g.globalAlpha = 0.4;
  g.lineWidth = 2;
  roundRect(g, 6, 6, 156, 222, 12);
  g.stroke();
  g.globalAlpha = 0.7;
  g.fillStyle = color;
  g.font = "600 20px Cinzel, Georgia, serif";
  g.textAlign = "center";
  g.fillText(label.toUpperCase(), 84, 124);
  return texture(c);
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

const FRAME: Record<string, [string, string]> = {
  W: ["#e6dcc2", "#b3a681"], U: ["#4f86c0", "#1f4876"], B: ["#5a5254", "#262123"], R: ["#cc5f42", "#7a2818"],
  G: ["#4f9563", "#1e5231"], M: ["#d9b65e", "#8e6b24"], C: ["#aaa6a0", "#66625d"], L: ["#a88f6a", "#5a4630"],
};

function wrap(g: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, lh: number, maxY: number): void {
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(" ")) {
      const test = line ? `${line} ${word}` : word;
      if (g.measureText(test).width > maxW && line) {
        if (y > maxY) return;
        g.fillText(line, x, y);
        y += lh;
        line = word;
      } else line = test;
    }
    if (y > maxY) return;
    g.fillText(line, x, y);
    y += lh * 1.25;
  }
}

/** A readable card front for cards without a cached image (offline, no art). */
export function textCardCanvas(card: CardData | undefined, face: number, fallbackName = ""): HTMLCanvasElement {
  const W = 488;
  const H = 680;
  const [c, g] = canvas(W, H);
  const f = card?.faces?.[face];
  const name = f?.name ?? card?.name ?? fallbackName;
  const type = f?.type_line ?? card?.type_line ?? "";
  const cost = f?.mana_cost ?? card?.mana_cost ?? "";
  const text = (f?.oracle_text ?? card?.oracle_text ?? "").replace(/\s*\([^()]*\)/g, "");
  const power = f?.power ?? card?.power;
  const toughness = f?.toughness ?? card?.toughness;
  const loyalty = f?.loyalty ?? card?.loyalty;
  const colors = f?.colors ?? card?.colors ?? [];
  const key = /\bLand\b/.test(type) ? "L" : colors.length > 1 ? "M" : colors[0] ?? "C";
  const [light, dark] = FRAME[key] ?? FRAME.C!;
  g.fillStyle = "#0d0d0d";
  roundRect(g, 0, 0, W, H, 26);
  g.fill();
  const grad = g.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, dark);
  grad.addColorStop(0.5, light);
  grad.addColorStop(1, dark);
  g.fillStyle = grad;
  roundRect(g, 18, 18, W - 36, H - 36, 14);
  g.fill();
  // name bar
  g.fillStyle = "rgba(250, 244, 230, 0.72)";
  roundRect(g, 32, 32, W - 64, 56, 10);
  g.fill();
  g.fillStyle = "#111";
  g.font = "700 30px Inter, Arial, sans-serif";
  g.textBaseline = "middle";
  let nameText = name;
  while (g.measureText(nameText).width > W - 180 && nameText.length > 4) nameText = nameText.slice(0, -2);
  g.fillText(nameText === name ? name : `${nameText}…`, 46, 61);
  // mana cost as pips
  const pips = [...cost.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]!);
  let px = W - 50;
  for (const pip of pips.reverse()) {
    const col = { W: "#f5efd9", U: "#9fcff0", B: "#b9aeb0", R: "#f2a07e", G: "#9ad3a6" }[pip] ?? "#ccc6c0";
    g.fillStyle = col;
    g.beginPath();
    g.arc(px, 61, 17, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#111";
    g.font = "700 20px Inter, Arial, sans-serif";
    g.textAlign = "center";
    g.fillText(/^[WUBRG]$/.test(pip) ? pip : pip.replace("/", ""), px, 62);
    g.textAlign = "left";
    px -= 38;
  }
  // art window: a soft wash, in the colour a basic land makes
  const basic = type.match(/\b(Plains|Island|Swamp|Mountain|Forest)\b/)?.[1];
  // a solid art window (a pale wash turns the whole card white at table distance)
  const [hiCol, loCol]: [string, string] = basic
    ? ({ Plains: ["#e8d9a4", "#a8915a"], Island: ["#5d9bd6", "#1d4677"], Swamp: ["#6a5566", "#241a22"], Mountain: ["#d8734f", "#6e2414"], Forest: ["#5fa36c", "#1c4a2a"] } as Record<string, [string, string]>)[basic]!
    : [light, dark];
  const art = g.createLinearGradient(32, 100, W - 32, 330);
  art.addColorStop(0, hiCol);
  art.addColorStop(1, loCol);
  g.fillStyle = art;
  roundRect(g, 32, 100, W - 64, 230, 6);
  g.fill();
  g.fillStyle = "rgba(255, 255, 255, 0.32)";
  g.font = "600 110px Cinzel, Georgia, serif";
  g.textAlign = "center";
  g.fillText(name.slice(0, 1).toUpperCase(), W / 2, 220);
  g.textAlign = "left";
  // type bar
  g.fillStyle = "rgba(250, 244, 230, 0.72)";
  roundRect(g, 32, 340, W - 64, 46, 8);
  g.fill();
  g.fillStyle = "#111";
  g.font = "600 24px Inter, Arial, sans-serif";
  let typeText = type;
  while (g.measureText(typeText).width > W - 90 && typeText.length > 4) typeText = typeText.slice(0, -2);
  g.fillText(typeText, 46, 364);
  // rules text
  g.fillStyle = "rgba(246, 238, 220, 0.8)";
  roundRect(g, 32, 396, W - 64, H - 450, 6);
  g.fill();
  g.fillStyle = "#151515";
  g.font = "400 23px Inter, Arial, sans-serif";
  g.textBaseline = "top";
  wrap(g, text, 48, 410, W - 96, 28, H - 110);
  // P/T or loyalty
  const pt = power != null && toughness != null ? `${power}/${toughness}` : loyalty != null ? String(loyalty) : null;
  if (pt) {
    g.fillStyle = "#f2efe8";
    roundRect(g, W - 150, H - 92, 112, 52, 10);
    g.fill();
    g.strokeStyle = "#333";
    g.lineWidth = 2;
    g.stroke();
    g.fillStyle = "#111";
    g.font = "800 32px Inter, Arial, sans-serif";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(pt, W - 94, H - 65);
  }
  return c;
}

/** The default card back: a dark sleeve with a subtle gold emblem in the player's colour. */
export function backCanvas(color: string): HTMLCanvasElement {
  const W = 244;
  const H = 340;
  const [c, g] = canvas(W, H);
  g.fillStyle = "#0b0b0b";
  roundRect(g, 0, 0, W, H, 14);
  g.fill();
  const grad = g.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, "#22304a");
  grad.addColorStop(1, "#111827");
  g.fillStyle = grad;
  roundRect(g, 8, 8, W - 16, H - 16, 10);
  g.fill();
  g.strokeStyle = "#c79a4a";
  g.globalAlpha = 0.7;
  g.lineWidth = 3;
  roundRect(g, 18, 18, W - 36, H - 36, 8);
  g.stroke();
  g.globalAlpha = 1;
  const rg = g.createRadialGradient(W / 2, H / 2, 4, W / 2, H / 2, 70);
  rg.addColorStop(0, "#e9c77a");
  rg.addColorStop(0.5, "#b8883e");
  rg.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = rg;
  g.beginPath();
  g.ellipse(W / 2, H / 2, 58, 80, 0, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = color;
  g.globalAlpha = 0.9;
  g.fillRect(W / 2 - 40, H - 34, 80, 5);
  g.globalAlpha = 1;
  return c;
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

/** Transparent overlay drawn on top of a card face: P/T plate, damage, keyword badges, counters. */
export function cardOverlayCanvas(o: CardOverlay): HTMLCanvasElement {
  const W = OVERLAY_W;
  const H = OVERLAY_H;
  const [c, g] = canvas(W, H);
  g.textAlign = "center";
  g.textBaseline = "middle";
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
  return c;
}
