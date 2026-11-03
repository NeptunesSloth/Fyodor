/** Geometry of the 2D targeting arrow: a brass cord bowing up from the source to the edge of its target. */

export interface Pt { x: number; y: number }
export interface Box { left: number; top: number; width: number; height: number }

/** Where the line from a box's centre toward ``p`` leaves the box (so the arrowhead stops at the card's edge). */
export function edgePoint(b: Box, p: Pt, pad = 3): Pt {
  const cx = b.left + b.width / 2;
  const cy = b.top + b.height / 2;
  const dx = p.x - cx;
  const dy = p.y - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const hw = b.width / 2 + pad;
  const hh = b.height / 2 + pad;
  const s = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
  return s >= 1 ? { x: p.x, y: p.y } : { x: cx + dx * s, y: cy + dy * s };
}

/** A quadratic curve from a to b whose middle bows up (toward the top of the screen) by a share of its length. */
export function bow(a: Pt, b: Pt, share = 0.18): { d: string; mid: Pt } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // the normal that points up the screen (screen y grows downward)
  let nx = -dy / len;
  let ny = dx / len;
  if (ny > 0) { nx = -nx; ny = -ny; }
  const k = Math.min(140, len * share);
  const c = { x: (a.x + b.x) / 2 + nx * k, y: (a.y + b.y) / 2 + ny * k };
  const r = (n: number) => Math.round(n * 10) / 10;
  return { d: `M${r(a.x)},${r(a.y)} Q${r(c.x)},${r(c.y)} ${r(b.x)},${r(b.y)}`, mid: { x: (a.x + 2 * c.x + b.x) / 4, y: (a.y + 2 * c.y + b.y) / 4 } };
}
