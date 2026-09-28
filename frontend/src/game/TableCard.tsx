import { memo } from "react";
import { openMenu } from "../components/ContextMenu";
import { useGame, useCardView } from "../state/gameStore";
import { isVisible, splitZone } from "../types/game";
import { moveCards, send, tapCards, targetsFor } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag, type DropResult } from "./dnd";
import { groupPositions } from "./geometry";
import { CounterBadges, GameCardFace } from "./GameCardFace";

interface Props {
  id: string;
  left: number;
  top: number;
  width: number;
  me: string;
  z: number;
}

/** A permanent on a battlefield: positioned, tappable, draggable, with counters and markers. */
export const TableCard = memo(function TableCard({ id, left, top, width, me, z }: Props) {
  const card = useCardView(id);
  const selected = useGame((s) => s.selection.includes(id));
  if (!card) return null;
  const visible = isVisible(card);
  const rotation = (card.tapped ? 90 : 0) + (card.flipped ? 180 : 0);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const store = useGame.getState();
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      store.select([id], "toggle");
      return;
    }
    if (!store.selection.includes(id)) store.select([id]);
    const ids = targetsFor(id);
    beginPointerDrag(e, { ids, from: card.zone, width, onDrop: (t) => onDrop(ids, t) });
  };

  const onDrop = (ids: string[], target: DropResult | null) => {
    if (!target) return;
    const view = useGame.getState().view;
    if (!view) return;
    const { zone } = splitZone(target.zone);
    if (zone === "battlefield" && target.x != null && target.y != null) {
      const same = target.zone === card.zone;
      const positions = groupPositions(ids, id, { x: target.x, y: target.y }, view.cards, same);
      useGame.getState().setPending(positions);
      if (same) {
        void send({ type: "set_position", moves: ids.map((cid) => [cid, ...positions[cid]!]) });
      } else {
        void moveCards(ids, "battlefield", { player: splitZone(target.zone).player, x: target.x, y: target.y });
      }
      return;
    }
    const player = splitZone(target.zone).player;
    void moveCards(ids, zone, { player, position: target.position, index: target.index });
  };

  return (
    <div
      className={`table-card ${selected ? "selected" : ""} ${card.attacking ? "attacking" : ""} ${card.blocking ? "blocking" : ""}`}
      data-card-id={id}
      data-tapped={card.tapped ? "" : undefined}
      style={{ left, top, width, zIndex: z, transform: rotation ? `rotate(${rotation}deg)` : undefined }}
      onPointerDown={onPointerDown}
      onDoubleClick={(e) => {
        e.stopPropagation();
        void tapCards(targetsFor(id));
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const store = useGame.getState();
        if (!store.selection.includes(id)) store.select([id]);
        const view = store.view;
        if (!view) return;
        const { title, items } = cardMenu(card, view, me);
        openMenu(e, items, title);
      }}
      onPointerEnter={() => useGame.getState().setHover(id)}
      onPointerLeave={() => useGame.getState().hover === id && useGame.getState().setHover(null)}
    >
      <GameCardFace card={card} />
      <div className="card-marks">
        {visible && card.is_token && !card.copy_of && <span className="mark token">TOKEN</span>}
        {visible && card.copy_of && <span className="mark copy" title={`Copy of ${card.copy_of.source_name}${card.copy_of.modifications ? ` — ${card.copy_of.modifications}` : ""}`}>COPY</span>}
        {visible && card.commander_key && <span className="mark cmdr" title="Commander">♛</span>}
        {visible && card.note && <span className="mark note" title={card.note}>✎</span>}
        {card.attacking && <span className="mark atk" title="Attacking">⚔</span>}
        {card.blocking && <span className="mark blk" title="Blocking">⛨</span>}
      </div>
      <CounterBadges counters={card.counters} />
    </div>
  );
});

/** Right-click menu for moving a whole zone's content, used by piles. */
export function zoneMoveAll(ids: string[], to: Parameters<typeof moveCards>[1], player: string | null) {
  return moveCards(ids, to, { player });
}
