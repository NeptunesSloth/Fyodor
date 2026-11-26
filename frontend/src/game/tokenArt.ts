/**
 * -- engine token art -- a token the rules engine described ("a 3/3 colorless Robot artifact creature token") has no printing of its
 * own (`card_id` null: its name, P/T and text are the engine's `token`), but the server names a matching token printing that
 * pictures it (`token.art_id`, its picture face `token.art_face`). Only the picture comes from that printing; the card's text and
 * stats stay the token's own.
 */
import type { GameCard } from "../types/game";

/** The printing whose picture stands for this described token, or null (a printed card, a hidden one, or no matching printing). */
export function tokenArtId(card: GameCard | undefined): string | null {
  if (!card || card.hidden || card.card_id || !card.token) return null;
  return card.token.art_id ?? null;
}

/** The picture face of `tokenArtId`'s printing (a double-faced token printing pictures one of its faces). */
export function tokenArtFace(card: GameCard | undefined): number {
  return card && !card.hidden ? card.token?.art_face ?? 0 : 0;
}
