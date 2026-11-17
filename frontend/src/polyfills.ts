/**
 * -- old browsers -- what an older Chrome or Edge lacks that the table draws with. The user's offline computer has Edge 92
 * (2021), which can't be updated; the 3D table's canvas labels call roundRect (Chrome 99), and without it the table failed
 * to draw. Imported first by main.tsx; each one only fills in what is missing.
 */

type Radii = number | DOMPointInit | (number | DOMPointInit)[];

const radius = (r: number | DOMPointInit | undefined): number => (typeof r === "number" ? r : r?.x ?? 0);

/** The four corner radii (top left, top right, bottom right, bottom left) from roundRect's 1–4 value forms, kept within the box. */
export function cornerRadii(w: number, h: number, radii: Radii = 0): [number, number, number, number] {
  const list = (Array.isArray(radii) ? radii : [radii]).map(radius);
  const [a = 0, b = a, c = a, d = b] = list;
  const corners: [number, number, number, number] = list.length === 3 ? [a, b, c, b] : [a, b, c, d];
  const scale = Math.min(1, Math.abs(w) / Math.max(1e-9, corners[0] + corners[1], corners[3] + corners[2]),
    Math.abs(h) / Math.max(1e-9, corners[0] + corners[3], corners[1] + corners[2]));
  return corners.map((r) => Math.max(0, r) * scale) as [number, number, number, number];
}

function roundRect(this: CanvasPath, x: number, y: number, w: number, h: number, radii?: Radii): void {
  const [tl, tr, br, bl] = cornerRadii(w, h, radii);
  this.moveTo(x + tl, y);
  this.lineTo(x + w - tr, y);
  this.arcTo(x + w, y, x + w, y + tr, tr);
  this.lineTo(x + w, y + h - br);
  this.arcTo(x + w, y + h, x + w - br, y + h, br);
  this.lineTo(x + bl, y + h);
  this.arcTo(x, y + h, x, y + h - bl, bl);
  this.lineTo(x, y + tl);
  this.arcTo(x, y, x + tl, y, tl);
  this.closePath();
}

const withRoundRect = [
  typeof CanvasRenderingContext2D !== "undefined" ? CanvasRenderingContext2D.prototype : null,
  typeof OffscreenCanvasRenderingContext2D !== "undefined" ? OffscreenCanvasRenderingContext2D.prototype : null,
  typeof Path2D !== "undefined" ? Path2D.prototype : null,
];
for (const proto of withRoundRect) {
  if (proto && typeof (proto as { roundRect?: unknown }).roundRect !== "function") {
    Object.defineProperty(proto, "roundRect", { value: roundRect, writable: true, configurable: true });
  }
}

if (typeof Object.hasOwn !== "function") {
  Object.defineProperty(Object, "hasOwn", { value: (o: object, k: PropertyKey) => Object.prototype.hasOwnProperty.call(o, k), writable: true, configurable: true });
}

for (const proto of [Array.prototype, String.prototype] as { at?: unknown }[]) {
  if (typeof proto.at !== "function") {
    Object.defineProperty(proto, "at", {
      value(this: ArrayLike<unknown>, i: number) {
        const n = Math.trunc(i) || 0;
        const k = n < 0 ? this.length + n : n;
        return k >= 0 && k < this.length ? this[k] : undefined;
      },
      writable: true, configurable: true,
    });
  }
}

const arrays = Array.prototype as unknown as Record<string, unknown>;
if (typeof arrays.findLast !== "function") {
  Object.defineProperty(Array.prototype, "findLast", {
    value(this: unknown[], f: (v: unknown, i: number, a: unknown[]) => unknown) {
      for (let i = this.length - 1; i >= 0; i--) if (f(this[i], i, this)) return this[i];
      return undefined;
    },
    writable: true, configurable: true,
  });
}
if (typeof arrays.findLastIndex !== "function") {
  Object.defineProperty(Array.prototype, "findLastIndex", {
    value(this: unknown[], f: (v: unknown, i: number, a: unknown[]) => unknown) {
      for (let i = this.length - 1; i >= 0; i--) if (f(this[i], i, this)) return i;
      return -1;
    },
    writable: true, configurable: true,
  });
}

if (typeof globalThis.structuredClone !== "function") {
  // (plain game data only: views and settings are JSON)
  (globalThis as { structuredClone?: unknown }).structuredClone = <T,>(v: T): T => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
}
