/** What happens when cards are dropped somewhere: shared by the 2D table, the hand and the 3D table. */
import { useGame } from "../state/gameStore";
import { splitZone } from "../types/game";
import { moveCards, send } from "./actions";
import type { DropResult } from "./dnd";
import { groupPositions } from "./geometry";
import { dropFromHand } from "./handDrop";

/** Drop `ids` (dragged by `anchorId`) on `target`. Rules intents first when automation is on. */
export function dropCards(ids: string[], anchorId: string, target: DropResult | null): void {
  if (!target) return;
  const view = useGame.getState().view;
  if (!view) return;
  if (dropFromHand(ids, target)) return; // automation on: a card from my hand plays (Alt: by hand)
  const anchor = view.cards[anchorId];
  const { zone, player } = splitZone(target.zone);
  if (zone === "battlefield" && target.x != null && target.y != null) {
    const same = !!anchor && target.zone === anchor.zone;
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
