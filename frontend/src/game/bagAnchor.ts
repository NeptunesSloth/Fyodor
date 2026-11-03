/** A screen box: where a drawer's bag chits stack (BagDraws.tsx). */
export interface Box { left: number; top: number }
export interface Rect { left: number; top: number; right: number; bottom: number }

export const CHIT_W = 260; // about one chit's width, to keep it on screen
export const CHIT_H = 48; // one chit and the gap under it

/**
 * Where a player's drawn chits go, from their plaque's box: under it when the plaque is in the top half (the opponents'
 * strips, the far seats of the 3D table), beside it on the right when it is low (your own rail), always on screen.
 */
export function bagAnchor(plate: Rect, screen: { width: number; height: number }): Box {
  const low = plate.top > screen.height / 2;
  const left = low ? plate.right + 10 : plate.left;
  const top = low ? plate.top : plate.bottom + 8;
  return {
    left: Math.round(Math.max(8, Math.min(left, screen.width - CHIT_W - 8))),
    top: Math.round(Math.max(52, Math.min(top, screen.height - CHIT_H * 3 - 8))),
  };
}

/**
 * The column moved down, past anything already showing where it would sit (a dice result line on a mat, another drawer's
 * chits), so nothing overlaps. `width`/`height`: the column's size.
 */
export function clearOf(at: Box, width: number, height: number, taken: Rect[]): Box {
  let top = at.top;
  for (let moved = true, guard = 0; moved && guard < 20; guard++) {
    moved = false;
    for (const r of taken) {
      if (at.left < r.right && r.left < at.left + width && top < r.bottom && r.top < top + height) {
        top = Math.round(r.bottom + 6);
        moved = true;
      }
    }
  }
  return { left: at.left, top };
}
