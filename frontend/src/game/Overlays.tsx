import { useEffect, useState } from "react";
import { useCardView, useGame } from "../state/gameStore";
import { useDrag } from "./dnd";
import { GameCardFace } from "./GameCardFace";
import { attachmentLinks, tetherAnchor } from "./attachments";
import { dropCaption, dropFacts, handDropKind } from "./handDrop";
import { isLand } from "./rules/intents";
import { chainEntries } from "./StackChain";
import { arrowLines } from "./stackGroups";

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
      <DropCaption ids={drag.ids} over={drag.overZone} manual={!!drag.manual} />
    </div>
  );
}

/** What letting go will do, over the table with automation on: "Cast", "Play land", or "Place by hand" while Alt is held. */
function DropCaption({ ids, over, manual }: { ids: string[]; over: string | null; manual: boolean }) {
  const view = useGame((s) => s.view);
  const facts = view ? dropFacts(ids, over, manual) : null;
  if (!facts || !view) return null;
  const kind = handDropKind(facts);
  const fromMine = handDropKind({ ...facts, manual: false }) !== "move";
  const land = !!ids[0] && (isLand(ids[0], view) || !!view.rules?.hints?.playable_lands?.includes(ids[0]));
  const text = dropCaption(kind, land, manual && fromMine);
  if (!text) return null;
  return <span className={`drop-caption ${kind}`} role="status" data-testid="drop-caption">{text}</span>;
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
 * -- playtest B3 -- a batch of identical stack objects points once at each target (×N, from its stack row), and at most
 * STACK_ARROW_CAP lines leave from the stack (stackGroups.arrowLines).
 */
export function CombatArrows() {
  const view = useGame((s) => s.view);
  const cards = view?.cards;
  const arrows = view?.arrows;
  const [lines, setLines] = useState<Line[]>([]);
  useEffect(() => {
    if (!cards || !view) return;
    const compute = () => {
      const out: Line[] = [];
      // blocks are shown by the combat strip (CombatStrip), not by lines across the table
      for (const l of arrowLines(arrows ?? [], view.stack.length ? chainEntries(view) : [])) {
        const a = locate(l.source);
        const b = a && locate(l.target);
        if (!a || !b) continue;
        const p = center(a);
        const q = center(b);
        out.push({ key: l.key, x1: p.x, y1: p.y, x2: q.x, y2: q.y, kind: l.kind, label: l.label });
      }
      setLines(out);
    };
    const raf = requestAnimationFrame(compute);
    window.addEventListener("resize", compute);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", compute);
    };
  }, [cards, arrows, view]);
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

/**
 * 2D attachment lines (game/attachments.ts): while an Aura, Equipment or Fortification or what it's attached to is
 * hovered or selected, a thin bone line joins them, with a dot on the attachment and a ring on the host (a shape,
 * not only a colour, and no arrowhead: arrows mean targeting here). It starts on the part of a tucked attachment
 * that peeks out from under its host.
 */
export function AttachLines() {
  const cards = useGame((s) => s.view?.cards);
  const hover = useGame((s) => s.hover);
  const selection = useGame((s) => s.selection);
  const focus = useGame((s) => s.focus);
  const [lines, setLines] = useState<{ key: string; x1: number; y1: number; x2: number; y2: number }[]>([]);
  useEffect(() => {
    if (!cards) return;
    const links = attachmentLinks({ cards }, [hover, ...selection]);
    if (!links.length) {
      setLines((old) => (old.length ? [] : old));
      return;
    }
    const foot = (el: Element) => {
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, hw: r.width / 2, hh: r.height / 2, rot: 0 };
    };
    const at = (id: string) => document.querySelector(`.battlefield [data-card-id="${CSS.escape(id)}"]`);
    const compute = () => {
      const out: { key: string; x1: number; y1: number; x2: number; y2: number }[] = [];
      for (const l of links) {
        const a = at(l.from);
        const b = l.player ? document.querySelector(`[data-player-id="${CSS.escape(l.to)}"]`) : at(l.to);
        if (!a || !b) continue;
        const host = foot(b);
        const from = l.player ? foot(a) : tetherAnchor(foot(a), host);
        out.push({ key: `${l.from}>${l.to}`, x1: from.x, y1: from.y, x2: host.x, y2: host.y });
      }
      setLines(out);
    };
    const raf = requestAnimationFrame(compute);
    const late = window.setTimeout(compute, 320); // again once a Look (focus) change has resized the boards
    window.addEventListener("resize", compute);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(late);
      window.removeEventListener("resize", compute);
    };
  }, [cards, hover, selection, focus]);
  if (!lines.length) return null;
  return (
    <svg className="attach-lines" data-testid="attach-lines" aria-hidden>
      {lines.map((l) => (
        <g key={l.key}>
          <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
          <circle className="from" cx={l.x1} cy={l.y1} r={3} />
          <circle className="to" cx={l.x2} cy={l.y2} r={6} />
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
