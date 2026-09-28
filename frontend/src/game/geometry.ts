/** Battlefield virtual coordinate space (must match backend/app/game/state.py). */
export const BF_W = 1000;
export const BF_H = 600;
export const CARD_RATIO = 88 / 63;

/** Card width in px for a battlefield of the given pixel size: fits ~13 across and ~3.4 rows. */
export function battlefieldCardWidth(width: number, height: number): number {
  return Math.max(36, Math.min((width / BF_W) * 72, height / 3.4 / CARD_RATIO));
}

/** Pixel position of a card's top-left corner. Opponent battlefields are mirrored vertically. */
export function toPixels(x: number, y: number, width: number, height: number, cardH: number, mirrored: boolean): [number, number] {
  const px = (x / BF_W) * width;
  let py = (y / BF_H) * height;
  if (mirrored) py = height - py - cardH;
  return [px, py];
}

/** Keep relative offsets when a group of cards is dropped: anchor card goes to (x, y). */
export function groupPositions(
  ids: string[],
  anchorId: string,
  target: { x: number; y: number },
  current: Record<string, { x?: number; y?: number } | undefined>,
  sameZone: boolean,
): Record<string, [number, number]> {
  const out: Record<string, [number, number]> = {};
  const anchor = current[anchorId];
  ids.forEach((id, i) => {
    const c = current[id];
    if (sameZone && anchor && c && anchor.x != null && anchor.y != null && c.x != null && c.y != null) {
      out[id] = [target.x + (c.x - anchor.x), target.y + (c.y - anchor.y)];
    } else {
      out[id] = [target.x + i * 18, target.y + i * 18];
    }
  });
  return out;
}
