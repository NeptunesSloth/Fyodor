import { playmatStyle, usePlaymat } from "./appearance";
import { useEffect, useMemo, useRef, useState } from "react";
import { useDrag } from "./dnd";
import { useGame, useZoneIds } from "../state/gameStore";
import { battlefieldCardWidth, BF_H, BF_W, CARD_RATIO, toPixels } from "./geometry";
import { TableCard } from "./TableCard";
import { openMenu } from "../components/ContextMenu";
import { tableMenu } from "./selection";
import { zonePileTops } from "./piles";
import { useCardCache } from "../state/cardCache";
import { usePrefs } from "../state/prefs";
import { isVisible } from "../types/game";
import { applyOrder, arrangeBoard, arrangeCard, boardOrder, type BoardLayout } from "./arrange";
import { publishBoard, useBoardOrderTick } from "./arrangeDrop";
import { hiddenUnderPiles, liftedIds } from "./boardCovers";
import { useLitCards } from "./combatFilter";
import { boardCards, guestSpot } from "./attachments";
import "./board.css";

interface Props {
  player: string;
  me: string;
  mirrored: boolean;
  color: string;
}

/** The hand overlaps the bottom of my mat by this much (px): the arranged board keeps its back row clear of it. */
export const HAND_OVERLAP = 22;

/**
 * A player's battlefield. Arranged (the default, this screen only): rows like MTG Arena's (game/arrange.ts). Free
 * placement: positions are virtual units scaled to the element size, as the server keeps them.
 */
export function Battlefield({ player, me, mirrored, color }: Props) {
  const playmat = usePlaymat(player);
  const key = `${player}:battlefield`;
  const zoneIds = useZoneIds(key);
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 300 });
  const pending = useGame((s) => s.pendingPositions);
  const cards = useGame((s) => s.view?.cards);
  const over = useDrag((s) => s.drag?.overZone === key);
  const dragging = useDrag((s) => s.drag?.ids);
  const selection = useGame((s) => s.selection);
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const typeData = useCardCache((s) => s.cards); // type lines arrive after the first render
  const view = useGame((s) => s.view);
  // -- attached elsewhere -- my Aura on your creature is drawn here, tucked under it (game/attachments.ts boardCards)
  const ids = useMemo(() => (view ? boardCards(view, key) : zoneIds ?? []), [view, key, zoneIds]);
  const arranged = usePrefs((s) => s.boardLayout) !== "free";
  useBoardBodyClass(arranged);
  const mine = player === me;
  const dialSpace = useTurnDialCorner(ref, mine ? (arranged ? "corner" : "reserve") : null);
  const keepOut = arranged ? dialSpace : null;
  const reserve = !arranged && dialSpace ? dialSpace.left : 0;
  const orderTick = useBoardOrderTick((s) => s.n);
  const facts = useMemo(() => {
    if (!arranged || !view) return null;
    const stats = view.rules?.stats;
    return applyOrder(ids, boardOrder(view.game.id, key)).flatMap((id) => {
      const c = view.cards[id];
      if (!c) return [];
      return [arrangeCard(c, isVisible(c) && c.card_id ? typeData[c.card_id] : undefined, stats?.[id])];
    });
    // orderTick: my order changed (it lives in session storage)
  }, [arranged, view, ids, key, typeData, orderTick]);
  // most updates change nothing on most boards: lay a board out again only when what it shows changed
  const sig = facts ? facts.map((f) => `${f.id}|${f.row}|${f.key ?? ""}|${f.n}|${f.turned ? 1 : 0}|${f.forward ? 1 : 0}|${f.host ?? ""}`).join("\n") : "";
  const layout = useMemo<BoardLayout | null>(
    () => (facts ? arrangeBoard(facts, { width: size.w, height: size.h, mirrored, backInset: mine ? HAND_OVERLAP : 0, keepOut, maxW: 150, minW: 60 }) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sig` stands for `facts`
    [sig, size.w, size.h, mirrored, mine, keepOut]);
  useEffect(() => publishBoard(key, layout, size.w, size.h, mirrored), [key, layout, size.w, size.h, mirrored]);
  const piles = useMemo(() => (view && !arranged ? zonePileTops(view, key) : new Map<string, number>()), [view, key, typeData, arranged]);
  // -- token piles -- a card wholly under an identical one isn't rendered (game/boardCovers.ts); the ×N on the top one counts it
  const hidden = useMemo(() => {
    if (!view) return new Set<string>();
    const lifted = liftedIds(view, ids, me, { selection, pending, dragging });
    for (const id of ids) if (view.cards[id]?.zone !== key) lifted.add(id); // (a guest's own position is on another mat)
    return hiddenUnderPiles(view, ids, lifted, pending, layout);
  }, [view, ids, key, me, selection, pending, dragging, layout]);
  // -- combat filter -- what the filter dims (game/combatFilter.ts); null: nothing
  const lit = useLitCards(me);
  const cardW = layout ? layout.w : battlefieldCardWidth(size.w, size.h, true);
  const cardH = layout ? layout.h : cardW * CARD_RATIO;

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || e.target !== e.currentTarget) return;
    const rect = ref.current!.getBoundingClientRect();
    const x0 = e.clientX - rect.left;
    const y0 = e.clientY - rect.top;
    if (!e.shiftKey) useGame.getState().clearSelection();
    let current = { x0, y0, x1: x0, y1: y0 };
    const move = (ev: PointerEvent) => {
      current = { x0, y0, x1: ev.clientX - rect.left, y1: ev.clientY - rect.top };
      setMarquee(current);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setMarquee(null);
      const minX = Math.min(current.x0, current.x1);
      const maxX = Math.max(current.x0, current.x1);
      const minY = Math.min(current.y0, current.y1);
      const maxY = Math.max(current.y0, current.y1);
      if (maxX - minX < 4 && maxY - minY < 4) return;
      const hit = ids.filter((id) => {
        const at = layout?.place.get(id);
        if (at) return at.left < maxX && at.left + cardW > minX && at.top < maxY && at.top + cardH > minY;
        const c = cards?.[id];
        if (layout || !c || c.x == null || c.y == null) return false;
        const [px, py] = toPixels(c.x, c.y, size.w, size.h, cardH, mirrored);
        return px < maxX && px + cardW > minX && py < maxY && py + cardH > minY;
      });
      useGame.getState().select(hit, e.shiftKey ? "add" : "replace");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div
      ref={ref}
      className={`battlefield ${mirrored ? "mirrored" : ""} ${over ? "drop-over" : ""} ${layout ? "arranged" : ""} ${layout && layout.w < 44 ? "tiny" : ""}`}
      // --tw: the arranged board's tile width, which sizes the tiles' name bars, plates and chips (board.css)
      style={{ ["--player-color" as string]: color, ...(layout ? { ["--tw" as string]: `${layout.w.toFixed(1)}px` } : {}), ...(reserve > 0 ? { marginRight: reserve } : {}) }}
      data-drop={key}
      data-battlefield=""
      data-cardh={cardH}
      {...(mirrored ? { "data-mirrored": "" } : {})}
      onPointerDown={onPointerDown}
      onContextMenu={(e) => {
        if (e.target !== e.currentTarget) return; // a card has its own menu
        e.preventDefault();
        openMenu(e, tableMenu(), "Table");
      }}
    >
      {playmat.url && (
        <div className={`playmat-layer ${playmat.mat?.show_zones ? "" : "bare"}`} style={playmatStyle(playmat.mat, playmat.url)} aria-hidden />
      )}
      {layout && <MatBands layout={layout} />}
      {layout && ids.map((id) => {
        const at = layout.place.get(id);
        if (!at || hidden.has(id)) return null;
        return <TableCard key={id} id={id} left={Math.round(at.left)} top={Math.round(at.top)} width={layout.w} me={me} z={at.z} pile={at.pile} dim={!!lit && !lit.has(id)} tile board={player} front={mirrored ? "bottom" : "top"}
          room={mirrored ? size.h - at.top - layout.h : at.top} />;
      })}
      {!layout && ids.map((id, i) => {
        const c = cards?.[id];
        if (!c || hidden.has(id)) return null;
        const guest = c.zone !== key && view ? guestSpot(view, id, (h) => pending[h] ?? (cards?.[h] ? [cards[h]!.x ?? 0, cards[h]!.y ?? 0] : null)) : null;
        const [vx, vy] = guest ?? pending[id] ?? [c.x ?? 0, c.y ?? 0];
        const [rawLeft, raw] = toPixels(Math.max(-40, Math.min(BF_W, vx)), Math.max(-40, Math.min(BF_H, vy)), size.w, size.h, cardH, mirrored);
        // a wide, short mat makes cards taller than the room below their row: keep them on the felt (display only)
        const top = size.h > cardH + 8 ? Math.max(4, Math.min(size.h - cardH - 4, raw)) : raw;
        // small mats draw cards larger than their share (readable): the right-most stay on the felt too
        const left = Math.max(0, Math.min(size.w - cardW - 2, rawLeft));
        return <TableCard key={id} id={id} left={left} top={top} width={cardW} me={me} z={i + 1} pile={piles.get(id)} dim={!!lit && !lit.has(id)} board={player} front={mirrored ? "bottom" : "top"}
          room={mirrored ? size.h - top - cardH : top} />;
      })}
      {marquee && (
        <div
          className="marquee"
          style={{
            left: Math.min(marquee.x0, marquee.x1),
            top: Math.min(marquee.y0, marquee.y1),
            width: Math.abs(marquee.x1 - marquee.x0),
            height: Math.abs(marquee.y1 - marquee.y0),
          }}
        />
      )}
    </div>
  );
}

/** The land strip at the mat's back edge, printed on the felt like a playmat's zone (only where there are lands). */
function MatBands({ layout }: { layout: BoardLayout }) {
  const lands = layout.rows.find((r) => r.kind === "land");
  if (!lands) return null;
  const pad = layout.w * 0.12;
  return <div className="mat-band" aria-hidden style={{ top: lands.top - pad, height: lands.height + pad * 2 }} />;
}

/**
 * The turn dial sits over the bottom right of my mat. Arranged (`mode` "corner"): the corner it covers (px, in the mat's
 * own coordinates), so the rows stop short of it. Free placement (`mode` "reserve"): how much of the mat's row (px from
 * its right edge) the dial takes, which the mat gives up, so no card can lie under it (the mat's own rect is still what
 * drops measure, so positions stay true). It keeps the tallest the dial has been, so the board doesn't reflow every step.
 */
function useTurnDialCorner(ref: React.RefObject<HTMLDivElement | null>, mode: "corner" | "reserve" | null): { top: number; left: number } | null {
  const [corner, setCorner] = useState<{ top: number; left: number } | null>(null);
  useEffect(() => {
    if (!mode) {
      setCorner(null);
      return;
    }
    let tallest = Infinity;
    let raf = 0;
    const measure = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        const box = mode === "reserve" ? el?.parentElement : el; // (the mat itself shrinks for a reserve: measure its row)
        const dial = document.querySelector(".turn-dial-wrap");
        if (!box || !dial) return setCorner(null);
        const m = box.getBoundingClientRect();
        const d = dial.getBoundingClientRect();
        if (d.width === 0 || d.left >= m.right || d.top >= m.bottom || d.right <= m.left) return setCorner(null);
        tallest = Math.min(tallest, Math.round(d.top - m.top));
        const next = mode === "reserve"
          ? { top: 0, left: Math.round(m.right - d.left + 10) } // (left: the width given up)
          : { top: Math.max(0, tallest), left: Math.round(d.left - m.left) };
        setCorner((c) => (c && c.top === next.top && c.left === next.left ? c : next));
      });
    };
    measure();
    const ro = new ResizeObserver(() => { tallest = Infinity; measure(); });
    const watched = mode === "reserve" ? ref.current?.parentElement : ref.current;
    if (watched) ro.observe(watched);
    const fold = () => { tallest = Infinity; measure(); };
    window.addEventListener("fyodor:dial-fold", fold);
    const dialRo = new ResizeObserver(measure);
    const watch = () => { const d = document.querySelector(".turn-dial-wrap"); if (d) dialRo.observe(d); };
    watch();
    const mo = new MutationObserver(() => { watch(); measure(); });
    const screen = document.querySelector(".game-screen");
    if (screen) mo.observe(screen, { childList: true });
    return () => { cancelAnimationFrame(raf); ro.disconnect(); dialRo.disconnect(); mo.disconnect(); window.removeEventListener("fyodor:dial-fold", fold); };
  }, [mode, ref]);
  return corner;
}

/** body.board-2d while 2D boards are on screen (the hand's height for the HUD), body.board-arranged when they're arranged. */
let boardsOnScreen = 0;
function useBoardBodyClass(arranged: boolean): void {
  useEffect(() => {
    boardsOnScreen++;
    document.body.classList.add("board-2d");
    return () => {
      if (--boardsOnScreen > 0) return;
      document.body.classList.remove("board-2d", "board-arranged");
    };
  }, []);
  useEffect(() => {
    document.body.classList.toggle("board-arranged", arranged);
  }, [arranged]);
}
