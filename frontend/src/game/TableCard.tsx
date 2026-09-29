import { usePrefs } from "../state/prefs";
import { memo } from "react";
import { openMenu } from "../components/ContextMenu";
import { useGame, useCardView } from "../state/gameStore";
import { FACE_DOWN_LABEL, isVisible } from "../types/game";
import { moveCards, tapCards, targetsFor } from "./actions";
import { dropCards } from "./drop";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag } from "./dnd";
import { CounterBadges, GameCardFace } from "./GameCardFace";
import { answerByClick, legalClass } from "./rules/RulesHud";

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
  const showSources = usePrefs((s) => s.showTokenSources);
  const legal = useGame((s) => legalClass(s.view, id, me));
  if (!card) return null;
  const visible = isVisible(card);
  const rotation = (card.tapped ? 90 : 0) + (card.flipped ? 180 : 0) + (card.rotation ?? 0);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const store = useGame.getState();
    if (legal === "rules-target" && answerByClick(store.view, id, me)) return; // click-to-target
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      store.select([id], "toggle");
      return;
    }
    if (!store.selection.includes(id)) store.select([id]);
    const ids = targetsFor(id);
    beginPointerDrag(e, { ids, from: card.zone, width, onDrop: (t) => dropCards(ids, id, t) });
  };

  return (
    <div
      className={`table-card ${selected ? "selected" : ""} ${card.attacking ? "attacking" : ""} ${card.blocking ? "blocking" : ""} ${legal}`}
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
        {visible && card.test_object && <span className="mark test" title="Test object — not part of any deck">TEST</span>}
        {visible && card.copy_of && <span className="mark copy" title={`Copy of ${card.copy_of.source_name}${card.copy_of.modifications ? ` — ${card.copy_of.modifications}` : ""}`}>COPY</span>}
        {visible && card.commander_key && <span className="mark cmdr" title="Commander">♛</span>}
        {visible && card.note && <span className="mark note" title={card.note}>✎</span>}
        {card.face_down && card.face_down_kind && card.face_down_kind !== "generic" && (
          <span className="mark fd" title={`${FACE_DOWN_LABEL[card.face_down_kind]} (face down)`}>{FACE_DOWN_LABEL[card.face_down_kind].toUpperCase()}</span>
        )}
        {card.attacking && <span className="mark atk" title="Attacking">⚔</span>}
        {card.blocking && <span className="mark blk" title="Blocking">⛨</span>}
        {card.locked && <span className="mark lock" title="Locked in place">🔒</span>}
        {visible && card.choices && Object.keys(card.choices).length > 0 && (
          <span className="mark choice" title={Object.entries(card.choices).map(([k, v]) => `${k}: ${v}`).join("\n")}>
            {Object.values(card.choices)[0]}
          </span>
        )}
        {visible && card.token_source && showSources && <span className="mark src" title={`Created by ${card.token_source.name}`}>↳ {card.token_source.name}</span>}
      </div>
      {(card.effects?.length || card.damage) ? (
        <div className="card-effects">
          {card.damage ? <span className="fx dmg" title="Damage marked">{card.damage}</span> : null}
          {card.effects?.slice(0, 4).map((e) => (
            <span key={e.id} className="fx" style={e.color ? { borderColor: e.color, color: e.color } : undefined} title={[e.name, e.value, e.text].filter(Boolean).join(" · ")}>
              {e.value ?? e.name}
            </span>
          ))}
          {(card.effects?.length ?? 0) > 4 && <span className="fx more">+{card.effects!.length - 4}</span>}
        </div>
      ) : null}
      <CounterBadges counters={card.counters} />
    </div>
  );
});

/** Right-click menu for moving a whole zone's content, used by piles. */
export function zoneMoveAll(ids: string[], to: Parameters<typeof moveCards>[1], player: string | null) {
  return moveCards(ids, to, { player });
}
