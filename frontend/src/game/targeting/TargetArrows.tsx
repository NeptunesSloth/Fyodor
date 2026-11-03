/**
 * The 2D table's targeting arrows: from the source (the spell in the bar, the stack row or the permanent whose ability it
 * is) to the candidate under the pointer or keyboard focus, and to each chosen one with its number. Positions come from
 * the DOM ([data-card-id] and the plaques' [data-player-id] boxes), so they follow any board layout; they are measured
 * again when the board changes, the window resizes or a Look moves the boards, never every frame.
 */
import { useEffect, useState } from "react";
import { useGame } from "../../state/gameStore";
import type { GameView } from "../../types/game";
import { bow, edgePoint, type Pt } from "./arrowPath";
import { useTargeting, type Pick } from "./store";
import type { Targeting } from "./targeting";

/** n: the order it was chosen in (0: not chosen); badge: draw that number at the arrow's end (a card on the table wears its own). */
interface Arrow { key: string; d: string; end: Pt; n: number; live: boolean; badge: boolean }

const q = (sel: string) => {
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
};

/** The element that stands for a card or player on the 2D table now (a pile for a card in a graveyard), or its tray thumbnail. */
export function locate(ref: string, view: GameView | null): Element | null {
  const id = CSS.escape(ref);
  if (view?.players.some((p) => p.id === ref)) return q(`.t3d-seat[data-player-id="${id}"]`) ?? q(`.tgt-thumb[data-ref="${id}"]`);
  const zone = view?.cards[ref]?.zone;
  return q(`.battlefield [data-card-id="${id}"]`) ?? q(`.command-zone [data-card-id="${id}"]`) ?? q(`.chain-list [data-card-id="${id}"]`)
    ?? (zone?.endsWith(":hand") ? q(`body:has(.tgt-bar[data-dock="above-hand"]) .hand-card[data-card-id="${id}"]`) : null)
    ?? (zone ? q(`[data-drop="${CSS.escape(zone)}"]`) : null) ?? q(`.tgt-thumb[data-ref="${id}"]`);
}

/** Where the arrows leave from: the source on the table or on the stack, else the spell's art in the bar. */
function origin(t: Targeting, art: HTMLElement | null): Element | null {
  if (t.source) {
    const id = CSS.escape(t.source);
    const el = q(`.battlefield [data-card-id="${id}"]`) ?? q(`.command-zone [data-card-id="${id}"]`) ?? q(`.chain-list [data-card-id="${id}"]`);
    if (el) return el;
  }
  return art;
}

export function TargetArrows({ t, origin: art, picked }: { t: Targeting; origin: React.RefObject<HTMLElement | null>; picked: Pick[] }) {
  const pointed = useTargeting((s) => s.hot ?? s.focus);
  const boardHover = useGame((s) => s.hover);
  const look = useGame((s) => s.focus);
  const view = useGame((s) => s.view);
  const live = pointed ?? (boardHover && t.candidates.some((c) => c.ref === boardHover) ? boardHover : null);
  const [arrows, setArrows] = useState<{ from: Pt | null; list: Arrow[] }>({ from: null, list: [] });
  useEffect(() => {
    const compute = () => {
      const src = origin(t, art.current);
      if (!src) return setArrows({ from: null, list: [] });
      const sb = src.getBoundingClientRect();
      const inBar = src === art.current;
      // from the top edge of the spell in the bar, from the middle of a card on the table
      const from = inBar ? { x: sb.left + sb.width / 2, y: sb.top + 4 } : { x: sb.left + sb.width / 2, y: sb.top + sb.height / 2 };
      const list: Arrow[] = [];
      const add = (ref: string, n: number, isLive: boolean) => {
        const el = locate(ref, view);
        if (!el || el === src) return;
        const end = edgePoint(el.getBoundingClientRect(), from);
        if (Math.hypot(end.x - from.x, end.y - from.y) < 24) return;
        list.push({ key: ref, d: bow(from, end).d, end, n, live: isLive, badge: n > 0 && !el.closest(".table-card") });
      };
      picked.forEach((p, i) => add(p.ref, i + 1, p.ref === live));
      if (live && !picked.some((p) => p.ref === live)) add(live, 0, true);
      setArrows({ from: list.length ? from : null, list });
    };
    const raf = requestAnimationFrame(compute);
    const late = window.setTimeout(compute, 340); // again once a Look has resized the boards
    window.addEventListener("resize", compute);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(late);
      window.removeEventListener("resize", compute);
    };
  }, [t, art, picked, live, view, look]);
  if (!arrows.list.length || !arrows.from) return null;
  return (
    <svg className="tgt-arrows" data-testid="targeting-arrows" aria-hidden>
      <defs>
        <marker id="tgt-head" viewBox="0 0 12 12" markerWidth="12" markerHeight="12" refX="9" refY="6" orient="auto" markerUnits="userSpaceOnUse">
          <path d="M1,1.5 L11,6 L1,10.5 L3.4,6 z" className="tgt-head" />
        </marker>
      </defs>
      <circle className="tgt-from" cx={arrows.from.x} cy={arrows.from.y} r={5} />
      {arrows.list.map((a) => (
        <g key={a.key} className={`tgt-arrow ${a.live ? "live" : ""} ${a.n ? "chosen" : ""}`}>
          <path className="tgt-cord-under" d={a.d} />
          <path className="tgt-cord" d={a.d} markerEnd={a.n ? undefined : "url(#tgt-head)"} />
          {a.badge ? (
            <g className="tgt-badge" transform={`translate(${a.end.x},${a.end.y})`}>
              <circle r={10} />
              <text dy="0.35em">{a.n}</text>
            </g>
          ) : a.n > 0 && <circle className="tgt-pin" cx={a.end.x} cy={a.end.y} r={4.5} />}
        </g>
      ))}
    </svg>
  );
}
