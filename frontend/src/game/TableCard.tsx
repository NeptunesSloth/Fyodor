import { doubleClickGesture } from "./rules/intents";
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
import { clickAnswer, justAnswered, legalClass } from "./rules/RulesHud";
import { TargetMark } from "./targeting/TargetMark";
import { Icon } from "../components/Icon";
import { countMark, countText } from "./piles";
import { BoardTile, packStats } from "./BoardTile";
import { reorderArranged } from "./arrangeDrop";
import { useHoverCard } from "./hoverCard";
import { attackDrop, attackSpot2D, defenderBadge, myAttackDecision, useAttackDraft } from "./rules/attackDraft";
import "./rules/attackers.css";

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
  /** The combat filter dims it (game/combatFilter.ts): drawn darker, still fully usable. */
  dim?: boolean;
  /** The player whose board it is drawn on: a card controlled by someone else is attached here from their board (game/attachments.ts guests). */
  board?: string;
  /** Which edge of the card faces the middle of the table on this board (where a tucked card peeks out). */
  front?: "top" | "bottom";
}

/** A permanent on a battlefield: positioned, tappable, draggable, with counters and markers. */
export const TableCard = memo(function TableCard({ id, left, top, width, me, z, pile, tile = false, dim = false, board, front = "top" }: Props) {
  const card = useCardView(id);
  const hover = useHoverCard();
  const selected = useGame((s) => s.selection.includes(id));
  const showSources = usePrefs((s) => s.showTokenSources);
  const legal = useGame((s) => legalClass(s.view, id, me));
  const stats = useGame((s) => s.view?.rules?.stats?.[id]);
  // the encoder's owner gem: a card controlled by someone other than its owner says whose it is
  const owner = useGame((s) => {
    const c = s.view?.cards[id];
    return c && c.owner !== c.controller ? s.view?.players.find((p) => p.id === c.owner) : undefined;
  });
  // -- attached elsewhere -- drawn on another player's board: its controller's seat colour and initial, never colour alone
  const guest = useGame((s) => {
    const c = s.view?.cards[id];
    return board && c && c.zone !== `${board}:battlefield` ? s.view?.players.find((p) => p.id === c.controller) : undefined;
  });
  const guestOf = useGame((s) => {
    const c = guest ? s.view?.cards[id] : undefined;
    if (!c) return "";
    const host = c.attached_to ? s.view?.cards[c.attached_to] : undefined;
    return host ? (isVisible(host) ? host.name : "a face-down permanent") : s.view?.players.find((p) => p.id === c.attached_player)?.name ?? "";
  });
  const peek = useGame((s) => s.peek.includes(id));
  // -- playtest (nov 18) -- combat read physically: an attacker (planned in the declare-attackers prompt, or declared) is pushed forward
  // toward the middle of the table and says whom it attacks ("→ B Bob"); a blocker steps forward too ("blocks 2" when it blocks several)
  const draftTarget = useAttackDraft((d) => d.plan[`a:${id}`]);
  const draftId = useAttackDraft((d) => d.decision);
  const deciding = useGame((s) => myAttackDecision(s.view, s.actingAs)?.id);
  const planned = draftId && draftId === deciding ? draftTarget : undefined;
  const attackTo = useGame((s) => {
    const c = s.view?.cards[id];
    const t = planned ? { id: planned.slice(2) } : c?.attacking;
    const b = s.view && t ? defenderBadge(s.view, t) : null;
    return b ? `${b.initial}|${b.color}|${b.name}` : "";
  });
  if (!card) return null;
  const visible = isVisible(card);
  const rotation = (card.tapped ? 90 : 0) + (card.flipped ? 180 : 0) + (card.rotation ?? 0);
  const count = countMark(card, pile); // ×N: the land pile it tops, or the token stack it is
  const fights = !!(card.attacking || card.attacking_without_target || card.blocking || card.blocking_without_attacker);
  const pushed = !!planned || (fights && !tile); // (an arranged tile's forward step is the layout's: game/arrange.ts)
  const [atkInitial, atkColor, atkName] = attackTo ? attackTo.split("|") : [];
  const blocks = card.blocking ? 1 + (card.blocking_more?.length ?? 0) : 0;

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const store = useGame.getState();
    if (clickAnswer(store.view, id, me, legal)) return; // click-to-target, and click a highlighted land to pay
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      store.select([id], "toggle");
      return;
    }
    // (a click on the one selected card selects it afresh: its action bar, closed when the stack moved on, opens again: Hud.tsx SelectionBar)
    if (!store.selection.includes(id) || store.selection.length === 1) store.select([id]);
    const ids = targetsFor(id);
    beginPointerDrag(e, { ids, from: card.zone, width, onDrop: (t) => {
      // declaring attackers: dragged toward an opponent it attacks them, back in my row it doesn't (rules/attackDraft.ts)
      const v = useGame.getState().view;
      if (t?.at && v && attackDrop(ids, attackSpot2D(v, me, t.zone, t.at.clientX, t.at.clientY))) return;
      return (tile && reorderArranged(ids, card.zone, t)) || dropCards(ids, id, t);
    } });
  };

  return (
    <div
      className={`table-card ${selected ? "selected" : ""} ${card.attacking || card.attacking_without_target ? "attacking" : ""} ${card.blocking || card.blocking_without_attacker ? "blocking" : ""} ${legal}${dim ? " combat-dim" : ""}${guest ? " guest" : ""}${peek ? " peek" : ""}${pushed ? ` pushed${front === "bottom" ? " push-down" : ""}` : ""}${planned ? " attack-planned" : ""}`}
      data-card-id={id}
      data-tapped={card.tapped ? "" : undefined}
      data-attack-planned={planned ? planned.slice(2) : undefined}
      data-tile={tile ? "" : undefined}
      style={{
        ...(tile
          // the arranged board positions its cards by transform: moving one is no layout for the rest of the board
          ? { left: 0, top: 0, width, zIndex: z, transform: `translate(${left}px, ${top}px)${rotation ? ` rotate(${rotation}deg)` : ""}` }
          : { left, top, width, zIndex: z, transform: rotation ? `rotate(${rotation}deg)` : undefined }),
        ...(guest ? { ["--guest" as string]: guest.color } : {}),
        ...(pushed ? { ["--push" as string]: `${Math.round(width * 0.3)}px` } : {}),
      }}
      onPointerDown={onPointerDown}
      onDoubleClick={(e) => {
        e.stopPropagation();
        if (justAnswered(id)) return; // the click already tapped it for mana (or chose it): don't tap it back
        doubleClickGesture(targetsFor(id), e, (x) => void tapCards(x)); // (-- playtest nov 17 -- a "{T}: …" ability activates, not a plain tap)
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
      {...hover(id)}
    >
      {tile ? <BoardTile card={card} stats={visible ? packStats(stats) : ""} /> : <GameCardFace card={card} />}
      {legal === "rules-target" && <TargetMark id={id} />}
      {guest && (
        <span className={`guest-tab ${front}`} data-testid="guest-tab" aria-label={`${guest.name}'s, attached to ${guestOf}`}
          title={`${guest.name} controls this${guestOf ? ` (attached to ${guestOf})` : ""}`}>
          {guest.name.slice(0, 1).toUpperCase()}
        </span>
      )}
      {count && <span className="pile-count-mark" data-testid={count.testId} title={count.title}>{countText(count.n)}</span>}
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
        {attackTo && (
          <span className={`mark atk-to${planned ? " planned" : ""}`} data-testid="attack-to" style={{ ["--seat" as string]: atkColor }}
            title={`${planned ? "Will attack" : "Attacking"} ${atkName}`}>→ <i>{atkInitial}</i>{atkName}</span>
        )}
        {(card.blocking || card.blocking_without_attacker) && <span className="mark blk" title="Blocking">⛨</span>}
        {blocks > 1 && <span className="mark blk-n" data-testid="blocks-n" title={`Blocking ${blocks} attackers`}>blocks {blocks}</span>}
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
