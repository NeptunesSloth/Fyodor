/**
 * One small texture atlas (512², with a matching normal map) for every prop on the table and every set piece: leather
 * grain, the page edges of a book block, parchment with a scholar's hand, wood grain, and a plain cell. The leather and
 * wood cells are grey (tinted by each part's vertex colour); the pages and parchment carry their own colour. Drawn once
 * per page load and shared, so it costs one texture for the whole room.
 */
import * as THREE from "three";
import { canvasTexture, rng } from "../textures";

/** Atlas cells as [u, v, width, height] (v up), each inset from its cell's edges so mipmaps don't bleed. */
export const ATLAS = {
  leather: [0.02, 0.52, 0.46, 0.46],
  pages: [0.51, 0.52, 0.23, 0.46],
  plain: [0.77, 0.77, 0.2, 0.2],
  parchment: [0.02, 0.02, 0.46, 0.46],
  wood: [0.52, 0.02, 0.46, 0.46],
} as const;

const SIZE = 512;
let cached: { color: HTMLCanvasElement; height: HTMLCanvasElement } | null = null;

function draw(): { color: HTMLCanvasElement; height: HTMLCanvasElement } {
  const color = document.createElement("canvas");
  color.width = color.height = SIZE;
  const height = document.createElement("canvas");
  height.width = height.height = SIZE;
  const g = color.getContext("2d")!;
  const h = height.getContext("2d")!;
  const rand = rng(4242);
  h.fillStyle = "#808080";
  h.fillRect(0, 0, SIZE, SIZE);

  // -- leather (canvas 0..256, 0..256): grey, blotched, pored and creased
  g.fillStyle = "#d8d8d8";
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 140; i++) {
    const x = rand() * 256, y = rand() * 256, r = 6 + rand() * 26;
    const grd = g.createRadialGradient(x, y, 0, x, y, r);
    const a = 0.05 + rand() * 0.09;
    grd.addColorStop(0, `rgba(40,40,40,${a})`);
    grd.addColorStop(1, "rgba(40,40,40,0)");
    g.fillStyle = grd;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  for (let i = 0; i < 2600; i++) {
    const x = rand() * 256, y = rand() * 256;
    g.fillStyle = `rgba(30,30,30,${0.1 + rand() * 0.2})`;
    g.fillRect(x, y, 1, 1);
    h.fillStyle = "rgba(0,0,0,0.35)";
    h.fillRect(x, y, 1.4, 1.4);
  }
  g.lineCap = h.lineCap = "round";
  for (let i = 0; i < 46; i++) {
    let x = rand() * 256, y = rand() * 256;
    const len = 6 + rand() * 18;
    const ang = rand() * Math.PI * 2;
    g.strokeStyle = `rgba(20,20,20,${0.12 + rand() * 0.16})`;
    g.lineWidth = 0.8;
    h.strokeStyle = "rgba(0,0,0,0.5)";
    h.lineWidth = 1.2;
    g.beginPath(); h.beginPath();
    g.moveTo(x, y); h.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      x += Math.cos(ang + (rand() - 0.5) * 0.9) * len / 4;
      y += Math.sin(ang + (rand() - 0.5) * 0.9) * len / 4;
      g.lineTo(x, y); h.lineTo(x, y);
    }
    g.stroke(); h.stroke();
  }

  // -- page edges (canvas 256..384, 0..256): cream, a fine line per few leaves, grubby toward the boards
  const px0 = 256;
  for (let y = 0; y < 256; y++) {
    const edge = Math.min(y, 255 - y) / 128; // 0 at the boards, 1 in the middle of the block
    const leaf = (y % 3 === 0 ? -14 : 0) + (rand() - 0.5) * 10;
    const grime = (1 - Math.min(1, edge * 3)) * 40;
    const v = 228 + leaf - grime;
    g.fillStyle = `rgb(${v}, ${v - 12}, ${v - 40})`;
    g.fillRect(px0, y, 128, 1);
    if (y % 3 === 0) {
      h.fillStyle = "rgba(0,0,0,0.4)";
      h.fillRect(px0, y, 128, 1);
    }
  }
  for (let i = 0; i < 40; i++) {
    // foxing: a few faint brown spots
    const x = px0 + rand() * 128, y = rand() * 256, r = 1 + rand() * 4;
    g.fillStyle = `rgba(120,80,30,${0.06 + rand() * 0.1})`;
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }

  // -- plain (canvas 384..512, 0..256): white with the faintest tooth
  g.fillStyle = "#f4f4f4";
  g.fillRect(384, 0, 128, 256);
  for (let i = 0; i < 900; i++) {
    g.fillStyle = `rgba(0,0,0,${rand() * 0.05})`;
    g.fillRect(384 + rand() * 128, rand() * 256, 2, 2);
  }

  // -- parchment (canvas 0..256, 256..512): warm, mottled, ruled lines of a scholar's hand
  g.fillStyle = "#e6d3a8";
  g.fillRect(0, 256, 256, 256);
  for (let i = 0; i < 90; i++) {
    const x = rand() * 256, y = 256 + rand() * 256, r = 8 + rand() * 30;
    const grd = g.createRadialGradient(x, y, 0, x, y, r);
    grd.addColorStop(0, `rgba(150,100,40,${0.04 + rand() * 0.07})`);
    grd.addColorStop(1, "rgba(150,100,40,0)");
    g.fillStyle = grd;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  g.fillStyle = "rgba(60,35,20,0.55)";
  for (let row = 0; row < 19; row++) {
    const y = 276 + row * 11.5;
    let x = 18 + (row === 0 ? 30 : 0);
    while (x < 236) {
      const w = 3 + rand() * 13;
      if (x + w > 238) break;
      g.globalAlpha = 0.35 + rand() * 0.4;
      g.fillRect(x, y + (rand() - 0.5) * 1.2, w, 1.6);
      x += w + 2.5 + rand() * 3;
    }
  }
  g.globalAlpha = 1;
  // an illuminated initial
  g.fillStyle = "rgba(140,30,24,0.8)";
  g.fillRect(18, 268, 22, 22);
  g.fillStyle = "rgba(200,160,70,0.9)";
  g.fillRect(22, 272, 14, 14);

  // -- wood grain (canvas 256..512, 256..512): grey grain running along v
  g.fillStyle = "#c8c8c8";
  g.fillRect(256, 256, 256, 256);
  for (let x = 0; x < 256; x++) {
    const ring = Math.sin(x * 0.21 + Math.sin(x * 0.037) * 4) * 0.5 + 0.5;
    const v = 150 + ring * 70 + (rand() - 0.5) * 18;
    g.fillStyle = `rgba(${v},${v},${v},0.55)`;
    g.fillRect(256 + x, 256, 1, 256);
    h.fillStyle = `rgba(${ring > 0.8 ? 0 : 255},${ring > 0.8 ? 0 : 255},${ring > 0.8 ? 0 : 255},0.12)`;
    h.fillRect(256 + x, 256, 1, 256);
  }
  for (let i = 0; i < 14; i++) {
    // knots and streaks
    const x = 256 + rand() * 256, y = 256 + rand() * 256;
    g.strokeStyle = `rgba(60,60,60,${0.15 + rand() * 0.2})`;
    g.lineWidth = 1;
    g.beginPath();
    g.ellipse(x, y, 2 + rand() * 4, 8 + rand() * 18, 0, 0, Math.PI * 2);
    g.stroke();
  }
  return { color, height };
}

/** A tangent-space normal map from a height canvas (Sobel), `strength` steepening it. */
function normalFrom(height: HTMLCanvasElement, strength: number): HTMLCanvasElement {
  const w = height.width, hh = height.height;
  const src = height.getContext("2d")!.getImageData(0, 0, w, hh).data;
  const out = document.createElement("canvas");
  out.width = w;
  out.height = hh;
  const og = out.getContext("2d")!;
  const img = og.createImageData(w, hh);
  const H = (x: number, y: number) => src[(((y + hh) % hh) * w + ((x + w) % w)) * 4]! / 255;
  for (let y = 0; y < hh; y++) {
    for (let x = 0; x < w; x++) {
      const dx = (H(x + 1, y) - H(x - 1, y)) * strength;
      const dy = (H(x, y + 1) - H(x, y - 1)) * strength;
      const n = new THREE.Vector3(-dx, dy, 1).normalize();
      const i = (y * w + x) * 4;
      img.data[i] = (n.x * 0.5 + 0.5) * 255;
      img.data[i + 1] = (n.y * 0.5 + 0.5) * 255;
      img.data[i + 2] = (n.z * 0.5 + 0.5) * 255;
      img.data[i + 3] = 255;
    }
  }
  og.putImageData(img, 0, 0);
  return out;
}

let normalCanvas: HTMLCanvasElement | null = null;

/** The atlas's colour and normal maps (new textures each call, over shared canvases; the caller disposes them). */
export function atlasMaps(): { map: THREE.CanvasTexture; normalMap: THREE.CanvasTexture } {
  cached ??= draw();
  normalCanvas ??= normalFrom(cached.height, 3);
  const map = canvasTexture(cached.color);
  const normalMap = canvasTexture(normalCanvas);
  normalMap.colorSpace = THREE.NoColorSpace;
  return { map, normalMap };
}
