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

// ------------------------------------------------------------------ attached elsewhere (drawn on the host's board)

/**
 * An Aura, Equipment or Fortification attached to a permanent on ANOTHER player's battlefield (or an Aura enchanting another
 * player, a Curse) is drawn on that board, tucked under its host as one's own attachments are (MTG Arena, and a physical table:
 * you put your Pacifism on their creature). Before, it stayed on its controller's mat, and its line crossed the whole table.
 *
 * Display only: the server's zones, positions and control are untouched. The card stays in its controller's battlefield, so
 * clicking, menus, abilities and permissions are its controller's as ever; it wears its controller's seat colour and initial
 * (game/TableCard.tsx, table3d/tiles.ts) so everyone sees whose it is, and its controller's plaque counts it
 * (game/SeatPlate.tsx). A face-down card is never moved. When the host leaves, the server puts the Aura in a graveyard (or the
 * Equipment stays, unattached): the board just follows the state.
 */
export interface Guest {
  /** The battlefield zone it is drawn on (the host's, or the enchanted player's). */
  board: string;
  /** The card it's attached to; null for an Aura enchanting a player. */
  host: string | null;
}

type ViewCards = Pick<GameView, "cards" | "zones">;

const guestMemo = new WeakMap<object, Map<string, Guest>>();

const isBattlefield = (zone: string | undefined) => !!zone && zone.endsWith(":battlefield");
const playerOf = (zone: string) => zone.slice(0, zone.indexOf(":"));

/** Every card drawn on a battlefield other than its own (cached per view). */
export function guests(view: ViewCards): Map<string, Guest> {
  const known = guestMemo.get(view.cards);
  if (known) return known;
  const out = new Map<string, Guest>();
  for (const c of Object.values(view.cards)) {
    if (!isBattlefield(c.zone) || c.face_down) continue;
    const host = c.attached_to ? view.cards[c.attached_to] : undefined;
    if (host) {
      // no chains: a host that is itself attached elsewhere keeps its attachments where they are
      if (isBattlefield(host.zone) && host.zone !== c.zone && !(host.attached_to && view.cards[host.attached_to])) out.set(c.id, { board: host.zone, host: host.id });
      continue;
    }
    const p = c.attached_player;
    if (p && p !== playerOf(c.zone) && view.zones[`${p}:battlefield`] !== undefined) out.set(c.id, { board: `${p}:battlefield`, host: null });
  }
  guestMemo.set(view.cards, out);
  return out;
}

const boardMemo = new Map<string, string[]>();

/**
 * The cards drawn on a battlefield, bottom to top: its own (less those drawn on another board), with each guest just before
 * (under) its host and Curses first. The zone's own array when no guest touches it, and the same array as last time when
 * nothing changed, so memoised layouts keep working.
 */
export function boardCards(view: ViewCards, zone: string): string[] {
  const own = (view.zones[zone] as string[] | undefined) ?? [];
  const g = guests(view);
  if (!g.size) return own;
  const incoming = new Map<string, string[]>();
  const curses: string[] = [];
  for (const [id, guest] of g) {
    if (guest.board !== zone) continue;
    if (guest.host) incoming.set(guest.host, [...(incoming.get(guest.host) ?? []), id]);
    else curses.push(id);
  }
  const leaving = own.some((id) => g.has(id));
  if (!leaving && !incoming.size && !curses.length) return own;
  const out: string[] = [...curses];
  for (const id of own) {
    if (g.has(id)) continue;
    const tucked = incoming.get(id);
    if (tucked) out.push(...tucked);
    out.push(id);
  }
  const last = boardMemo.get(zone);
  if (last && last.length === out.length && last.every((id, i) => id === out[i])) return last;
  boardMemo.set(zone, out);
  return out;
}

/** The board a battlefield card is drawn on: a guest's host board, else its own zone. */
export function drawnOn(view: ViewCards, id: string): string | undefined {
  return guests(view).get(id)?.board ?? view.cards[id]?.zone;
}

/** The cards a player controls that are drawn on someone else's board (their plaque counts them). */
export function guestsOf(view: ViewCards, player: string): string[] {
  const out: string[] = [];
  for (const id of guests(view).keys()) if (view.cards[id]?.controller === player) out.push(id);
  return out;
}

/** Free placement: where a guest lies on its board (virtual units), tucked under its host as the server tucks one's own (10, −18 a step). */
export function guestSpot(view: ViewCards, id: string, hostAt: (host: string) => [number, number] | null): [number, number] | null {
  const g = guests(view).get(id);
  if (!g) return null;
  if (!g.host) {
    // a Curse: along the front of the enchanted player's mat, by their plaque, one step each
    const k = boardCards(view, g.board).filter((x) => guests(view).get(x)?.host === null).indexOf(id);
    return [12 + Math.max(0, k) * 46, 12];
  }
  const at = hostAt(g.host);
  if (!at) return null;
  // after the host's own attachments (which the server already tucked at these steps), one step further each
  let k = 0;
  for (const c of Object.values(view.cards)) if (c.attached_to === g.host && c.zone === view.cards[g.host]?.zone) k++;
  const mine = boardCards(view, g.board).filter((x) => guests(view).get(x)?.host === g.host).indexOf(id);
  k += Math.max(0, mine);
  return [at[0] + 10 + 10 * k, at[1] - 18 - 14 * k];
}
