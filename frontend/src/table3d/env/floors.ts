/**
 * The ground around the table, per plane: a tiling floor (oak boards, slate flags, worn chapel stones, marble, broken
 * rock, tatami, sand, mossy temple tiles, riveted plates, meadow grass) and the piece set under the table (a rug, a
 * mosaic, a ritual circle...). Drawn on canvases once per page load (1024² for the floor, 1024×768 for the piece under
 * the table, with normal maps from their height), lit by the room (roomShader.ts).
 */
import * as THREE from "three";
import { canvasTexture, rng } from "../textures";

export type FloorKind = "planks" | "slate" | "flagstone" | "marble" | "rock" | "tatami" | "sand" | "mossy" | "plates" | "grass";
export type CentreKind = "rug" | "mosaic" | "ritual" | "meander" | "stones" | "mat" | "dais" | "calendar" | "grate" | "none";

const FLOOR_PX = 1024;
type Ctx = CanvasRenderingContext2D;

function canvas(w: number, h: number): [HTMLCanvasElement, Ctx] {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return [c, c.getContext("2d")!];
}

const rgb = (c: THREE.Color, k = 1, a = 1) => `rgba(${Math.round(Math.min(255, c.r * 255 * k))},${Math.round(Math.min(255, c.g * 255 * k))},${Math.round(Math.min(255, c.b * 255 * k))},${a})`;
/** A colour from an sRGB hex, as the canvas draws it (no linear conversion). */
const srgb = (hex: string) => new THREE.Color().setStyle(hex, THREE.NoColorSpace);
const lerp = (a: THREE.Color, b: THREE.Color, t: number) => a.clone().lerp(b, t);

function blotches(g: Ctx, rand: () => number, w: number, h: number, n: number, color: string, rMin: number, rMax: number, aMax: number): void {
  for (let i = 0; i < n; i++) {
    const x = rand() * w, y = rand() * h, r = rMin + rand() * (rMax - rMin);
    for (const [ox, oy] of [[0, 0], [w, 0], [-w, 0], [0, h], [0, -h]]) {
      const grd = g.createRadialGradient(x + ox!, y + oy!, 0, x + ox!, y + oy!, r);
      grd.addColorStop(0, color.replace("ALPHA", (rand() * aMax).toFixed(3)));
      grd.addColorStop(1, color.replace("ALPHA", "0"));
      g.fillStyle = grd;
      g.fillRect(x + ox! - r, y + oy! - r, r * 2, r * 2);
    }
  }
}

function speckle(g: Ctx, rand: () => number, w: number, h: number, n: number, color: string, aMax: number, size = 1.5): void {
  for (let i = 0; i < n; i++) {
    g.fillStyle = color.replace("ALPHA", (rand() * aMax).toFixed(3));
    g.fillRect(rand() * w, rand() * h, size, size);
  }
}

/** Irregular stone flags in rows (tiling), each with its own tone, chipped edges and worn hollows. */
function flags(g: Ctx, h: Ctx, rand: () => number, W: number, rows: number, base: THREE.Color, joint: THREE.Color, vary: number, jointW: number): void {
  g.fillStyle = rgb(joint);
  g.fillRect(0, 0, W, W);
  h.fillStyle = "#303030";
  h.fillRect(0, 0, W, W);
  const rh = W / rows;
  for (let r = 0; r < rows; r++) {
    let x = -rand() * rh;
    while (x < W) {
      const w = rh * (0.8 + rand() * 1.1);
      const tone = 1 + (rand() - 0.5) * vary;
      const c = base.clone().multiplyScalar(tone);
      for (const ox of [0, W]) {
        const x0 = x - ox + jointW, y0 = r * rh + jointW, ww = Math.min(w, W + ox - x) - jointW * 2, hh = rh - jointW * 2;
        if (ww <= 0) continue;
        g.fillStyle = rgb(c);
        g.beginPath();
        const j = () => (rand() - 0.5) * jointW * 1.6;
        g.moveTo(x0 + j(), y0 + j());
        g.lineTo(x0 + ww + j(), y0 + j());
        g.lineTo(x0 + ww + j(), y0 + hh + j());
        g.lineTo(x0 + j(), y0 + hh + j());
        g.closePath();
        g.fill();
        // worn middle: lighter and smoother; edges darker
        const grd = g.createRadialGradient(x0 + ww / 2, y0 + hh / 2, 0, x0 + ww / 2, y0 + hh / 2, Math.max(ww, hh) * 0.7);
        grd.addColorStop(0, "rgba(255,255,255,0.06)");
        grd.addColorStop(1, "rgba(0,0,0,0.18)");
        g.fillStyle = grd;
        g.fillRect(x0, y0, ww, hh);
        h.fillStyle = `rgb(${150 + Math.round(rand() * 40)},${150},${150})`;
        h.fillRect(x0, y0, ww, hh);
      }
      x += w;
    }
  }
}

/** The tiling floor's colour and height canvases. `a`, `b`: the plane's surface colours (base and grain). */
function drawFloor(kind: FloorKind, a: string, b: string, seed: number): { color: HTMLCanvasElement; height: HTMLCanvasElement } {
  const W = FLOOR_PX;
  const [c, g] = canvas(W, W);
  const [hc, h] = canvas(W, W);
  const rand = rng(seed);
  const A = srgb(a);
  const B = srgb(b);
  h.fillStyle = "#808080";
  h.fillRect(0, 0, W, W);
  switch (kind) {
    case "planks": {
      // long oak boards, ends staggered, each its own tone and grain, dark gaps between
      const boards = 8;
      const bw = W / boards;
      g.fillStyle = rgb(B, 0.5);
      g.fillRect(0, 0, W, W);
      for (let i = 0; i < boards; i++) {
        let y = -rand() * W;
        while (y < W) {
          const len = W * (0.45 + rand() * 0.7);
          const tone = 0.75 + rand() * 0.5;
          const col = lerp(B, A, 0.35 + rand() * 0.5).multiplyScalar(tone);
          const x0 = i * bw + 2, w = bw - 4;
          for (const oy of [0, W]) {
            const y0 = y - oy + 2;
            g.fillStyle = rgb(col);
            g.fillRect(x0, y0, w, len - 4);
            // grain: wavy lines along the board
            for (let k = 0; k < 9; k++) {
              const gx = x0 + rand() * w;
              g.strokeStyle = rgb(B, 0.55 + rand() * 0.3, 0.25 + rand() * 0.3);
              g.lineWidth = 0.6 + rand() * 1.6;
              g.beginPath();
              g.moveTo(gx, y0);
              const amp = 1 + rand() * 4, f = 0.004 + rand() * 0.01, ph = rand() * 6;
              for (let t = 0; t <= len; t += 12) g.lineTo(gx + Math.sin(t * f + ph) * amp, y0 + t);
              g.stroke();
            }
            // a knot or two
            if (rand() < 0.4) {
              const kx = x0 + w * (0.25 + rand() * 0.5), ky = y0 + rand() * len;
              g.fillStyle = rgb(B, 0.45, 0.7);
              g.beginPath();
              g.ellipse(kx, ky, 3 + rand() * 4, 7 + rand() * 9, 0, 0, Math.PI * 2);
              g.fill();
            }
            // worn sheen down the middle, darker toward the gaps
            const grd = g.createLinearGradient(x0, 0, x0 + w, 0);
            grd.addColorStop(0, "rgba(0,0,0,0.28)");
            grd.addColorStop(0.15, "rgba(0,0,0,0)");
            grd.addColorStop(0.85, "rgba(0,0,0,0)");
            grd.addColorStop(1, "rgba(0,0,0,0.3)");
            g.fillStyle = grd;
            g.fillRect(x0, y0, w, len - 4);
            h.fillStyle = "#9a9a9a";
            h.fillRect(x0, y0, w, len - 4);
            // nail heads at the board's ends
            g.fillStyle = "rgba(20,14,10,0.8)";
            for (const ny of [y0 + 10, y0 + len - 16]) for (const nx of [x0 + w * 0.22, x0 + w * 0.78]) g.fillRect(nx, ny, 3, 3);
          }
          // the board's end joint
          g.fillStyle = rgb(B, 0.35);
          g.fillRect(i * bw, ((y + len) % W + W) % W - 2, bw, 3);
          h.fillStyle = "#202020";
          h.fillRect(i * bw, ((y + len) % W + W) % W - 2, bw, 3);
          y += len;
        }
        h.fillStyle = "#202020";
        h.fillRect(i * bw, 0, 3, W);
      }
      blotches(g, rand, W, W, 30, "rgba(0,0,0,ALPHA)", 30, 120, 0.12);
      break;
    }
    case "slate":
      flags(g, h, rand, W, 4, lerp(A, B, 0.3), B.clone().multiplyScalar(0.4), 0.35, 4);
      speckle(g, rand, W, W, 9000, "rgba(255,255,255,ALPHA)", 0.06);
      // a polished sheen streak per flag
      blotches(g, rand, W, W, 24, "rgba(180,190,220,ALPHA)", 40, 140, 0.07);
      break;
    case "flagstone":
      flags(g, h, rand, W, 7, lerp(A, B, 0.25), B.clone().multiplyScalar(0.3), 0.6, 5);
      blotches(g, rand, W, W, 50, "rgba(0,0,0,ALPHA)", 10, 70, 0.22);
      // moss in some joints, cracks
      speckle(g, rand, W, W, 1600, "rgba(70,90,50,ALPHA)", 0.3, 3);
      for (let i = 0; i < 30; i++) {
        let x = rand() * W, y = rand() * W;
        g.strokeStyle = "rgba(10,10,12,0.5)";
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(x, y);
        for (let k = 0; k < 5; k++) { x += (rand() - 0.5) * 40; y += (rand() - 0.5) * 40; g.lineTo(x, y); }
        g.stroke();
      }
      break;
    case "marble": {
      const tiles = 4, tw = W / tiles;
      for (let i = 0; i < tiles; i++) for (let j = 0; j < tiles; j++) {
        const tone = (i + j) % 2 ? 1 : 0.86;
        g.fillStyle = rgb(A, tone);
        g.fillRect(i * tw, j * tw, tw, tw);
      }
      // veins
      for (let k = 0; k < 40; k++) {
        let x = rand() * W, y = rand() * W;
        g.strokeStyle = rgb(B, 0.8, 0.12 + rand() * 0.2);
        g.lineWidth = 0.6 + rand() * 2;
        g.beginPath();
        g.moveTo(x, y);
        const ang = rand() * Math.PI;
        for (let s = 0; s < 14; s++) { x += Math.cos(ang) * 22 + (rand() - 0.5) * 18; y += Math.sin(ang) * 22 + (rand() - 0.5) * 18; g.lineTo(x, y); }
        g.stroke();
      }
      g.fillStyle = rgb(B, 0.6, 0.7);
      for (let i = 0; i <= tiles; i++) { g.fillRect(i * tw - 1, 0, 2, W); g.fillRect(0, i * tw - 1, W, 2); }
      h.fillStyle = "#404040";
      for (let i = 0; i <= tiles; i++) { h.fillRect(i * tw - 1, 0, 3, W); h.fillRect(0, i * tw - 1, W, 3); }
      break;
    }
    case "rock":
      g.fillStyle = rgb(B, 0.8);
      g.fillRect(0, 0, W, W);
      // broken slabs between earth
      for (let i = 0; i < 70; i++) {
        const x = rand() * W, y = rand() * W, r = 30 + rand() * 90;
        const col = lerp(A, B, rand() * 0.6).multiplyScalar(0.8 + rand() * 0.4);
        for (const [ox, oy] of [[0, 0], [W, 0], [-W, 0], [0, W], [0, -W]]) {
          g.fillStyle = rgb(col);
          h.fillStyle = `rgb(${140 + Math.round(rand() * 60)},0,0)`;
          g.beginPath(); h.beginPath();
          const n = 6 + Math.floor(rand() * 4);
          for (let k = 0; k < n; k++) {
            const t = (k / n) * Math.PI * 2;
            const rr = r * (0.65 + rand() * 0.4);
            const px = x + ox! + Math.cos(t) * rr, py = y + oy! + Math.sin(t) * rr * 0.8;
            if (k) { g.lineTo(px, py); h.lineTo(px, py); } else { g.moveTo(px, py); h.moveTo(px, py); }
          }
          g.closePath(); h.closePath(); g.fill(); h.fill();
        }
      }
      speckle(g, rand, W, W, 8000, "rgba(0,0,0,ALPHA)", 0.25, 2);
      speckle(g, rand, W, W, 1500, "rgba(110,160,100,ALPHA)", 0.3, 3);
      break;
    case "tatami": {
      // mats 2:1 in the classic offset layout, woven straw with dark cloth borders
      const u = W / 4;
      const mats: [number, number, number, number][] = [[0, 0, 2, 1], [2, 0, 1, 2], [3, 0, 1, 2], [0, 1, 1, 2], [1, 1, 1, 2], [2, 2, 2, 1], [0, 3, 2, 1], [2, 3, 2, 1]];
      for (const [mx, my, mw, mh] of mats) {
        const x0 = mx * u, y0 = my * u, w = mw * u, hh = mh * u;
        g.fillStyle = rgb(A, 0.95 + rand() * 0.1);
        g.fillRect(x0, y0, w, hh);
        const horiz = mw > mh;
        for (let k = 0; k < (horiz ? hh : w); k += 3) {
          g.fillStyle = rgb(B, 0.9 + rand() * 0.2, 0.25);
          if (horiz) g.fillRect(x0, y0 + k, w, 1); else g.fillRect(x0 + k, y0, 1, hh);
          h.fillStyle = k % 6 ? "#909090" : "#707070";
          if (horiz) h.fillRect(x0, y0 + k, w, 1.5); else h.fillRect(x0 + k, y0, 1.5, hh);
        }
        // the cloth border along the long sides
        g.fillStyle = "rgb(30,26,24)";
        if (horiz) { g.fillRect(x0, y0, w, 10); g.fillRect(x0, y0 + hh - 10, w, 10); } else { g.fillRect(x0, y0, 10, hh); g.fillRect(x0 + w - 10, y0, 10, hh); }
        g.fillStyle = "rgba(0,0,0,0.45)";
        g.fillRect(x0, y0, w, 2); g.fillRect(x0, y0, 2, hh);
      }
      break;
    }
    case "sand":
      g.fillStyle = rgb(A);
      g.fillRect(0, 0, W, W);
      // wind ripples
      for (let y = 0; y < W; y += 2) {
        const v = Math.sin(y * 0.09 + Math.sin(y * 0.013) * 3) * 0.5 + 0.5;
        g.fillStyle = rgb(v > 0.5 ? A : B, 1, 0.08 + v * 0.06);
        g.fillRect(0, y, W, 2);
        h.fillStyle = `rgb(${Math.round(110 + v * 60)},0,0)`;
        h.fillRect(0, y, W, 2);
      }
      blotches(g, rand, W, W, 30, "rgba(90,60,30,ALPHA)", 40, 160, 0.15);
      speckle(g, rand, W, W, 12000, "rgba(255,240,200,ALPHA)", 0.18, 1.5);
      break;
    case "mossy":
      flags(g, h, rand, W, 4, lerp(A, B, 0.35), srgb("#1f2a17"), 0.4, 9);
      blotches(g, rand, W, W, 60, "rgba(60,95,40,ALPHA)", 20, 110, 0.4);
      speckle(g, rand, W, W, 4000, "rgba(90,130,60,ALPHA)", 0.4, 3);
      break;
    case "plates": {
      const tiles = 4, tw = W / tiles;
      for (let i = 0; i < tiles; i++) for (let j = 0; j < tiles; j++) {
        const x0 = i * tw, y0 = j * tw;
        g.fillStyle = rgb(A, 0.8 + rand() * 0.4);
        g.fillRect(x0 + 3, y0 + 3, tw - 6, tw - 6);
        // brushed streaks, oil stains, rivets
        for (let k = 0; k < 40; k++) { g.fillStyle = `rgba(255,255,255,${rand() * 0.04})`; g.fillRect(x0 + 3, y0 + rand() * tw, tw - 6, 1); }
        for (const [rx, ry] of [[12, 12], [tw - 18, 12], [12, tw - 18], [tw - 18, tw - 18]]) {
          g.fillStyle = "rgba(200,210,200,0.5)";
          g.beginPath(); g.arc(x0 + rx! + 3, y0 + ry! + 3, 4, 0, Math.PI * 2); g.fill();
          h.fillStyle = "#e0e0e0";
          h.beginPath(); h.arc(x0 + rx! + 3, y0 + ry! + 3, 4, 0, Math.PI * 2); h.fill();
        }
        h.fillStyle = "#202020";
        h.fillRect(x0, y0, tw, 3); h.fillRect(x0, y0, 3, tw);
      }
      g.fillStyle = "rgba(10,14,10,0.9)";
      for (let i = 0; i <= tiles; i++) { g.fillRect(i * tw - 3, 0, 6, W); g.fillRect(0, i * tw - 3, W, 6); }
      blotches(g, rand, W, W, 26, "rgba(20,40,20,ALPHA)", 30, 120, 0.5);
      break;
    }
    case "grass":
      g.fillStyle = rgb(B);
      g.fillRect(0, 0, W, W);
      blotches(g, rand, W, W, 50, "rgba(120,150,60,ALPHA)", 40, 160, 0.3);
      for (let i = 0; i < 26000; i++) {
        const x = rand() * W, y = rand() * W;
        const col = lerp(A, B, rand()).multiplyScalar(0.8 + rand() * 0.6);
        g.strokeStyle = rgb(col, 1, 0.7);
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(x, y);
        g.lineTo(x + (rand() - 0.5) * 4, y - 3 - rand() * 7);
        g.stroke();
      }
      // clover and tiny flowers
      for (let i = 0; i < 160; i++) {
        g.fillStyle = rand() < 0.5 ? "rgba(250,240,200,0.8)" : "rgba(230,200,90,0.8)";
        g.beginPath(); g.arc(rand() * W, rand() * W, 1.5 + rand() * 1.5, 0, Math.PI * 2); g.fill();
      }
      speckle(h, rand, W, W, 20000, "rgba(255,255,255,ALPHA)", 0.5, 2);
      break;
  }
  return { color: c, height: hc };
}

function normalFrom(height: HTMLCanvasElement, strength: number): HTMLCanvasElement {
  const w = height.width, hh = height.height;
  const src = height.getContext("2d")!.getImageData(0, 0, w, hh).data;
  const [out, og] = canvas(w, hh);
  const img = og.createImageData(w, hh);
  const H = (x: number, y: number) => src[(((y + hh) % hh) * w + ((x + w) % w)) * 4]! / 255;
  for (let y = 0; y < hh; y++) {
    for (let x = 0; x < w; x++) {
      const dx = (H(x + 1, y) - H(x - 1, y)) * strength;
      const dy = (H(x, y + 1) - H(x, y - 1)) * strength;
      const l = Math.hypot(dx, dy, 1);
      const i = (y * w + x) * 4;
      img.data[i] = (-dx / l * 0.5 + 0.5) * 255;
      img.data[i + 1] = (dy / l * 0.5 + 0.5) * 255;
      img.data[i + 2] = (1 / l * 0.5 + 0.5) * 255;
      img.data[i + 3] = 255;
    }
  }
  og.putImageData(img, 0, 0);
  return out;
}

const floorCache = new Map<string, { color: HTMLCanvasElement; normal: HTMLCanvasElement }>();

/** The floor's maps (shared canvases, new textures: the caller disposes them), repeating every tile. */
export function floorMaps(kind: FloorKind, a: string, b: string): { map: THREE.CanvasTexture; normalMap: THREE.CanvasTexture } {
  const key = `${kind}|${a}|${b}`;
  let c = floorCache.get(key);
  if (!c) {
    const d = drawFloor(kind, a, b, 1234 + kind.length * 31);
    c = { color: d.color, normal: normalFrom(d.height, 2.5) };
    floorCache.set(key, c);
  }
  const map = canvasTexture(c.color);
  const normalMap = canvasTexture(c.normal);
  normalMap.colorSpace = THREE.NoColorSpace;
  for (const t of [map, normalMap]) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return { map, normalMap };
}

// ------------------------------------------------------------------ the piece under the table

const CW = 1024;
const CH = 768;

function ring(g: Ctx, cx: number, cy: number, r: number, w: number, color: string): void {
  g.strokeStyle = color;
  g.lineWidth = w;
  g.beginPath();
  g.arc(cx, cy, r, 0, Math.PI * 2);
  g.stroke();
}

/** A border of repeated motifs along a rectangle's edge. */
function motifBorder(x: number, y: number, w: number, h: number, step: number, draw: (cx: number, cy: number, ang: number) => void): void {
  for (let t = x + step / 2; t < x + w; t += step) { draw(t, y, 0); draw(t, y + h, Math.PI); }
  for (let t = y + step / 2; t < y + h; t += step) { draw(x, t, -Math.PI / 2); draw(x + w, t, Math.PI / 2); }
}

function drawCentre(kind: CentreKind, accent: string, seed: number): { color: HTMLCanvasElement; height: HTMLCanvasElement } {
  const [c, g] = canvas(CW, CH);
  const [hc, h] = canvas(CW, CH);
  const rand = rng(seed);
  h.fillStyle = "#808080";
  h.fillRect(0, 0, CW, CH);
  const ACC = srgb(accent);
  const cx = CW / 2, cy = CH / 2;
  switch (kind) {
    case "rug": {
      // a hand-knotted rug: a madder-red field, indigo borders with a running vine, a central medallion, fringe
      const field = "#4e1a16", deep = "#2c0e0e", indigo = "#18202f", ivory = "#8e7d5e", gold = "#7a5c2e";
      g.clearRect(0, 0, CW, CH);
      const fx = 34, fy = 10; // the fringe runs along the short ends
      g.fillStyle = indigo;
      g.fillRect(fx, fy, CW - fx * 2, CH - fy * 2);
      g.fillStyle = ivory;
      g.fillRect(fx + 18, fy + 18, CW - fx * 2 - 36, CH - fy * 2 - 36);
      g.fillStyle = indigo;
      g.fillRect(fx + 24, fy + 24, CW - fx * 2 - 48, CH - fy * 2 - 48);
      // the main border's vine
      g.strokeStyle = gold;
      g.lineWidth = 3;
      const bx = fx + 24, by = fy + 24, bw = CW - fx * 2 - 48, bh = CH - fy * 2 - 48;
      motifBorder(bx + 30, by + 30, bw - 60, bh - 60, 46, (x, y, ang) => {
        g.save(); g.translate(x, y); g.rotate(ang);
        g.fillStyle = field; g.beginPath(); g.moveTo(0, -12); g.lineTo(10, 0); g.lineTo(0, 12); g.lineTo(-10, 0); g.closePath(); g.fill();
        g.fillStyle = ivory; g.beginPath(); g.arc(0, 0, 3.5, 0, Math.PI * 2); g.fill();
        g.strokeStyle = gold; g.beginPath(); g.moveTo(-23, 4); g.quadraticCurveTo(-12, 16, 0, 12); g.quadraticCurveTo(12, 8, 23, 4); g.stroke();
        g.restore();
      });
      g.fillStyle = ivory;
      g.fillRect(bx + 58, by + 58, bw - 116, bh - 116);
      // the field
      const ix = bx + 64, iy = by + 64, iw = bw - 128, ih = bh - 128;
      g.fillStyle = field;
      g.fillRect(ix, iy, iw, ih);
      // a lattice of small guls over the field
      for (let x = ix + 30; x < ix + iw; x += 60) for (let y = iy + 30; y < iy + ih; y += 52) {
        g.fillStyle = deep;
        g.beginPath(); g.moveTo(x, y - 14); g.lineTo(x + 18, y); g.lineTo(x, y + 14); g.lineTo(x - 18, y); g.closePath(); g.fill();
        g.fillStyle = "rgba(217,196,154,0.55)";
        g.fillRect(x - 2, y - 2, 4, 4);
      }
      // the medallion and its corner quarters
      const med = (x: number, y: number, rx: number, ry: number) => {
        g.fillStyle = indigo; g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = ivory; g.beginPath(); g.ellipse(x, y, rx * 0.86, ry * 0.86, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = field; g.beginPath(); g.ellipse(x, y, rx * 0.78, ry * 0.78, 0, 0, Math.PI * 2); g.fill();
        for (let k = 0; k < 16; k++) {
          const t = (k / 16) * Math.PI * 2;
          g.fillStyle = k % 2 ? gold : indigo;
          g.beginPath(); g.ellipse(x + Math.cos(t) * rx * 0.55, y + Math.sin(t) * ry * 0.55, 10, 6, t, 0, Math.PI * 2); g.fill();
        }
        g.fillStyle = gold; g.beginPath(); g.ellipse(x, y, rx * 0.22, ry * 0.22, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = deep; g.beginPath(); g.ellipse(x, y, rx * 0.12, ry * 0.12, 0, 0, Math.PI * 2); g.fill();
      };
      med(cx, cy, 170, 130);
      g.save(); g.beginPath(); g.rect(ix, iy, iw, ih); g.clip();
      for (const [x, y] of [[ix, iy], [ix + iw, iy], [ix, iy + ih], [ix + iw, iy + ih]]) med(x!, y!, 120, 90);
      g.restore();
      // the knotted pile: fine noise, and wear down the middle where feet go
      speckle(g, rand, CW, CH, 60000, "rgba(0,0,0,ALPHA)", 0.18, 1.5);
      speckle(g, rand, CW, CH, 20000, "rgba(255,240,210,ALPHA)", 0.08, 1.5);
      speckle(h, rand, CW, CH, 80000, "rgba(255,255,255,ALPHA)", 0.6, 1.5);
      const wear = g.createRadialGradient(cx, cy, 40, cx, cy, 420);
      wear.addColorStop(0, "rgba(255,230,200,0.07)");
      wear.addColorStop(1, "rgba(0,0,0,0.12)");
      g.fillStyle = wear;
      g.fillRect(fx, fy, CW - fx * 2, CH - fy * 2);
      // fringe
      for (const x0 of [0, CW - fx]) for (let y = fy + 4; y < CH - fy - 4; y += 5) {
        g.strokeStyle = `rgba(120,104,80,${0.35 + rand() * 0.3})`;
        g.lineWidth = 1.2;
        g.beginPath();
        const inner = x0 === 0 ? fx : CW - fx;
        g.moveTo(inner, y);
        g.lineTo(x0 === 0 ? 4 + rand() * 8 : CW - 4 - rand() * 8, y + (rand() - 0.5) * 6);
        g.stroke();
      }
      break;
    }
    case "mosaic": {
      // a guildhall floor: a great circle of slate and silver tesserae, rings of script, a compass star
      g.fillStyle = "rgba(0,0,0,0)";
      g.clearRect(0, 0, CW, CH);
      const R = CH * 0.48;
      const tess = (r0: number, r1: number, cols: string[]) => {
        for (let r = r0; r < r1; r += 9) {
          const n = Math.floor((Math.PI * 2 * r) / 9);
          for (let k = 0; k < n; k++) {
            const t = (k / n) * Math.PI * 2;
            g.fillStyle = cols[Math.floor(rand() * cols.length)]!;
            g.fillRect(cx + Math.cos(t) * r * 1.33 - 3.5, cy + Math.sin(t) * r - 3.5, 7, 7);
          }
        }
      };
      g.save(); g.scale(1, 1);
      tess(R * 0.86, R, ["#2b3346", "#323b52", "#262d3e"]);
      tess(R * 0.8, R * 0.86, ["#9aa6c2", "#b7c3d9", "#8691ad"]);
      tess(R * 0.25, R * 0.8, ["#1d2232", "#222839", "#1a1f2d", "#252b3d"]);
      g.restore();
      // a silver compass star
      g.fillStyle = "rgba(183,195,217,0.55)";
      for (let k = 0; k < 8; k++) {
        const t = (k / 8) * Math.PI * 2, l = k % 2 ? R * 0.45 : R * 0.72;
        g.beginPath();
        g.moveTo(cx, cy);
        g.lineTo(cx + Math.cos(t - 0.09) * R * 0.18 * 1.33, cy + Math.sin(t - 0.09) * R * 0.18);
        g.lineTo(cx + Math.cos(t) * l * 1.33, cy + Math.sin(t) * l);
        g.lineTo(cx + Math.cos(t + 0.09) * R * 0.18 * 1.33, cy + Math.sin(t + 0.09) * R * 0.18);
        g.closePath();
        g.fill();
      }
      g.save(); g.translate(cx, cy); g.scale(1.33, 1);
      ring(g, 0, 0, R * 0.8, 3, rgb(ACC, 1, 0.8));
      ring(g, 0, 0, R * 0.25, 3, rgb(ACC, 1, 0.8));
      g.restore();
      speckle(h, rand, CW, CH, 40000, "rgba(0,0,0,ALPHA)", 0.5, 2);
      break;
    }
    case "ritual": {
      // a chapel's floor: a worn runner of faded crimson, a silver warding circle inlaid in the stone under it
      g.clearRect(0, 0, CW, CH);
      g.save(); g.translate(cx, cy); g.scale(1.33, 1);
      const R = CH * 0.47;
      ring(g, 0, 0, R, 10, "rgba(170,180,195,0.55)");
      ring(g, 0, 0, R * 0.9, 3, "rgba(170,180,195,0.45)");
      for (let k = 0; k < 12; k++) {
        const t = (k / 12) * Math.PI * 2;
        g.save(); g.rotate(t); g.translate(R * 0.95, 0);
        g.strokeStyle = "rgba(170,180,195,0.5)"; g.lineWidth = 3;
        g.beginPath(); g.moveTo(-10, -12); g.lineTo(0, 12); g.lineTo(10, -12); g.moveTo(-14, 0); g.lineTo(14, 0); g.stroke();
        g.restore();
      }
      g.restore();
      // the runner
      const rx = cx - 160, rw = 320;
      g.fillStyle = "#2e0c10";
      g.fillRect(rx, 0, rw, CH);
      g.fillStyle = "#43141a";
      g.fillRect(rx + 14, 0, rw - 28, CH);
      g.fillStyle = "rgba(150,120,80,0.45)";
      g.fillRect(rx + 22, 0, 3, CH); g.fillRect(rx + rw - 25, 0, 3, CH);
      // a faded lozenge pattern down its length
      for (let y = 20; y < CH; y += 64) {
        g.strokeStyle = "rgba(150,110,70,0.25)";
        g.lineWidth = 3;
        g.beginPath(); g.moveTo(cx, y); g.lineTo(cx + 60, y + 32); g.lineTo(cx, y + 64); g.lineTo(cx - 60, y + 32); g.closePath(); g.stroke();
      }
      blotches(g, rand, CW, CH, 40, "rgba(0,0,0,ALPHA)", 30, 140, 0.3);
      speckle(g, rand, CW, CH, 40000, "rgba(0,0,0,ALPHA)", 0.2, 1.5);
      speckle(h, rand, CW, CH, 50000, "rgba(255,255,255,ALPHA)", 0.5, 1.5);
      break;
    }
    case "meander": {
      // a temple's inlay: a gold Greek-key band round a field of dark Nyx-blue marble flecked with stars
      g.clearRect(0, 0, CW, CH);
      const m = 30;
      g.fillStyle = "#7a6230";
      g.fillRect(m, m, CW - m * 2, CH - m * 2);
      g.fillStyle = "#8c8678";
      g.fillRect(m + 8, m + 8, CW - m * 2 - 16, CH - m * 2 - 16);
      // the key pattern
      g.strokeStyle = "#6a5222";
      g.lineWidth = 6;
      const key = (x: number, y: number, ang: number) => {
        g.save(); g.translate(x, y); g.rotate(ang);
        g.beginPath(); g.moveTo(-18, 14); g.lineTo(-18, -14); g.lineTo(14, -14); g.lineTo(14, 6); g.lineTo(-6, 6); g.lineTo(-6, -4); g.lineTo(4, -4);
        g.moveTo(-18, 14); g.lineTo(22, 14);
        g.stroke(); g.restore();
      };
      motifBorder(m + 30, m + 30, CW - m * 2 - 60, CH - m * 2 - 60, 44, key);
      g.fillStyle = "#7a6230";
      g.fillRect(m + 56, m + 56, CW - m * 2 - 112, CH - m * 2 - 112);
      g.fillStyle = "#18183a";
      g.fillRect(m + 62, m + 62, CW - m * 2 - 124, CH - m * 2 - 124);
      blotches(g, rand, CW, CH, 30, "rgba(90,70,180,ALPHA)", 30, 120, 0.25);
      for (let i = 0; i < 500; i++) {
        const x = m + 70 + rand() * (CW - m * 2 - 140), y = m + 70 + rand() * (CH - m * 2 - 140);
        g.fillStyle = `rgba(240,230,255,${0.3 + rand() * 0.7})`;
        g.fillRect(x, y, rand() < 0.1 ? 3 : 1.5, rand() < 0.1 ? 3 : 1.5);
      }
      h.fillStyle = "#404040";
      h.fillRect(m, m, CW - m * 2, 8);
      break;
    }
    case "mat": {
      // a great woven mat with a dark brocade border and the house crest's ring
      g.clearRect(0, 0, CW, CH);
      g.fillStyle = "#1c1416";
      g.fillRect(20, 20, CW - 40, CH - 40);
      g.fillStyle = "#857552";
      g.fillRect(54, 54, CW - 108, CH - 108);
      for (let y = 54; y < CH - 54; y += 3) {
        g.fillStyle = `rgba(120,100,60,${0.15 + rand() * 0.15})`;
        g.fillRect(54, y, CW - 108, 1);
        h.fillStyle = y % 6 ? "#909090" : "#606060";
        h.fillRect(54, y, CW - 108, 1.5);
      }
      motifBorder(37, 37, CW - 74, CH - 74, 34, (x, y) => {
        g.fillStyle = "#6a2420"; g.beginPath(); g.arc(x, y, 4.5, 0, Math.PI * 2); g.fill();
        g.fillStyle = "#9a7a3a"; g.beginPath(); g.arc(x, y, 1.8, 0, Math.PI * 2); g.fill();
      });
      g.save(); g.translate(cx, cy); g.scale(1.33, 1);
      ring(g, 0, 0, 150, 12, "rgba(168,50,42,0.55)");
      ring(g, 0, 0, 128, 3, "rgba(168,50,42,0.5)");
      g.restore();
      break;
    }
    case "dais": {
      // a sandstone dais inlaid with lapis bands and gold
      g.clearRect(0, 0, CW, CH);
      g.fillStyle = "#86683e";
      g.fillRect(16, 16, CW - 32, CH - 32);
      for (let y = 16; y < CH - 16; y += 96) for (let x = 16 + ((y / 96) % 2) * 64; x < CW - 16; x += 128) {
        g.strokeStyle = "rgba(80,55,30,0.5)"; g.lineWidth = 2; g.strokeRect(x, y, 128, 96);
      }
      g.fillStyle = "#24479a";
      g.fillRect(40, 40, CW - 80, 22); g.fillRect(40, CH - 62, CW - 80, 22); g.fillRect(40, 40, 22, CH - 80); g.fillRect(CW - 62, 40, 22, CH - 80);
      g.fillStyle = "#e3b04b";
      for (let x = 50; x < CW - 50; x += 30) { g.fillRect(x, 47, 12, 8); g.fillRect(x, CH - 55, 12, 8); }
      blotches(g, rand, CW, CH, 30, "rgba(60,40,20,ALPHA)", 30, 140, 0.25);
      speckle(g, rand, CW, CH, 30000, "rgba(255,230,190,ALPHA)", 0.12, 1.5);
      h.fillStyle = "#606060";
      h.fillRect(40, 40, CW - 80, 22);
      break;
    }
    case "calendar": {
      // a carved stone sun-disc, the jungle creeping over its rim
      g.clearRect(0, 0, CW, CH);
      g.save(); g.translate(cx, cy); g.scale(1.33, 1);
      const R = CH * 0.47;
      g.fillStyle = "#6e6a55"; g.beginPath(); g.arc(0, 0, R, 0, Math.PI * 2); g.fill();
      for (const [r, w] of [[R * 0.95, 6], [R * 0.75, 5], [R * 0.45, 5], [R * 0.2, 4]] as const) ring(g, 0, 0, r, w, "rgba(30,28,20,0.7)");
      for (let k = 0; k < 20; k++) {
        const t = (k / 20) * Math.PI * 2;
        g.save(); g.rotate(t);
        g.fillStyle = "rgba(30,28,20,0.6)"; g.fillRect(R * 0.78, -8, R * 0.14, 16);
        g.fillStyle = "rgba(232,181,58,0.55)"; g.fillRect(R * 0.5, -4, R * 0.2, 8);
        g.restore();
      }
      g.restore();
      blotches(g, rand, CW, CH, 60, "rgba(60,100,40,ALPHA)", 20, 90, 0.5);
      speckle(h, rand, CW, CH, 40000, "rgba(0,0,0,ALPHA)", 0.6, 2);
      break;
    }
    case "grate": {
      // a vent of porcelain-white ribs over a glowing oil-green pit
      g.clearRect(0, 0, CW, CH);
      g.save(); g.translate(cx, cy); g.scale(1.33, 1);
      const R = CH * 0.46;
      const grd = g.createRadialGradient(0, 0, 0, 0, 0, R);
      grd.addColorStop(0, "rgba(90,200,80,0.55)");
      grd.addColorStop(0.7, "rgba(20,60,22,0.6)");
      grd.addColorStop(1, "rgba(0,0,0,0)");
      g.fillStyle = grd; g.beginPath(); g.arc(0, 0, R, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "#5e625a"; g.lineWidth = 12;
      for (let k = 0; k < 14; k++) {
        const t = (k / 14) * Math.PI * 2;
        g.beginPath(); g.moveTo(Math.cos(t) * R * 0.15, Math.sin(t) * R * 0.15);
        g.quadraticCurveTo(Math.cos(t + 0.3) * R * 0.6, Math.sin(t + 0.3) * R * 0.6, Math.cos(t + 0.15) * R, Math.sin(t + 0.15) * R);
        g.stroke();
      }
      ring(g, 0, 0, R, 16, "#6a6e64");
      g.restore();
      break;
    }
    case "stones":
    case "none":
      g.clearRect(0, 0, CW, CH);
      break;
  }
  return { color: c, height: hc };
}

const centreCache = new Map<string, { color: HTMLCanvasElement; normal: HTMLCanvasElement }>();

export function centreMaps(kind: CentreKind, accent: string): { map: THREE.CanvasTexture; normalMap: THREE.CanvasTexture } {
  const key = `${kind}|${accent}`;
  let c = centreCache.get(key);
  if (!c) {
    const d = drawCentre(kind, accent, 99 + kind.length);
    c = { color: d.color, normal: normalFrom(d.height, 1.5) };
    centreCache.set(key, c);
  }
  const map = canvasTexture(c.color);
  const normalMap = canvasTexture(c.normal);
  normalMap.colorSpace = THREE.NoColorSpace;
  return { map, normalMap };
}
