import { tapGesture } from "./rules/intents";
import { usePrefs } from "../state/prefs";
import { memo } from "react";
import { openMenu } from "../components/ContextMenu";
import { useGame, useCardView } from "../state/gameStore";
import { FACE_DOWN_LABEL, isVisible, type CardStats } from "../types/game";
import { moveCards, tapCards, targetsFor } from "./actions";
import { dropCards } from "./drop";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag } from "./dnd";
import { CounterBadges, GameCardFace } from "./GameCardFace";
import { answerByClick, legalClass } from "./rules/RulesHud";
import { Icon } from "../components/Icon";
import { countMark } from "./piles";
import { BoardTile } from "./BoardTile";
import { reorderArranged } from "./arrangeDrop";

interface Props {
  id: string;
  left: number;
  top: number;
  width: number;
  me: string;
  z: number;
  /** Arena-style: this card tops a pile of identical lands (game/piles.ts) or tokens (the arranged board). */
  pile?: number;
  /** On the arranged board: drawn as an art tile (game/BoardTile.tsx), dragged along its row to reorder. */
  tile?: boolean;
}

/** A permanent on a battlefield: positioned, tappable, draggable, with counters and markers. */
export const TableCard = memo(function TableCard({ id, left, top, width, me, z, pile, tile = false }: Props) {
  const card = useCardView(id);
  const selected = useGame((s) => s.selection.includes(id));
  const showSources = usePrefs((s) => s.showTokenSources);
  const legal = useGame((s) => legalClass(s.view, id, me));
  const stats = useGame((s) => s.view?.rules?.stats?.[id]);
  // the encoder's owner gem: a card controlled by someone other than its owner says whose it is
  const owner = useGame((s) => {
    const c = s.view?.cards[id];
    return c && c.owner !== c.controller ? s.view?.players.find((p) => p.id === c.owner) : undefined;
  });
  if (!card) return null;
  const visible = isVisible(card);
  const rotation = (card.tapped ? 90 : 0) + (card.flipped ? 180 : 0) + (card.rotation ?? 0);
  const count = countMark(card, pile); // ×N: the land pile it tops, or the token stack it is

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
    beginPointerDrag(e, { ids, from: card.zone, width, onDrop: (t) => (tile && reorderArranged(ids, card.zone, t)) || dropCards(ids, id, t) });
  };

  return (
    <div
      className={`table-card ${selected ? "selected" : ""} ${card.attacking || card.attacking_without_target ? "attacking" : ""} ${card.blocking || card.blocking_without_attacker ? "blocking" : ""} ${legal}`}
      data-card-id={id}
      data-tapped={card.tapped ? "" : undefined}
      data-tile={tile ? "" : undefined}
      style={tile
        // the arranged board moves its cards with transform only (no layout per frame when a row reflows)
        ? { left: 0, top: 0, width, zIndex: z, transform: `translate(${left}px, ${top}px)${rotation ? ` rotate(${rotation}deg)` : ""}` }
        : { left, top, width, zIndex: z, transform: rotation ? `rotate(${rotation}deg)` : undefined }}
      onPointerDown={onPointerDown}
      onDoubleClick={(e) => {
        e.stopPropagation();
        tapGesture(targetsFor(id), (x) => void tapCards(x));
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
      {tile ? <BoardTile card={card} stats={visible ? stats : undefined} /> : <GameCardFace card={card} />}
      {count && <span className="pile-count-mark" data-testid={count.testId} title={count.title}>×{count.n}</span>}
      <div className="card-marks">
        {visible && card.is_token && !card.copy_of && <span className="mark token">TOKEN</span>}
        {visible && card.test_object && <span className="mark test" title="Test object — not part of any deck">TEST</span>}
        {visible && card.copy_of && <span className="mark copy" title={`Copy of ${card.copy_of.source_name}${card.copy_of.modifications ? ` — ${card.copy_of.modifications}` : ""}`}>COPY</span>}
        {visible && card.commander_key && <span className="mark cmdr" title="Commander"><Icon name="crown" size={11} /></span>}
        {visible && card.merged && card.merged.length > 1 && (
          <span className="mark merge" data-testid="merge-mark" title={`${card.melded ? "Melded" : "Merged"} permanent, top to bottom:\n${card.merged.map((p) => p.name).join("\n")}`}>
            {card.melded ? "MELD" : `MUTATED ×${card.merged.length - 1}`}
          </span>
        )}
        {visible && card.note && <span className="mark note" title={card.note}>✎</span>}
        {card.face_down && card.face_down_kind && card.face_down_kind !== "generic" && (
          <span className="mark fd" title={`${FACE_DOWN_LABEL[card.face_down_kind]} (face down)`}>{FACE_DOWN_LABEL[card.face_down_kind].toUpperCase()}</span>
        )}
        {(card.attacking || card.attacking_without_target) && <span className="mark atk" title="Attacking"><Icon name="swords" size={11} /></span>}
        {(card.blocking || card.blocking_without_attacker) && <span className="mark blk" title="Blocking">⛨</span>}
        {card.locked && <span className="mark lock" title="Locked in place">🔒</span>}
        {visible && card.choices && Object.keys(card.choices).length > 0 && (
          <span className="mark choice" title={Object.entries(card.choices).map(([k, v]) => `${k}: ${v}`).join("\n")}>
            {Object.values(card.choices)[0]}
          </span>
        )}
        {visible && card.token_source && showSources && <span className="mark src" title={`Created by ${card.token_source.name}`}>↳ {card.token_source.name}</span>}
        {owner && <span className="mark owner" data-testid="owner-gem" style={{ ["--owner" as string]: owner.color }} title={`Owned by ${owner.name}`}>{owner.name.slice(0, 1).toUpperCase()}</span>}
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
      <CounterBadges counters={card.counters} cardId={id} />
      {visible && stats && !tile && <StatBadge stats={stats} />}
    </div>
  );
});

/** The creature's current power/toughness and gained/lost keywords, when the rules change them. */
export function StatBadge({ stats }: { stats: CardStats }) {
  const base = Number(stats.base?.[0] ?? NaN) + Number(stats.base?.[1] ?? NaN);
  const now = stats.pt ? stats.pt[0] + stats.pt[1] : NaN;
  const trend = Number.isNaN(base) || Number.isNaN(now) || now === base ? "" : now > base ? " up" : " down";
  const title = [stats.gained?.length ? `Has: ${stats.gained.join(", ")}` : "", stats.lost?.length ? `Lost: ${stats.lost.join(", ")}` : ""]
    .filter(Boolean).join("\n");
  return (
    <span className={`stat-badge${trend}`} title={title || undefined} data-testid="stat-badge">
      {stats.gained?.length ? <i>{stats.gained.map((k) => KEYWORD_GLYPH[k] ?? "✦").join("")}</i> : null}
      {stats.pt ? `${stats.pt[0]}/${stats.pt[1]}` : ""}
    </span>
  );
}

const KEYWORD_GLYPH: Record<string, string> = {
  flying: "🪶", haste: "»", trample: "⇶", vigilance: "◉", lifelink: "♥", deathtouch: "☠", "first strike": "⚡",
  "double strike": "⚡⚡", menace: "⚔", reach: "↑", hexproof: "◈", indestructible: "⛨",
};

/** Right-click menu for moving a whole zone's content, used by piles. */
export function zoneMoveAll(ids: string[], to: Parameters<typeof moveCards>[1], player: string | null) {
  return moveCards(ids, to, { player });
}
