import { useEffect, useState } from "react";
import { useCardView, useGame } from "../state/gameStore";
import { useDrag } from "./dnd";
import { GameCardFace } from "./GameCardFace";

/** Card ghosts that follow the pointer while dragging. */
export function DragLayer() {
  const drag = useDrag((s) => s.drag);
  if (!drag) return null;
  return (
    <div className="drag-layer" style={{ left: drag.x - drag.offsetX, top: drag.y - drag.offsetY, width: drag.width }}>
      {drag.ids.slice(0, 5).map((id, i) => (
        <GhostCard key={id} id={id} index={i} />
      ))}
      {drag.ids.length > 1 && <span className="drag-count">{drag.ids.length}</span>}
    </div>
  );
}

function GhostCard({ id, index }: { id: string; index: number }) {
  const card = useCardView(id);
  if (!card) return null;
  return (
    <div className="ghost" style={{ transform: `translate(${index * 10}px, ${index * 10}px)` }}>
      <GameCardFace card={card} />
    </div>
  );
}

interface Line {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  kind: "block" | "target" | "attack" | "custom";
  label?: string;
}

const center = (el: Element) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
};

function locate(ref: string): Element | null {
  return (
    document.querySelector(`.battlefield [data-card-id="${CSS.escape(ref)}"]`) ??
    document.querySelector(`.chain-list [data-card-id="${CSS.escape(ref)}"]`) ??
    document.querySelector(`[data-player-id="${CSS.escape(ref)}"]`)
  );
}

/**
 * Arrows over the whole table: blockers → attackers, plus every arrow players drew
 * (targets, attacks, custom). Kept thin and translucent so a busy Commander board stays readable.
 */
export function CombatArrows() {
  const cards = useGame((s) => s.view?.cards);
  const arrows = useGame((s) => s.view?.arrows);
  const [lines, setLines] = useState<Line[]>([]);
  useEffect(() => {
    if (!cards) return;
    const compute = () => {
      const out: Line[] = [];
      for (const c of Object.values(cards)) {
        if (!c.blocking) continue;
        const a = locate(c.id);
        if (!a) continue;
        for (const target of [c.blocking, ...(c.blocking_more ?? [])]) {
          const b = locate(target);
          if (!b) continue;
          const p = center(a);
          const q = center(b);
          out.push({ key: `blk-${c.id}-${target}`, x1: p.x, y1: p.y, x2: q.x, y2: q.y, kind: "block" });
        }
      }
      for (const ar of arrows ?? []) {
        const a = locate(ar.source);
        if (!a) continue;
        const p = center(a);
        ar.targets.forEach((t, i) => {
          const b = locate(t);
          if (!b) return;
          const q = center(b);
          out.push({ key: `${ar.id}-${t}`, x1: p.x, y1: p.y, x2: q.x, y2: q.y, kind: ar.kind, label: i === 0 ? ar.label : undefined });
        });
      }
      setLines(out);
    };
    const raf = requestAnimationFrame(compute);
    window.addEventListener("resize", compute);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", compute);
    };
  }, [cards, arrows]);
  if (!lines.length) return null;
  return (
    <svg className="combat-arrows" data-testid="table-arrows">
      <defs>
        {(["block", "target", "attack", "custom"] as const).map((k) => (
          <marker key={k} id={`arrowhead-${k}`} markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className={`head ${k}`} />
          </marker>
        ))}
      </defs>
      {lines.map((l) => (
        <g key={l.key} className={`arrow ${l.kind}`}>
          <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} markerEnd={`url(#arrowhead-${l.kind})`} />
          {l.label && <text x={(l.x1 + l.x2) / 2} y={(l.y1 + l.y2) / 2 - 6}>{l.label}</text>}
        </g>
      ))}
    </svg>
  );
}

/** A click on a card or player while picking targets. */
export function pickClick(id: string): void {
  const cur = useGame.getState().pick;
  if (!cur) return;
  if (!cur.multi) {
    useGame.getState().setPick(null);
    cur.onDone([id]);
    return;
  }
  const picked = cur.picked.includes(id) ? cur.picked.filter((x) => x !== id) : [...cur.picked, id];
  useGame.getState().setPick({ ...cur, picked });
}

/**
 * Pick mode: while choosing targets, clicks on cards and players pick them instead of acting.
 * Esc cancels; Done finishes a multi-pick.
 */
export function PickLayer() {
  const pick = useGame((s) => s.pick);
  useEffect(() => {
    if (!pick) return;
    const onDown = (e: PointerEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest(".pick-bar")) return;
      const cardEl = el.closest<HTMLElement>("[data-card-id]");
      const playerEl = pick.players ? el.closest<HTMLElement>("[data-player-id]") : null;
      const id = cardEl?.dataset.cardId ?? playerEl?.dataset.playerId;
      if (!id) return;
      e.preventDefault();
      e.stopPropagation();
      pickClick(id);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        useGame.getState().setPick(null);
      }
      if (e.key === "Enter") {
        const cur = useGame.getState().pick;
        useGame.getState().setPick(null);
        cur?.onDone(cur.picked);
      }
    };
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("keydown", onKey, true);
    document.body.classList.add("picking");
    return () => {
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("keydown", onKey, true);
      document.body.classList.remove("picking");
    };
  }, [pick]);
  useEffect(() => {
    document.querySelectorAll(".picked").forEach((el) => el.classList.remove("picked"));
    for (const id of pick?.picked ?? []) {
      document.querySelectorAll(`[data-card-id="${CSS.escape(id)}"], [data-player-id="${CSS.escape(id)}"]`).forEach((el) => el.classList.add("picked"));
    }
  }, [pick]);
  if (!pick) return null;
  return (
    <div className="pick-bar" data-testid="pick-bar">
      <span>{pick.prompt}{pick.multi ? ` · ${pick.picked.length} chosen` : ""}</span>
      <span className="hint">{pick.multi ? "Click cards or players · Enter when done" : "Click a card"} · Esc cancels</span>
      {pick.multi && (
        <button className="tt-btn brass" data-testid="pick-done" disabled={!pick.picked.length} onClick={() => {
          useGame.getState().setPick(null);
          pick.onDone(pick.picked);
        }}>Done</button>
      )}
      <button className="tt-btn ghost" onClick={() => useGame.getState().setPick(null)}>Cancel</button>
    </div>
  );
}
