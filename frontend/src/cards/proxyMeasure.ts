/**
 * Text measuring for the DOM proxy (cards/proxy.ts): the real fonts through one shared 2D canvas once
 * they have loaded, the estimate table before that. Widths are cached per word, in ems.
 */
import { estimateMeasure, fitLabel, type FontRole, type Measure } from "./proxy";

/** The CSS font of each role at 100px (the DOM card and the 3D texture use the same faces). */
export const PROXY_FONTS: Record<FontRole, string> = {
  name: '700 100px Cinzel, Georgia, serif',
  type: '600 100px "Inter Variable", Inter, Arial, sans-serif',
  text: '430 100px "Inter Variable", Inter, Arial, sans-serif',
  stat: '700 100px Cinzel, Georgia, serif',
};

let ctx: CanvasRenderingContext2D | null | undefined;
const cache = new Map<string, number>();
let ready = false;

/** True once the proxy's fonts are loaded (asks the browser to load them the first time). */
export function proxyFontsReady(): boolean {
  if (ready) return true;
  if (typeof document === "undefined" || !document.fonts) return false;
  const fonts = Object.values(PROXY_FONTS);
  ready = fonts.every((f) => document.fonts.check(f));
  if (!ready) for (const f of fonts) void document.fonts.load(f).catch(() => {});
  return ready;
}

/** Resolves when the proxy's fonts have loaded (or failed to). */
export function whenProxyFontsReady(): Promise<void> {
  if (proxyFontsReady() || typeof document === "undefined" || !document.fonts) return Promise.resolve();
  return Promise.all(Object.values(PROXY_FONTS).map((f) => document.fonts.load(f).catch(() => []))).then(() => { ready = true; });
}

const real: Measure = (s, role) => {
  const key = `${role}\u0000${s}`;
  let w = cache.get(key);
  if (w === undefined) {
    ctx!.font = PROXY_FONTS[role];
    w = ctx!.measureText(s).width / 100;
    cache.set(key, w);
  }
  return w;
};

/** The measure to lay out a proxy with now (the DOM card and the 3D texture use the same one). */
export function textMeasure(): Measure {
  if (ctx === undefined) ctx = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
  return ctx && proxyFontsReady() ? real : estimateMeasure;
}

/** The tiny card (battlefield, thumbnails) prints only its name, over up to three lines (11px on a 76px battlefield card). */
export function tinyNameSize(name: string, measure: Measure): number {
  return fitLabel(name, [80], 3, 14.5, 10, measure, "name").size;
}
