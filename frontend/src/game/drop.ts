/** What happens when cards are dropped somewhere: shared by the 2D table, the hand and the 3D table. */
import { useGame } from "../state/gameStore";
import { isVisible, splitZone, type GameCard } from "../types/game";
import { moveCards, send } from "./actions";
import type { DropResult } from "./dnd";
import { groupPositions } from "./geometry";
import { dropFromHand } from "./handDrop";
import { guests } from "./attachments";
import { toast } from "../components/Toasts";

/** Drop `ids` (dragged by `anchorId`) on `target`. Rules intents first when automation is on. */
export function dropCards(ids: string[], anchorId: string, target: DropResult | null): void {
  if (!target) return;
  const view = useGame.getState().view;
  if (!view) return;
  if (dropFromHand(ids, target)) return; // automation on: a card from my hand plays (Alt: by hand)
  const anchor = view.cards[anchorId];
  const { zone, player } = splitZone(target.zone);
  // -- attached elsewhere -- my Aura drawn under your creature (game/attachments.ts): let go on your board, it springs back
  // under its host (never a move onto your battlefield, which would hand it to you); pulled back onto my own board, it comes off
  const away = guests(view);
  const guest = away.get(anchorId);
  if (guest && target.zone === guest.board && anchor?.zone !== target.zone) return;
  if (zone === "battlefield" && target.x != null && target.y != null) {
    const same = !!anchor && target.zone === anchor.zone;
    const off = same ? ids.filter((id) => away.has(id) && view.cards[id]?.zone === target.zone) : [];
    if (off.length) {
      void send({ type: "detach", card_ids: off });
      toast(off.length === 1 ? `${nameOf(view.cards[off[0]!])}: detached` : `${off.length} cards detached`, "info");
    }
    const positions = groupPositions(ids, anchorId, { x: target.x, y: target.y }, view.cards, same);
    useGame.getState().setPending(positions);
    if (same) {
      void send({ type: "set_position", moves: ids.map((cid) => [cid, ...positions[cid]!]) });
    } else {
      void moveCards(ids, "battlefield", { player, x: target.x, y: target.y });
    }
    return;
  }
  void moveCards(ids, zone, { player, position: target.position, index: target.index });
}

const nameOf = (c: GameCard | undefined) => (c && isVisible(c) ? c.name : "Card");
