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

function mix(a: THREE.Color, b: THREE.Color, t: number): string {
  return `#${a.clone().lerp(b, Math.max(0, Math.min(1, t))).getHexString()}`;
}

/** The table top for a plane: wood, marble, slate, stone… */
export function surfaceTexture(kind: Surface, base: string, grain: string, inlay: string, seed = 7): THREE.CanvasTexture {
  const size = 1024;
  const [c, g] = canvas(size, size);
  const rand = rng(seed);
  const A = hex(base);
  const B = hex(grain);
  const n1 = noiseField(size, 6, rand);
  const n2 = noiseField(size, 24, rand);
  const img = g.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let t: number;
      switch (kind) {
        case "oak":
        case "weathered":
        case "lacquer": {
          // long planks with flowing grain lines
          const plank = Math.floor(y / 128);
          const warp = n1(x, y + plank * 97) * 18;
          const line = Math.sin((y + warp) * 0.55 + plank * 3.1) * 0.5 + 0.5;
          t = 0.35 * line + 0.45 * n2(x * 0.25, y * 2.2) + (y % 128 < 2 ? 0.9 : 0);
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
        }
      }
      const col = new THREE.Color(mix(A, B, t));
      const i = (y * size + x) * 4;
      img.data[i] = col.r * 255;
      img.data[i + 1] = col.g * 255;
      img.data[i + 2] = col.b * 255;
      img.data[i + 3] = 255;
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
  void inlay;
  return texture(c);
}

/** A seat mat: a faint bordered area with zone outlines, tinted with the plane's inlay colour. */
export function matTexture(inlay: string, accent: string, playerColor: string): THREE.CanvasTexture {
  const w = 1200;
  const h = 720;
  const [c, g] = canvas(w, h);
  g.fillStyle = "rgba(0, 0, 0, 0.12)";
  g.fillRect(0, 0, w, h);
  const grad = g.createRadialGradient(w / 2, h / 2, 50, w / 2, h / 2, w * 0.6);
  grad.addColorStop(0, "rgba(255, 255, 255, 0.04)");
  grad.addColorStop(1, "rgba(0, 0, 0, 0.14)");
  g.fillStyle = grad;
  g.fillRect(0, 0, w, h);
  g.strokeStyle = inlay;
  g.globalAlpha = 0.55;
  g.lineWidth = 4;
  g.strokeRect(10, 10, w - 20, h - 20);
  g.globalAlpha = 0.25;
  g.lineWidth = 2;
  g.strokeRect(24, 24, w - 48, h - 48);
  // corner ornaments
  g.globalAlpha = 0.6;
  g.strokeStyle = accent;
  for (const [x, y, sx, sy] of [[24, 24, 1, 1], [w - 24, 24, -1, 1], [24, h - 24, 1, -1], [w - 24, h - 24, -1, -1]] as const) {
    g.beginPath();
    g.moveTo(x, y + sy * 60);
    g.lineTo(x, y);
    g.lineTo(x + sx * 60, y);
    g.stroke();
  }
  // the owner's edge carries their seat colour
  g.globalAlpha = 0.8;
  g.fillStyle = playerColor;
  g.fillRect(w * 0.3, h - 16, w * 0.4, 5);
  g.globalAlpha = 1;
  return texture(c);
}

/** Outline slot for a zone pile. */
export function slotTexture(label: string, color: string): THREE.CanvasTexture {
  const [c, g] = canvas(168, 234);
  g.strokeStyle = color;
  g.globalAlpha = 0.55;
  g.setLineDash([10, 8]);
  g.lineWidth = 4;
  roundRect(g, 6, 6, 156, 222, 12);
  g.stroke();
  g.setLineDash([]);
  g.globalAlpha = 0.6;
  g.fillStyle = color;
  g.font = "600 22px Cinzel, Georgia, serif";
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
  W: ["#f3ecd6", "#d8cba6"], U: ["#a9cde9", "#5f93c2"], B: ["#a79c9a", "#4b4342"], R: ["#eaa688", "#b8553a"],
  G: ["#a5cf9f", "#4f8a50"], M: ["#e4cf87", "#b89a3e"], C: ["#cfc9c2", "#8f8a84"], L: ["#c9b89a", "#8a7658"],
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
  // art window: a soft abstract wash in the card's colours
  const art = g.createLinearGradient(32, 100, W - 32, 330);
  art.addColorStop(0, "rgba(0, 0, 0, 0.55)");
  art.addColorStop(1, "rgba(0, 0, 0, 0.15)");
  g.fillStyle = art;
  roundRect(g, 32, 100, W - 64, 230, 6);
  g.fill();
  g.fillStyle = "rgba(255, 255, 255, 0.28)";
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
  grad.addColorStop(0, "#3a2616");
  grad.addColorStop(1, "#1c120b");
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

/** A small rounded label (counters, damage, P/T changes). */
export function labelCanvas(text: string, bg: string, fg = "#fff"): HTMLCanvasElement {
  const [probe, pg] = canvas(8, 8);
  void probe;
  pg.font = "700 40px Inter, Arial, sans-serif";
  const w = Math.ceil(pg.measureText(text).width) + 36;
  const [c, g] = canvas(w, 60);
  g.fillStyle = bg;
  roundRect(g, 2, 2, w - 4, 56, 26);
  g.fill();
  g.strokeStyle = "rgba(0, 0, 0, 0.6)";
  g.lineWidth = 3;
  g.stroke();
  g.fillStyle = fg;
  g.font = "700 40px Inter, Arial, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, w / 2, 32);
  return c;
}

export { texture as canvasTexture };
