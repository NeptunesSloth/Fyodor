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
}

/** Arrows from blockers to the attackers they block (drawn over the whole table). */
export function CombatArrows() {
  const cards = useGame((s) => s.view?.cards);
  const [lines, setLines] = useState<Line[]>([]);
  useEffect(() => {
    if (!cards) return;
    const compute = () => {
      const out: Line[] = [];
      for (const c of Object.values(cards)) {
        if (!c.blocking) continue;
        const a = document.querySelector<HTMLElement>(`.battlefield [data-card-id="${CSS.escape(c.id)}"]`);
        const b = document.querySelector<HTMLElement>(`.battlefield [data-card-id="${CSS.escape(c.blocking)}"]`);
        if (!a || !b) continue;
        const ra = a.getBoundingClientRect();
        const rb = b.getBoundingClientRect();
        out.push({ key: c.id, x1: ra.left + ra.width / 2, y1: ra.top + ra.height / 2, x2: rb.left + rb.width / 2, y2: rb.top + rb.height / 2 });
      }
      setLines(out);
    };
    const raf = requestAnimationFrame(compute);
    window.addEventListener("resize", compute);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", compute);
    };
  }, [cards]);
  if (!lines.length) return null;
  return (
    <svg className="combat-arrows">
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="#6aa7e8" />
        </marker>
      </defs>
      {lines.map((l) => (
        <line key={l.key} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} markerEnd="url(#arrowhead)" />
      ))}
    </svg>
  );
}
