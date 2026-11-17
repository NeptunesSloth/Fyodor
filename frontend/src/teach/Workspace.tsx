/**
 * -- Teach Fyodor -- the script workspace: each ability a stack of rounded rows (a When row on top, its pieces indented under
 * it, nested groups for "You may" / "If you do" / "You may pay"), every row with its category's coloured square, bold label
 * and white value chips you tap to change. Drop slots appear between rows while something is dragged; the keyboard moves
 * (arrows), removes (Delete) and edits chips (Enter) without one.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon } from "../components/Icon";
import { ManaText } from "../cards/ManaText";
import type { DragItem, DragState } from "./drag";
import { CONTAINERS, type Node, type Path, type Script } from "./script";
import { render } from "./sentence";
import type { Piece, Slot, Value, Vocabulary } from "./types";

export const spotKey = (path: Path) => `${path.ability}:${path.index.join(".")}`;
export const chipKey = (uid: string, slot: string) => `${uid}/${slot}`;

export interface WorkspaceProps {
  script: Script;
  voc: Vocabulary;
  pieces: Record<string, Piece>;
  active: number;
  setActive: (i: number) => void;
  drag: DragState | null;
  allowed: Set<string>; // spot keys the dragged piece may snap to
  chipTargets: Set<string>; // chip keys a dragged chip may land on
  onStartDrag: (e: React.PointerEvent, item: DragItem) => void;
  onSetValue: (path: Path, key: string, value: Value) => void;
  onRemove: (path: Path) => void;
  onMoveKey: (path: Path, dir: -1 | 1) => void;
  onRemoveAbility: (index: number) => void;
  onAddAbility: () => void;
  focusUid: string | null;
  me: string;
}

const numberWord = (v: Value) => (v === "N" ? "N" : v === "-N" ? "−N" : typeof v === "number" && v > 0 ? `${v}` : String(v));

function chipText(slot: Slot, value: Value, voc: Vocabulary, me: string): ReactNode {
  if (slot.kind === "choice") return (voc.options[String(value)]?.text ?? String(value)).replace("{self}", me);
  if (slot.kind === "mana") return <ManaText text={String(value)} />;
  if (slot.kind === "signed" && typeof value === "number") return value >= 0 ? `+${value}` : String(value);
  return numberWord(value);
}

/** The popover under a chip: options to pick, or a number to step (and N for a keyword with a number). */
function ChipEditor({ slot, value, voc, param, me, onPick, onClose }: {
  slot: Slot; value: Value; voc: Vocabulary; param: boolean; me: string; onPick: (v: Value) => void; onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [text, setText] = useState(String(value));
  useEffect(() => {
    const first = box.current?.querySelector<HTMLElement>("button, input");
    first?.focus();
    const away = (e: PointerEvent) => { if (box.current && !box.current.contains(e.target as globalThis.Node)) onClose(); };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [onClose]);
  const key = (e: React.KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
  if (slot.kind === "choice") {
    return (
      <div className="t-pop" ref={box} role="listbox" aria-label="Choose" onKeyDown={key}>
        {slot.options.map((o) => (
          <button key={o} type="button" role="option" aria-selected={o === value} className={`t-opt ${o === value ? "on" : ""} ${voc.options[o]?.cat === "target" ? "cat-target" : ""}`}
            onClick={() => { onPick(o); onClose(); }}>{(voc.options[o]?.text ?? o).replace("{self}", me) || "(none)"}</button>
        ))}
      </div>
    );
  }
  if (slot.kind === "mana") {
    const add = (sym: string) => setText((t) => t + sym);
    const commit = () => { onPick(text.trim()); onClose(); };
    return (
      <div className="t-pop t-pop-mana" ref={box} onKeyDown={key}>
        <label className="t-pop-row">
          <span>Mana cost</span>
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && commit()} aria-label="Mana cost, like {2}{U}" />
        </label>
        <div className="t-pop-syms">
          {["{1}", "{2}", "{3}", "{W}", "{U}", "{B}", "{R}", "{G}", "{C}", ...(param ? ["{N}"] : [])].map((s) => (
            <button key={s} type="button" onClick={() => add(s)} aria-label={`add ${s}`}><ManaText text={s} /></button>
          ))}
          <button type="button" className="t-opt" onClick={() => setText("")}>clear</button>
        </div>
        <button type="button" className="btn small primary" onClick={commit}>Use it</button>
      </div>
    );
  }
  const num = typeof value === "number" ? value : slot.default;
  const step = (d: number) => onPick(Math.min(slot.max, Math.max(slot.min, num + d)));
  return (
    <div className="t-pop t-pop-num" ref={box} onKeyDown={key}>
      <div className="t-pop-row">
        <button type="button" onClick={() => step(-1)} aria-label="less" disabled={num <= slot.min}>−</button>
        <input type="number" min={slot.min} max={slot.max} value={typeof value === "number" ? value : ""} placeholder={String(value)}
          onChange={(e) => { const v = parseInt(e.target.value, 10); if (!Number.isNaN(v) && v >= slot.min && v <= slot.max) onPick(v); }}
          onKeyDown={(e) => e.key === "Enter" && onClose()} aria-label="Number" />
        <button type="button" onClick={() => step(1)} aria-label="more" disabled={num >= slot.max}>+</button>
      </div>
      <div className="t-pop-syms">
        {[1, 2, 3, 4, 5].filter((v) => v >= slot.min && v <= slot.max).map((v) => (
          <button key={v} type="button" className={`t-opt ${value === v ? "on" : ""}`} onClick={() => { onPick(v); onClose(); }}>{v}</button>
        ))}
        {slot.param && param && (
          <>
            <button type="button" className={`t-opt t-n ${value === "N" ? "on" : ""}`} title="The number after the keyword (Dive 2 → 2)" onClick={() => { onPick("N"); onClose(); }}>N</button>
            {slot.kind === "signed" && <button type="button" className={`t-opt t-n ${value === "-N" ? "on" : ""}`} onClick={() => { onPick("-N"); onClose(); }}>−N</button>}
          </>
        )}
      </div>
      {slot.param && !param && <p className="t-pop-hint">Tick “has a number” on the keyword to use N here.</p>}
    </div>
  );
}

interface RowProps extends Omit<WorkspaceProps, "script" | "active" | "setActive" | "onRemoveAbility" | "onAddAbility"> {
  node: Node; path: Path; isHat?: boolean; param: boolean;
}

function Row({ node, path, isHat, pieces, voc, drag, chipTargets, onStartDrag, onSetValue, onRemove, onMoveKey, focusUid, me, param, allowed }: RowProps) {
  const piece = pieces[node.id];
  const [editing, setEditing] = useState<string | null>(null);
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => { if (focusUid === node.uid) el.current?.focus(); }, [focusUid, node.uid]);
  if (!piece) return null;
  const dragging = drag?.item.kind === "node" && drag.item.uid === node.uid;
  // the label with its settings as chips, in the order the sentence says them
  const parts: ReactNode[] = [];
  const slots = piece.slots ?? {};
  const seen = new Set<string>();
  const re = /\{([a-z]+)(?::[a-z]+)?\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  const text = piece.text;
  // words between chips: the card's own name and a slot's second mention ("card{n:s}" → "cards") written out, as the sentence says them
  const words = (s: string) => render(s, node.values, voc, { me, n: null });
  while ((m = re.exec(text))) {
    const key = m[1]!;
    if (!(key in slots) || seen.has(key)) continue; // ({self}, a repeat of a slot: the label words carry it)
    seen.add(key);
    const before = words(text.slice(last, m.index)).trim();
    if (before) parts.push(<span key={`t${m.index}`}>{before} </span>);
    last = m.index + m[0].length;
    const slot = slots[key]!;
    const ck = chipKey(node.uid, key);
    const hot = drag?.item.kind === "chip" && chipTargets.has(ck);
    const target = drag?.target === `chip:${ck}`;
    parts.push(
      <span key={key} className="t-chipwrap">
        <button type="button" className={`t-chip ${slot.kind === "choice" && voc.options[String(node.values[key])]?.cat === "target" ? "is-target" : ""} ${hot ? "hot" : ""} ${target ? "snap" : ""}`}
          data-chip={ck} aria-label={`${key}: ${String(node.values[key])}. Change`} aria-expanded={editing === key}
          onClick={() => setEditing(editing === key ? null : key)} onPointerDown={(e) => e.stopPropagation()}>
          {chipText(slot, node.values[key] ?? slot.default, voc, me)}
        </button>
        {editing === key && <ChipEditor slot={slot} value={node.values[key] ?? slot.default} voc={voc} param={param} me={me}
          onPick={(v) => onSetValue(path, key, v)} onClose={() => { setEditing(null); el.current?.focus(); }} />}
      </span>,
    );
  }
  const tail = words(text.slice(last));
  if (parts.length === 0) parts.push(<span key="label">{piece.label}</span>);
  else if (tail.trim()) parts.push(<span key="tail" className={tail.startsWith(" ") ? "" : "t-glued"}>{tail.trim()}</span>);
  const fixed = piece.role === "action_hat"; // (the action's hat stays: it is what is being taught)
  const onKey = (e: React.KeyboardEvent) => {
    if (e.target !== el.current) return;
    if ((e.key === "Delete" || e.key === "Backspace") && !fixed) { e.preventDefault(); onRemove(path); }
    else if (e.key === "ArrowUp" && !isHat) { e.preventDefault(); onMoveKey(path, -1); }
    else if (e.key === "ArrowDown" && !isHat) { e.preventDefault(); onMoveKey(path, 1); }
    else if (e.key === "Enter" && Object.keys(slots).length) { e.preventDefault(); setEditing(Object.keys(slots)[0]!); }
  };
  const container = CONTAINERS.has(piece.role);
  return (
    <div className={`t-rowwrap ${container ? "has-kids" : ""}`}>
      <div ref={el} className={`t-row cat-${piece.cat} ${isHat ? "is-hat" : ""} ${dragging ? "lifting" : ""}`} tabIndex={0} role="listitem"
        data-row={node.uid} aria-label={`${piece.label}${isHat ? " (when)" : ""}. Arrow keys move, Delete removes, Enter edits`}
        onKeyDown={onKey} onPointerDown={(e) => onStartDrag(e, { kind: "node", uid: node.uid, piece })}>
        <span className="t-sq" aria-hidden />
        <span className="t-label">{parts}</span>
        {!fixed && (
          <button type="button" className="t-x" aria-label={`Remove ${piece.label}`} onClick={() => onRemove(path)} onPointerDown={(e) => e.stopPropagation()}>
            <Icon name="close" size={14} />
          </button>
        )}
      </div>
      {container && (
        <div className="t-kids" role="list">
          {(node.body ?? []).map((child, i) => (
            <Row key={child.uid} node={child} path={{ ability: path.ability, index: [...path.index, i] }} pieces={pieces} voc={voc} drag={drag}
              allowed={allowed} chipTargets={chipTargets} onStartDrag={onStartDrag} onSetValue={onSetValue} onRemove={onRemove} onMoveKey={onMoveKey}
              focusUid={focusUid} me={me} param={param} />
          ))}
          <Spot path={{ ability: path.ability, index: [...path.index, (node.body ?? []).length] }} drag={drag} allowed={allowed}
            label={(node.body ?? []).length ? "" : piece.role === "may" ? "drop a Do piece here" : "drop pieces here"} />
        </div>
      )}
    </div>
  );
}

/** A slot between rows: a quiet dotted line while idle, a bar that lights up when the dragged piece may land here. */
function Spot({ path, drag, allowed, label }: { path: Path; drag: DragState | null; allowed: Set<string>; label?: string }) {
  const key = spotKey(path);
  const ok = !!drag && drag.item.kind !== "chip" && allowed.has(key);
  const hot = drag?.target === `spot:${key}`;
  return (
    <div className={`t-spot ${ok ? "ok" : ""} ${hot ? "hot" : ""} ${label ? "t-spot-empty" : ""}`} data-spot={ok ? key : undefined} aria-hidden>
      {label && <span>{label}</span>}
    </div>
  );
}

export function Workspace(props: WorkspaceProps) {
  const { script, pieces, active, setActive, drag, allowed, onRemoveAbility, onAddAbility, me } = props;
  const param = script.param;
  return (
    <div className="t-work" role="region" aria-label="Script workspace">
      {script.abilities.map((ab, a) => {
        const hatKey = spotKey({ ability: a, index: [] });
        const hatOk = !!drag && drag.item.kind !== "chip" && allowed.has(hatKey);
        const hatHot = drag?.target === `spot:${hatKey}`;
        return (
          <section key={ab.uid} className={`t-ability ${a === active ? "on" : ""}`} aria-label={`Ability ${a + 1}`} onPointerDownCapture={() => setActive(a)}>
            <header className="t-ab-head">
              <span>{script.kind === "action" ? "What happens" : `Ability ${a + 1}`}</span>
              {script.abilities.length > 1 && (
                <button type="button" className="t-x" aria-label={`Remove ability ${a + 1}`} onClick={() => onRemoveAbility(a)}><Icon name="close" size={14} /></button>
              )}
            </header>
            <div role="list" className="t-stack">
              {ab.hat ? (
                <>
                  <div className={`t-hatspot ${hatOk ? "ok" : ""} ${hatHot ? "hot" : ""}`} data-spot={hatOk ? hatKey : undefined} aria-hidden={!hatOk} />
                  <Row {...props} node={ab.hat} path={{ ability: a, index: [] }} isHat param={param} />
                </>
              ) : (
                <div className={`t-row t-empty-hat ${hatOk ? "ok" : ""} ${hatHot ? "hot" : ""}`} data-spot={hatOk ? hatKey : undefined} role="listitem">
                  <span className="t-sq" aria-hidden />
                  <span className="t-label">Start with a <b>When</b> piece — <i>Enters</i>, <i>Attacks</i>, <i>Pay to use it</i>, <i>Always</i> …</span>
                </div>
              )}
              <div className="t-body">
                {ab.body.map((n, i) => (
                  <div key={n.uid}>
                    <Spot path={{ ability: a, index: [i] }} drag={drag} allowed={allowed} />
                    <Row {...props} node={n} path={{ ability: a, index: [i] }} param={param} />
                  </div>
                ))}
                <Spot path={{ ability: a, index: [ab.body.length] }} drag={drag} allowed={allowed}
                  label={ab.hat && !ab.body.length ? (pieces[ab.hat.id]?.role === "static_hat" ? "drop an Always piece here" : pieces[ab.hat.id]?.role === "activated" ? "drop a Cost, then Do pieces" : "drop Do pieces here") : ""} />
              </div>
            </div>
          </section>
        );
      })}
      {script.kind !== "action" && (
        <button type="button" className="t-addab" onClick={onAddAbility} disabled={script.abilities.length >= 4}>
          <Icon name="plus" size={14} /> Another ability
        </button>
      )}
      <div className="t-me">{script.kind === "action" ? "The creature the card names is “it”: cards say “it dives”, “target creature dives”." : `The card calls itself “${me}”.`}</div>
    </div>
  );
}
