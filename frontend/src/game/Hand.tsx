import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { ManaSymbol, ManaText } from "../cards/ManaText";
import { PayPreview, previewPay } from "./PayPreview";
import { GameCardFace } from "./GameCardFace";
import { dropFromHand } from "./handDrop";
import { legalClass } from "./rules/RulesHud";
import { customOrder, moveInOrder, saveCustomOrder, sortHand, type HandFacts } from "./handSort";
import { isOut } from "./outOfGame";
import type { CardData } from "../types/cards";
import { useHoverCard } from "./hoverCard";
import { handCardWidth, handLayout, handRoom, stripRange } from "./handLayout";
import { keyLabel } from "./hotkeys";
import { useFreshDraws } from "./drawNotices";

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
export function displayOrder(ids: string[]): string[] {
  const view = useGame.getState().view;
  const sort = usePrefs.getState().handSort;
  if (!view || sort === "drawn") return ids;
  const cache = useCardCache.getState().cards;
  return sortHand(ids, (id) => factsOf(view.cards[id], cache), sort, customOrder(view.game.id));
}

/** An opponent's hand on the 2D table: at most this many card backs, then a ×N count (a 77-card hand is a pile, not a row). */
export const COMPACT_MAX = 12;

/** Open (or close) my whole hand as a grid of cards: the zone browser, with its filters and sorts (Shift+H). */
export function toggleHandBrowser(me: string): void {
  const s = useGame.getState();
  const zone = `${me}:hand`;
  s.openBrowser(s.browser?.zone === zone ? null : { zone, title: "Your hand" });
}

/** The width this hand has (px), whether it is on the 3D table, and the window's width (the 3D cards size to it). */
function useHandRoom(ref: React.RefObject<HTMLDivElement | null>, on: boolean): { width: number; three: boolean; vw: number } {
  const [room, setRoom] = useState({ width: 0, three: false, vw: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!on || !el) return;
    const measure = () => {
      const next = { width: el.clientWidth, three: !!el.closest(".is-3d"), vw: window.innerWidth };
      setRoom((cur) => (cur.width === next.width && cur.three === next.three && cur.vw === next.vw ? cur : next));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, on]);
  return room;
}

/**
 * Horizontal, overlapping hand. Only the owner (or an open-table view) sees card faces.
 * My hand always fits the screen: a fan while it can, a strip that scrolls sideways past STRIP_AT cards (handLayout.ts);
 * "Hand (N)" opens the whole hand in the zone browser. An opponent's hand is a few backs and a count.
 */
export function Hand({ player, me, compact = false }: { player: string; me: string; compact?: boolean }) {
  const key = `${player}:hand`;
  const ids = useZoneIds(key) ?? [];
  const over = useDrag((s) => s.drag?.overZone === key);
  const sort = usePrefs((s) => s.handSort);
  const cards = useGame((s) => s.view?.cards);
  const cache = useCardCache((s) => s.cards);
  const tick = useOrderTick((s) => s.n);
  const out = useGame((s) => isOut(s.view, me)); // -- out of the game -- nothing to draw for: they watch
  const browsing = useGame((s) => s.browser?.zone === key);
  const mine = player === me && !compact;
  // my hand in the order I chose (Arena-style sorting, or my own arrangement); the server keeps the drawn order
  const shown = useMemo(() => (mine && sort !== "drawn" && cards ? displayOrder(ids) : ids),
    // displayOrder reads these stores; tick covers "my order"
    [mine, sort, ids, cards, cache, tick]);
  const box = useRef<HTMLDivElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  const room = useHandRoom(box, !compact);
  const layout = useMemo(() => {
    if (compact || !room.width) return null;
    const cardW = handCardWidth(room.vw, room.three);
    return handLayout(shown.length, handRoom(room.width, room.three), cardW, room.three ? "arc" : "row");
  }, [compact, room, shown.length]);
  const [scrollLeft, setScrollLeft] = useState(0);
  const isStrip = layout?.mode === "strip";
  useEffect(() => { if (!isStrip) setScrollLeft(0); }, [isStrip]);
  // an opponent's hand: a few backs and the count (never 77 backs across their seat)
  const drawn = compact && shown.length > COMPACT_MAX ? shown.slice(0, COMPACT_MAX) : shown;
  const x0 = layout ? Math.round((room.width - layout.boxW) / 2) : 0;
  const style: Record<string, string | number> = { ["--n"]: ids.length };
  if (layout) {
    style["--w"] = `${layout.cardW}px`;
    style["--overlap"] = `${layout.cardW - layout.step}px`;
    style["--spread"] = `${layout.spread}deg`;
    // the arc's outer cards sit a little lower: at most ~24px at the ends, however many cards (a 20-card fan stays on screen)
    const ends = Math.max(1, ((shown.length - 1) / 2) ** 2);
    style["--sag"] = `${Math.min(2.2, 24 / ends).toFixed(3)}px`;
    if (isStrip) {
      style["--x0"] = `${x0}px`;
      style["--box-w"] = `${layout.boxW}px`;
    }
  }
  const range = layout && isStrip ? stripRange(shown.length, layout, scrollLeft) : null;
  const scrollBy = (dir: 1 | -1) => strip.current?.scrollBy({ left: dir * Math.max(layout?.step ?? 0, (layout?.boxW ?? 0) * 0.8), behavior: usePrefs.getState().reducedMotion ? "auto" : "smooth" });
  return (
    <div ref={box} className={`hand ${compact ? "compact" : ""} ${over ? "drop-over" : ""}`} data-drop={key} data-ordered="" data-count={ids.length}>
      {ids.length === 0 && !compact && !out && <div className="hand-empty">Hand is empty — press D to draw</div>}
      <div
        ref={strip}
        className="hand-cards"
        data-mode={layout?.mode}
        data-testid={compact ? undefined : "my-hand-cards"}
        style={style}
        onScroll={isStrip ? (e) => setScrollLeft(e.currentTarget.scrollLeft) : undefined}
        onWheel={isStrip ? (e) => {
          // the wheel scrolls the strip sideways (a trackpad's own sideways swipe already does)
          if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
          e.currentTarget.scrollLeft += e.deltaY * (e.deltaMode === 1 ? 40 : 1);
        } : undefined}
      >
        {drawn.map((id, i) => (
          <HandCard key={id} id={id} index={ids.indexOf(id)} fan={isStrip ? 0 : i - (shown.length - 1) / 2} me={me} compact={compact} small={isStrip} />
        ))}
      </div>
      {compact && shown.length > COMPACT_MAX && (
        <span className="hand-count" data-testid={`hand-count-${player}`} aria-label={`${shown.length} cards in hand`}>×{shown.length}</span>
      )}
      {mine && <PayPreview me={me} />}
      {mine && layout && ids.length > 0 && (
        <div className="hand-tools" style={{ ["--x0" as string]: `${x0}px` }}>
          <button type="button" className="hand-browse" data-testid="hand-browse" aria-pressed={browsing}
            title={`See your whole hand as a grid: filter, sort, drag or double-click to play (${keyLabel("hand_browse", usePrefs.getState().keymap) ?? "Shift+H"})`}
            aria-label={`Your hand: ${ids.length} ${ids.length === 1 ? "card" : "cards"}. Open the hand browser`}
            onClick={() => toggleHandBrowser(me)}>
            Hand <b>{ids.length}</b>
          </button>
          <ManaReady />
          {range && (
            <div className="hand-scroll" role="group" aria-label="Scroll your hand">
              <button type="button" className="hand-scroll-btn" aria-label="Scroll hand left" data-testid="hand-scroll-left"
                disabled={scrollLeft <= 1} onClick={() => scrollBy(-1)}>‹</button>
              <span className="hand-range" aria-live="polite">{range.first}–{range.last}</span>
              <button type="button" className="hand-scroll-btn" aria-label="Scroll hand right" data-testid="hand-scroll-right"
                disabled={range.last >= shown.length} onClick={() => scrollBy(1)}>›</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** -- mana readout -- what my untapped sources make now (the server's count: Cabal Coffers its Swamps, mana creatures that can tap). */
function ManaReady() {
  const r = useGame((s) => (s.view?.rules && !s.view.rules.paused ? s.view.rules.mana_ready : undefined));
  if (!r?.count) return null;
  const extra = r.count - r.symbols.length;
  const words = r.symbols.map((m) => (m === "any" ? "any colour" : m)).join(" ");
  return (
    <span className="mana-ready" data-testid="mana-ready" role="note" aria-label={`${r.count} mana available: ${words}${extra > 0 ? ` and ${extra} more` : ""}`}
      title="What your untapped lands and mana sources can make now. Point at a card you can cast to see which ones it would tap.">
      <b>{r.count}</b> available:
      {r.symbols.map((m, i) => (m === "any" ? <span key={i} className="mr-any" aria-hidden title="Any colour">✦</span> : <ManaSymbol key={i} sym={m} />))}
      {extra > 0 && <span aria-hidden>+{extra}</span>}
    </span>
  );
}

/**
 * A card of my hand dropped somewhere (from the hand itself or from the hand browser): with automation on, onto the table
 * plays or casts it (handDrop.ts); within the hand it moves (or, in a sorted hand, becomes "my order"); anywhere else it moves.
 */
export function dropHandCards(ids: string[], target: DropResult | null, me: string, card: Pick<GameCard, "zone">, index: number): void {
  if (!target) return;
  if (dropFromHand(ids, target, me)) return; // automation on: play the land / cast the spell (Alt: place by hand)
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
}

/**
 * Play a card from my hand: double-click or Enter (with automation on, the land is played / the spell cast). It goes the way a drag
 * onto my side does (handDrop.ts): -- playtest (nov 16) -- a split card, an adventure or a modal double-faced card asks which half or
 * face at `at` (the double-click, or the card for Enter); a double-click cast Fire // Ice's left half without asking.
 */
export function playFromHand(id: string, me: string, at?: { clientX: number; clientY: number }): void {
  if (dropFromHand([id], { zone: `${me}:battlefield`, ...(at ? { at } : {}) }, me)) return;
  void moveCards([id], "battlefield", { player: me });
}

/** Where a chooser a keyboard play opens shows: over the card. */
export function centreOf(el: Element): { clientX: number; clientY: number } {
  const r = el.getBoundingClientRect();
  return { clientX: Math.round(r.left + r.width / 2), clientY: Math.round(r.top + r.height / 2) };
}

/** Start dragging a card of my hand (the selection, if it is part of it); a click with Shift/Ctrl adds to the selection. */
export function grabHandCard(e: React.PointerEvent, id: string, card: Pick<GameCard, "zone">, me: string, index: number): void {
  const store = useGame.getState();
  if (e.shiftKey || e.ctrlKey || e.metaKey) {
    store.select([id], "toggle");
    return;
  }
  if (!store.selection.includes(id)) store.select([id]);
  const ids = targetsFor(id);
  beginPointerDrag(e, { ids, from: card.zone, onDrop: (t) => dropHandCards(ids, t, me, card, index) });
}

/** A card's menu (right-click), as on the table. */
export function handCardMenu(e: React.MouseEvent, id: string, card: GameCard, me: string): void {
  e.preventDefault();
  const store = useGame.getState();
  if (!store.view) return;
  if (!store.selection.includes(id)) store.select([id]);
  const { title, items } = cardMenu(card, store.view, me);
  openMenu(e, items, title);
}

/** fan: the card's offset from the middle of the hand (the 3D table lays the hand out as an arc). */
/** small: a long strip draws its slivers from the small images (scrolling 77–200 cards stays cheap; the hover preview is full size). */
const HandCard = memo(function HandCard({ id, index, fan, me, compact, small = false }: { id: string; index: number; fan: number; me: string; compact: boolean; small?: boolean }) {
  const card = useCardView(id);
  const hover = useHoverCard();
  const selected = useGame((s) => s.selection.includes(id));
  const legal = useGame((s) => legalClass(s.view, id, me));
  // what it costs to cast right now, when that isn't its mana cost (Grand Arbiter Augustin, Thalia, Sphere: the server's own reckoning)
  const costNow = useGame((s) => (s.view?.rules && !s.view.rules.paused ? s.view.rules.hints.cost_now?.[id] : undefined));
  const fresh = useFreshDraws((s) => !compact && s.ids.includes(id)); // -- draw notice -- drawn and not looked at yet
  if (!card) return null;
  return (
    <div
      className={`hand-card ${selected ? "selected" : ""} ${fresh ? "fresh-draw" : ""} ${!card.hidden && card.revealed ? "revealed" : ""} ${legal}`}
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
          playFromHand(id, me, centreOf(e.currentTarget));
        } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Home" || e.key === "End") && !e.ctrlKey && !e.metaKey && !e.altKey) {
          // walk the hand with the arrows (a long hand scrolls along); the 3D view's arrow panning waits
          const el = e.currentTarget;
          const next = e.key === "ArrowLeft" ? el.previousElementSibling : e.key === "ArrowRight" ? el.nextElementSibling
            : e.key === "Home" ? el.parentElement?.firstElementChild : el.parentElement?.lastElementChild;
          e.preventDefault();
          e.stopPropagation();
          if (next instanceof HTMLElement && next !== el) {
            next.focus({ preventScroll: true });
            // bring it into the strip's view by scrolling the strip only (scrollIntoView would also shift the table: the
            // cards reach below the screen's edge)
            const strip = next.parentElement;
            if (strip && strip.scrollWidth > strip.clientWidth) {
              if (next.offsetLeft < strip.scrollLeft) strip.scrollLeft = next.offsetLeft;
              else if (next.offsetLeft + next.offsetWidth > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = next.offsetLeft + next.offsetWidth - strip.clientWidth;
            }
          }
        }
      }}
      onPointerDown={(e) => {
        if (e.button !== 0 || compact) return;
        grabHandCard(e, id, card, me, index);
      }}
      onDoubleClick={(e) => {
        if (card.hidden) return;
        // with automation on this plays the land / casts the spell through the rules engine
        playFromHand(id, me, { clientX: e.clientX, clientY: e.clientY });
      }}
      onContextMenu={(e) => handCardMenu(e, id, card, me)}
      onMouseEnter={fresh ? () => useFreshDraws.getState().seen(id) : undefined}
      onFocus={() => { if (fresh) useFreshDraws.getState().seen(id); if (!compact) previewPay(id, me); }}
      onBlur={compact ? undefined : () => previewPay(null, me)}
      {...hover(id)}
    >
      <GameCardFace card={card} size={small ? "small" : "normal"} />
      {!card.hidden && card.revealed && <span className="revealed-tag">revealed</span>}
      {costNow && !card.hidden && (
        <span className="cost-now" data-testid="cost-now" title={`Costs ${costNow} to cast now (cost reductions and taxes)`} aria-label={`Costs ${costNow} now`}>
          <ManaText text={costNow} />
        </span>
      )}
    </div>
  );
});
