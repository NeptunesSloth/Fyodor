import { memo } from "react";
import { openMenu } from "../components/ContextMenu";
import { useCardView, useGame, useZoneIds } from "../state/gameStore";
import { splitZone } from "../types/game";
import { moveCards, targetsFor } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag, useDrag, type DropResult } from "./dnd";
import { GameCardFace } from "./GameCardFace";
import { dropAsIntent } from "./rules/intents";
import { legalClass } from "./rules/RulesHud";

/** Horizontal, overlapping hand. Only the owner (or an open-table view) sees card faces. */
export function Hand({ player, me, compact = false }: { player: string; me: string; compact?: boolean }) {
  const key = `${player}:hand`;
  const ids = useZoneIds(key) ?? [];
  const over = useDrag((s) => s.drag?.overZone === key);
  return (
    <div className={`hand ${compact ? "compact" : ""} ${over ? "drop-over" : ""}`} data-drop={key} data-ordered="">
      {ids.length === 0 && !compact && <div className="hand-empty">Hand is empty — press D to draw</div>}
      <div className="hand-cards" style={{ ["--n" as string]: ids.length }}>
        {ids.map((id, i) => (
          <HandCard key={id} id={id} index={i} fan={i - (ids.length - 1) / 2} me={me} compact={compact} />
        ))}
      </div>
    </div>
  );
}

/** fan: the card's offset from the middle of the hand (the 3D table lays the hand out as an arc). */
const HandCard = memo(function HandCard({ id, index, fan, me, compact }: { id: string; index: number; fan: number; me: string; compact: boolean }) {
  const card = useCardView(id);
  const selected = useGame((s) => s.selection.includes(id));
  const legal = useGame((s) => legalClass(s.view, id, me));
  if (!card) return null;
  const onDrop = (ids: string[], target: DropResult | null) => {
    if (!target) return;
    if (dropAsIntent(ids, target, me)) return; // automation on: play the land / cast the spell
    const { zone, player } = splitZone(target.zone);
    if (target.zone === card.zone && target.index != null) {
      const adjusted = target.index > index ? target.index - 1 : target.index;
      if (adjusted !== index) void moveCards(ids, "hand", { player, index: adjusted });
      return;
    }
    if (zone === "battlefield" && target.x != null && target.y != null) {
      useGame.getState().setPending(Object.fromEntries(ids.map((cid, i) => [cid, [target.x! + i * 18, target.y! + i * 18]])));
      void moveCards(ids, "battlefield", { player, x: target.x, y: target.y });
      return;
    }
    void moveCards(ids, zone, { player, position: target.position, index: target.index });
  };
  return (
    <div
      className={`hand-card ${selected ? "selected" : ""} ${!card.hidden && card.revealed ? "revealed" : ""} ${legal}`}
      data-index={index}
      data-card-id={id}
      style={{ ["--fan" as string]: fan, ["--fan2" as string]: fan * fan }}
      tabIndex={compact ? -1 : 0}
      role="button"
      aria-label={card.hidden ? "Hidden card" : card.name}
      aria-pressed={selected}
      onKeyDown={(e) => {
        if (e.key === " ") {
          e.preventDefault();
          useGame.getState().select([id], e.shiftKey || e.ctrlKey || e.metaKey ? "toggle" : undefined);
        } else if (e.key === "Enter" && !card.hidden) {
          // the keyboard way to play a card: the same as double-click (rules intents first)
          e.preventDefault();
          if (!dropAsIntent([id], { zone: `${me}:battlefield` }, me)) void moveCards([id], "battlefield", { player: me });
        }
      }}
      onPointerDown={(e) => {
        if (e.button !== 0 || compact) return;
        const store = useGame.getState();
        if (e.shiftKey || e.ctrlKey || e.metaKey) {
          store.select([id], "toggle");
          return;
        }
        if (!store.selection.includes(id)) store.select([id]);
        const ids = targetsFor(id);
        beginPointerDrag(e, { ids, from: card.zone, onDrop: (t) => onDrop(ids, t) });
      }}
      onDoubleClick={() => {
        if (card.hidden) return;
        // with automation on this plays the land / casts the spell through the rules engine
        if (dropAsIntent([id], { zone: `${me}:battlefield` }, me)) return;
        void moveCards([id], "battlefield", { player: me });
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        const store = useGame.getState();
        if (!store.view) return;
        if (!store.selection.includes(id)) store.select([id]);
        const { title, items } = cardMenu(card, store.view, me);
        openMenu(e, items, title);
      }}
      onPointerEnter={() => useGame.getState().setHover(id)}
      onPointerLeave={() => useGame.getState().hover === id && useGame.getState().setHover(null)}
    >
      <GameCardFace card={card} />
      {!card.hidden && card.revealed && <span className="revealed-tag">revealed</span>}
    </div>
  );
});
