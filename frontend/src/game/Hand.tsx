import { memo, useMemo } from "react";
import { create } from "zustand";
import { openMenu } from "../components/ContextMenu";
import { toast } from "../components/Toasts";
import { useCardCache } from "../state/cardCache";
import { useCardView, useGame, useZoneIds } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, splitZone, type GameCard } from "../types/game";
import { moveCards, targetsFor } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag, useDrag, type DropResult } from "./dnd";
import { ManaText } from "../cards/ManaText";
import { GameCardFace } from "./GameCardFace";
import { dropAsIntent } from "./rules/intents";
import { legalClass } from "./rules/RulesHud";
import { customOrder, moveInOrder, saveCustomOrder, sortHand, type HandFacts } from "./handSort";
import { isOut } from "./outOfGame";
import type { CardData } from "../types/cards";

/** What sorting needs to know about a card in my hand (null while its card data hasn't loaded). */
function factsOf(card: GameCard | undefined, cache: Record<string, CardData>): HandFacts | null {
  if (!isVisible(card)) return null;
  if (card.token) return { name: card.name, mv: 0, colors: card.token.colors ?? [], typeLine: card.token.type_line ?? "" };
  const data = card.card_id ? cache[card.card_id] : undefined;
  if (!data) return null;
  return { name: data.name, mv: data.cmc ?? 0, colors: data.colors, typeLine: data.type_line ?? "" };
}

/** Bumped when "my order" changes (it lives in session storage, outside React). */
const useOrderTick = create<{ n: number; bump: () => void }>((set) => ({ n: 0, bump: () => set((s) => ({ n: s.n + 1 })) }));

/** My hand in the order I see it: drawn, sorted, or my own arrangement (display only). */
function displayOrder(ids: string[]): string[] {
  const view = useGame.getState().view;
  const sort = usePrefs.getState().handSort;
  if (!view || sort === "drawn") return ids;
  const cache = useCardCache.getState().cards;
  return sortHand(ids, (id) => factsOf(view.cards[id], cache), sort, customOrder(view.game.id));
}

/** Horizontal, overlapping hand. Only the owner (or an open-table view) sees card faces. */
export function Hand({ player, me, compact = false }: { player: string; me: string; compact?: boolean }) {
  const key = `${player}:hand`;
  const ids = useZoneIds(key) ?? [];
  const over = useDrag((s) => s.drag?.overZone === key);
  const sort = usePrefs((s) => s.handSort);
  const cards = useGame((s) => s.view?.cards);
  const cache = useCardCache((s) => s.cards);
  const tick = useOrderTick((s) => s.n);
  const out = useGame((s) => isOut(s.view, me)); // -- out of the game -- nothing to draw for: they watch
  const mine = player === me && !compact;
  // my hand in the order I chose (Arena-style sorting, or my own arrangement); the server keeps the drawn order
  const shown = useMemo(() => (mine && sort !== "drawn" && cards ? displayOrder(ids) : ids),
    // displayOrder reads these stores; tick covers "my order"
    [mine, sort, ids, cards, cache, tick]);
  return (
    <div className={`hand ${compact ? "compact" : ""} ${over ? "drop-over" : ""}`} data-drop={key} data-ordered="">
      {ids.length === 0 && !compact && !out && <div className="hand-empty">Hand is empty — press D to draw</div>}
      <div className="hand-cards" style={{ ["--n" as string]: ids.length }}>
        {shown.map((id, i) => (
          <HandCard key={id} id={id} index={ids.indexOf(id)} fan={i - (shown.length - 1) / 2} me={me} compact={compact} />
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
  // what it costs to cast right now, when that isn't its mana cost (Grand Arbiter Augustin, Thalia, Sphere: the server's own reckoning)
  const costNow = useGame((s) => (s.view?.rules && !s.view.rules.paused ? s.view.rules.hints.cost_now?.[id] : undefined));
  if (!card) return null;
  const onDrop = (ids: string[], target: DropResult | null) => {
    if (!target) return;
    if (dropAsIntent(ids, target, me)) return; // automation on: play the land / cast the spell
    const { zone, player } = splitZone(target.zone);
    if (target.zone === card.zone && target.index != null) {
      const prefs = usePrefs.getState();
      const view = useGame.getState().view;
      if (prefs.handSort !== "drawn" && view) {
        // a sorted hand: keep what I see, with this move, as "my order" (display only, like the sort)
        const hand = (view.zones[card.zone] as string[] | undefined) ?? [];
        const before = target.index < hand.length ? hand[target.index]! : null;
        saveCustomOrder(view.game.id, moveInOrder(displayOrder(hand), ids, before));
        if (prefs.handSort !== "custom") {
          prefs.set({ handSort: "custom" });
          toast("Hand: in my order (S cycles the sorts)");
        }
        useOrderTick.getState().bump();
        return;
      }
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
      {costNow && !card.hidden && (
        <span className="cost-now" data-testid="cost-now" title={`Costs ${costNow} to cast now (cost reductions and taxes)`} aria-label={`Costs ${costNow} now`}>
          <ManaText text={costNow} />
        </span>
      )}
    </div>
  );
});
