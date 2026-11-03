/**
 * Attachment lines (TABLETOP_QOL_MILESTONE #8): which Aura, Equipment or Fortification is attached to what. A
 * visualization of the server's `attached_to` / `attached_player` (sent only for battlefield cards, so public),
 * drawn by both tables: an SVG line on the 2D table (game/Overlays.tsx), a thin cord on the 3D one
 * (table3d/tethers.ts).
 *
 * Lines show only while either end is hovered or selected. Attachments already sit tucked under their host, so a
 * permanent line on every one would be clutter on a crowded board; the line answers the question when it's asked
 * ("what is this attached to?", "what's on this creature?") and matters most when the two are apart (an Aura on an
 * opponent's creature, or cards moved by hand).
 */
import type { GameView } from "../types/game";

export interface AttachLink {
  /** The attachment. */
  from: string;
  /** What it's attached to: a battlefield card, or a player (an Aura enchanting a player, 702.5d). */
  to: string;
  player?: true;
}

/** No spaghetti: at most this many lines at once (a big marquee selection). */
export const MAX_ATTACH_LINKS = 24;

export function attachmentLinks(view: Pick<GameView, "cards">, focus: Iterable<string | null | undefined>): AttachLink[] {
  const want = new Set<string>();
  for (const id of focus) if (id) want.add(id);
  if (!want.size) return [];
  const out: AttachLink[] = [];
  for (const c of Object.values(view.cards)) {
    if (!c.zone.endsWith(":battlefield")) continue;
    const host = c.attached_to ? view.cards[c.attached_to] : undefined;
    if (host?.zone.endsWith(":battlefield")) {
      if (want.has(c.id) || want.has(host.id)) out.push({ from: c.id, to: host.id });
    } else if (c.attached_player && want.has(c.id)) {
      out.push({ from: c.id, to: c.attached_player, player: true });
    }
    if (out.length >= MAX_ATTACH_LINKS) break;
  }
  return out;
}

/**
 * A card's footprint on the table: centre, half width and height, and its turn `rot` (radians): the card's width runs
 * along (cos rot, sin rot) and its height along (−sin rot, cos rot). A tapped card is turned a quarter.
 */
export interface Footprint { x: number; y: number; hw: number; hh: number; rot: number }

/** How far from a card's centre, going along the unit direction (dx, dy), its edge is. */
function edge(f: Footprint, dx: number, dy: number): number {
  const c = Math.cos(f.rot);
  const s = Math.sin(f.rot);
  const lx = Math.abs(dx * c + dy * s);
  const ly = Math.abs(-dx * s + dy * c);
  return Math.min(lx > 1e-9 ? f.hw / lx : Infinity, ly > 1e-9 ? f.hh / ly : Infinity);
}

/**
 * Where the line leaves the attachment: its centre, unless it's tucked under its host. Then the middle of the sliver
 * that peeks out from under the host, so the line starts on the card you can see rather than on the host's face.
 */
export function tetherAnchor(att: Footprint, host: Footprint): { x: number; y: number } {
  const dx = att.x - host.x;
  const dy = att.y - host.y;
  const d = Math.hypot(dx, dy);
  if (d < 1e-6) return { x: att.x, y: att.y }; // exactly under: nothing peeks out
  const ux = dx / d;
  const uy = dy / d;
  const hostEdge = edge(host, ux, uy);
  const reach = edge(att, ux, uy);
  const near = d - reach;
  const far = d + reach;
  if (near >= hostEdge || far <= hostEdge) return { x: att.x, y: att.y }; // apart, or hidden along this line
  const t = (hostEdge + far) / 2;
  return { x: host.x + ux * t, y: host.y + uy * t };
}
