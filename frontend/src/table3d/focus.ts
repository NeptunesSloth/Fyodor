/**
 * Focus (TABLETOP_QOL_MILESTONE #10): the camera keys as a pure step, and how the camera frames the stack or a
 * fight. Camera only, never game state. C zooms to the hovered card, K looks at the stack, X at the current combat;
 * the same key again, or Esc, goes back to the view you had.
 */
import type { GameView } from "../types/game";
import type { GroundBox } from "./arrows";
import type { CameraPreset } from "./TableScene";

/** The close-ups C, K and X open: each returns to the view you came from. */
export function isCloseUp(p: CameraPreset): boolean {
  return typeof p === "object" && ("card" in p || "stack" in p || "combat" in p);
}

/** The cards in the current combat: attackers and the creatures blocking them, on the battlefield. */
export function combatCardIds(view: Pick<GameView, "cards">): string[] {
  const out: string[] = [];
  for (const c of Object.values(view.cards)) {
    if (!c.zone.endsWith(":battlefield")) continue;
    if (c.attacking || c.attacking_without_target || c.blocking || c.blocking_without_attacker) out.push(c.id);
  }
  return out;
}

export interface CamKeyContext {
  me: string;
  /** Seat order. */
  players: string[];
  hover: string | null;
  /** Is this card drawn on the 3D table (a hand card of mine isn't)? */
  onTable: (id: string) => boolean;
  stack: boolean;
  combat: boolean;
  /** The digit pressed, for the player keys 2–6. */
  digit?: number;
  /** cam_focus_player: whose seat (the winner spotlight). */
  player?: string;
}

/**
 * One camera key: the new view, and the view the close-ups return to. Opening a close-up from another close-up
 * keeps the view you started from; a key that has nothing to show (an empty stack) changes nothing.
 */
export function cameraKey(id: string, cur: CameraPreset, back: CameraPreset, ctx: CamKeyContext): { preset: CameraPreset; back: CameraPreset } {
  const others = ctx.players.filter((p) => p !== ctx.me);
  const keep = { preset: cur, back };
  const open = (p: CameraPreset) => ({ preset: p, back: isCloseUp(cur) ? back : cur });
  const toggle = (is: boolean, p: CameraPreset, can: boolean) => (is ? { preset: back, back } : can ? open(p) : keep);
  const obj = typeof cur === "object" ? cur : null;
  switch (id) {
    case "cam_seat":
    case "cam_reset":
      return { preset: "seat", back };
    case "cam_table":
      return { preset: "overview", back };
    case "cam_player": {
      const pid = others[(ctx.digit ?? 0) - 2];
      return pid ? { preset: { focus: pid }, back } : keep;
    }
    case "cam_focus_player": // the winner spotlight turns toward the winning seat (your own seat: your usual view)
      return { preset: ctx.player && ctx.player !== ctx.me && ctx.players.includes(ctx.player) ? { focus: ctx.player } : "seat", back };
    case "cam_focus":
      return toggle(!!obj && "card" in obj, { card: ctx.hover ?? "" }, !!ctx.hover && ctx.onTable(ctx.hover));
    case "cam_stack":
      return toggle(!!obj && "stack" in obj, { stack: true }, ctx.stack);
    case "cam_combat":
      return toggle(!!obj && "combat" in obj, { combat: true }, ctx.combat);
    case "escape":
      return isCloseUp(cur) ? { preset: back, back } : keep;
    default:
      return keep;
  }
}

/**
 * A camera that frames an area of the table from the viewer's side: looking at its middle from `out` (the unit
 * direction toward the viewer's seat), raised by `elevation` (radians), far enough back to see all of it. One card
 * comes out as close as C's card close-up.
 */
export function frameBox(box: GroundBox, out: [number, number], opts: { y?: number; elevation?: number } = {}): { look: [number, number, number]; pos: [number, number, number] } {
  const y = opts.y ?? 0;
  const el = opts.elevation ?? 1.1;
  const cx = (box.minX + box.maxX) / 2;
  const cz = (box.minZ + box.maxZ) / 2;
  const span = Math.max(box.maxX - box.minX, box.maxZ - box.minZ);
  const dist = Math.max(5.8, span * 2.1);
  const flat = Math.cos(el) * dist;
  return { look: [cx, y, cz], pos: [cx + out[0] * flat, y + Math.sin(el) * dist, cz + out[1] * flat] };
}
