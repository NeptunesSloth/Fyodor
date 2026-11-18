/**
 * Cards in exile this viewer may cast or play right now (Ian Malcolm's cards they don't own, impulse draw, adventure, plot, Hostage
 * Taker …), from the viewer's own rules hints: the server lists only what this viewer may do, so nothing here is anyone else's
 * business. ``exiled_with`` names the card whose "exiled with" link allows it ("Exiled with Ian Malcolm, Chaotician").
 */
import { openMenu, type MenuItem } from "../components/ContextMenu";
import type { GameCard, GameView } from "../types/game";
import { castOrCount, send } from "./rules/intents";
import { rulesMenu } from "./rules/rulesMenu";

export interface ExileCastable { id: string; play: boolean; owner: string; source?: string }

const inExile = (view: GameView, id: string) => (view.cards[id]?.zone ?? "").endsWith(":exile");

export function exileCastables(view: GameView | null): ExileCastable[] {
  const rules = view?.rules;
  if (!view || !rules || rules.paused || !rules.hints.has_priority) return [];
  const h = rules.hints;
  const out: ExileCastable[] = [];
  const seen = new Set<string>();
  for (const [ids, play] of [[h.castable ?? [], false], [h.playable_lands ?? [], true]] as const) {
    for (const id of ids) {
      if (seen.has(id) || !inExile(view, id)) continue;
      seen.add(id);
      out.push({ id, play, owner: view.cards[id]!.zone.split(":")[0]!, ...(h.exiled_with?.[id] ? { source: h.exiled_with[id] } : {}) });
    }
  }
  return out;
}

/** The zones a hint can name a card outside the hand in: flashback and escape (graveyard), impulse draw (exile), Bolas's Citadel (library). */
const ELSEWHERE = new Set(["graveyard", "exile", "library", "foretell"]);

/**
 * -- playtest (nov 16) -- cards in any pile this viewer may cast or play right now, by the engine's own hints: a flashback or escape card in the
 * graveyard (Snapcaster Mage's grant too), an exiled card, the top of the library under Bolas's Citadel. `free`/`alt`: only a cast without
 * paying its mana cost, or only for an alternative cost, is open to it. The graveyard browser said "double-click to put into hand" over a
 * flashback Lightning Bolt; these are marked there and a double-click casts them.
 */
export interface ZoneCastable { id: string; play: boolean; free: boolean; alt: boolean; source?: string }

export function zoneCastables(view: GameView | null): ZoneCastable[] {
  const rules = view?.rules;
  if (!view || !rules || rules.paused || !rules.hints.has_priority) return [];
  const h = rules.hints;
  const cast = new Set(h.castable ?? []);
  const lands = new Set(h.playable_lands ?? []);
  const free = new Set(h.free_castable ?? []);
  const alt = h.alt_castable ?? {};
  const out: ZoneCastable[] = [];
  for (const id of new Set([...cast, ...lands, ...free, ...Object.keys(alt)])) {
    if (!ELSEWHERE.has((view.cards[id]?.zone ?? "").split(":")[1] ?? "")) continue;
    // (free / alt: only that way is open; a card also plainly castable is just castable)
    const plain = cast.has(id) || lands.has(id);
    out.push({ id, play: lands.has(id), free: !plain && free.has(id), alt: !plain && !free.has(id) && id in alt, ...(h.exiled_with?.[id] ? { source: h.exiled_with[id] } : {}) });
  }
  return out;
}

/** How many cards of one pile (an exile, a graveyard, a library's top) this viewer may cast or play now. */
export function castableIn(view: GameView | null, zoneKey: string): number {
  return zoneCastables(view).filter((c) => view?.cards[c.id]?.zone === zoneKey).length;
}

/** Cast it (asking for X first when the spell has X) or play the land. */
export function playFromExile(c: Pick<ExileCastable, "id" | "play">): Promise<boolean> {
  return c.play ? send({ type: "play_land", card_id: c.id }) : castOrCount({ type: "cast_spell", card_id: c.id });
}

type Row = Exclude<MenuItem, "separator">;

/** The card menu's own ways to cast or play `card` from where it lies (flashback, aftermath's half, escape, free, an alternative cost …). */
export function castRows(card: GameCard, view: GameView, me: string): Row[] {
  return rulesMenu(card, view, me).filter((i): i is Row => i !== "separator" && !!i.onClick && !i.disabled && /^(Cast|Play)\b/.test(i.label));
}

/**
 * A double-click on a castable card in a pile: its one way to cast or play it goes straight to the server (which asks for targets and
 * mana); with several (flashback, or escape for another cost) they open as a menu at `at`. False: nothing to cast.
 */
export function castFromZone(card: GameCard, view: GameView, me: string, at: { clientX: number; clientY: number }): boolean {
  const rows = castRows(card, view, me);
  if (!rows.length) return false;
  if (rows.length === 1) rows[0]!.onClick!();
  else openMenu(at, rows, "name" in card && card.name ? card.name : "Cast");
  return true;
}
