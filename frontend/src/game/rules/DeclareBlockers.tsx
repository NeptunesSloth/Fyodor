import { createPortal } from "react-dom";
import { useEffect } from "react";
import { useGame } from "../../state/gameStore";
import type { DecisionOptionView, DecisionView } from "../../types/game";
import { useDrag } from "../dnd";
import { useHoverCard } from "../hoverCard";
import { combatStats, statLine } from "./blockerLabels";
import {
  attackerOptions, blockDeclarations, blockHint, blockLimit, blockNames, blockRefusal, blockSpot2D, blockSummary, blockerOptions, menaceShort,
  openBlockDraft, setBlocks, useBlockDraft, withBlock, withoutBlock,
} from "./blockDraft";
import { send } from "./intents";
import "./attackers.css";

/**
 * The declare-blockers prompt (509.1), docked at the side of the table like the attackers prompt so the board stays in view. The
 * attackers once, as chips (stats, and how many block each); then one compact row per creature of mine: what it blocks (a select, so the
 * keyboard does everything a drag does), and for one already blocking an "also blocks" select and removable chips (a creature that can
 * block several). The plan is the one the table edits by dragging a creature onto an attacker (blockDraft.ts); the main button declares
 * it and the server says what's wrong (menace, a limit, a cost) if anything is. "No blocks" declares none at once.
 */
export function DeclareBlockers({ d }: { d: DecisionView }) {
  const draft = useBlockDraft();
  const plan = draft.decision === d.id ? draft.plan : {};
  useEffect(() => { openBlockDraft(d); }, [d]);
  const hover = useHoverCard();
  const stats = combatStats(d);
  const names = blockNames(d);
  const blockers = blockerOptions(d);
  const attackers = attackerOptions(d);
  const stat = (o: DecisionOptionView) => statLine(o.card_id ? stats[o.card_id] : undefined);
  const edit = (next: Record<string, string[]>) => setBlocks(d, next);
  const declare = (blocks = blockDeclarations(plan)) => void send({ type: "declare_blockers", blocks });
  const per = new Map<string, number>();
  for (const list of Object.values(plan)) for (const a of list) per.set(a, (per.get(a) ?? 0) + 1);
  const n = Object.keys(plan).length;
  const menace = menaceShort(d, plan);
  const optionText = (b: string, a: DecisionOptionView) => {
    const why = blockRefusal(d, b, a.id);
    return [names[a.id], stat(a)].filter(Boolean).join(" · ") + (why ? ` (can't: ${why})` : "");
  };
  return (
    <div className="decision-combat blockers" data-testid="blockers-prompt">
      <div className="attack-quick" role="group" aria-label="Quick blocks">
        <button className="tt-btn ghost" data-testid="no-blocks" title="Declare no blockers now" onClick={() => declare([])}>No blocks</button>
        <button className="tt-btn ghost" data-testid="block-clear" disabled={!n} title="Take every planned block back" onClick={() => edit({})}>Clear</button>
      </div>
      <div className="blockers-attacking" data-testid="blockers-attacking">
        <span className="blockers-head">Attacking</span>
        {attackers.map((a) => (
          <span key={a.id} className={`blockers-attacker${per.get(a.id) ? " blocked" : ""}`} {...(a.card_id ? hover(a.card_id) : {})} data-testid={`attacker-${a.id.slice(2)}`}>
            {names[a.id]}{stat(a) && <span className="combat-stat">{stat(a)}</span>}
            {per.get(a.id) ? <span className="blocked-n" title={`Blocked by ${per.get(a.id)}`}>⛨ {per.get(a.id)}</span> : null}
          </span>
        ))}
      </div>
      <span className="blockers-head">Your creatures</span>
      {blockers.map((b) => {
        const list = plan[b.id] ?? [];
        // (an "also blocks" choice only for a creature that may block another attacker: 509.1a, the server's limits)
        const others = list.length < blockLimit(d, b.id) ? attackers.filter((a) => !list.includes(a.id)) : [];
        return (
          <div key={b.id} className={`combat-row blocker-row${list.length ? " blocking" : ""}`} {...(b.card_id ? hover(b.card_id) : {})}>
            <span className="blocker-name">{names[b.id]}{stat(b) && <span className="combat-stat">{stat(b)}</span>}</span>
            <select data-testid={`block-${b.id.slice(2)}`} value={list[0] ?? ""} aria-label={`${names[b.id]} blocks`}
              onChange={(e) => edit(e.target.value ? { ...plan, [b.id]: [e.target.value, ...list.slice(1).filter((a) => a !== e.target.value)] } : withBlock(plan, b.id, ""))}>
              <option value="">Doesn't block</option>
              {attackers.map((a) => <option key={a.id} value={a.id}>{optionText(b.id, a)}</option>)}
            </select>
            {list.length > 0 && (list.length > 1 || others.length > 0) && (
              <div className="block-extra">
                {list.slice(1).map((a) => (
                  <span key={a} className="block-chip">+ {names[a]}
                    <button type="button" aria-label={`${names[b.id]} stops blocking ${names[a]}`} data-testid={`unblock-${b.id.slice(2)}-${a.slice(2)}`}
                      onClick={() => edit(withoutBlock(plan, b.id, a))}>×</button>
                  </span>
                ))}
                {others.length > 0 && (
                  <select className="block-also" data-testid={`block-also-${b.id.slice(2)}`} value="" aria-label={`${names[b.id]} also blocks`}
                    title="It can block an additional creature: Shift-drop on the table does the same"
                    onChange={(e) => e.target.value && edit(withBlock(plan, b.id, e.target.value, true))}>
                    <option value="">+ also blocks…</option>
                    {others.map((a) => <option key={a.id} value={a.id}>{optionText(b.id, a)}</option>)}
                  </select>
                )}
              </div>
            )}
          </div>
        );
      })}
      {menace.length > 0 && (
        <div className="divide-warn" role="note" data-testid="block-menace">
          {menace.map((a) => names[a]).join(", ")}: menace, it needs two or more blockers
        </div>
      )}
      <div className="decision-options">
        <span className="attack-summary" data-testid="block-summary" aria-live="polite">{blockSummary(d, plan) || "Or drag a creature onto an attacker"}</span>
        <button className="tt-btn brass" data-testid="declare-blockers" onClick={() => declare()}>{n ? `Block with ${n}` : "No blocks"}</button>
      </div>
      <BlockDragHint />
    </div>
  );
}

/** While a creature is dragged on the table during the decision: what letting go does, by the pointer ("Block Serra Angel"). */
function BlockDragHint() {
  const hint = useBlockDraft((s) => s.hint);
  const drag = useDrag((s) => s.drag); // the 2D table's drag (the 3D table sets `hint` itself)
  const view = useGame((s) => s.view);
  let shown = hint;
  if (drag && view) {
    const h = blockHint(drag.ids, blockSpot2D(view, drag.overZone, drag.x, drag.y, drag.ids));
    shown = h ? { ...h, x: drag.x, y: drag.y } : null;
  }
  if (!shown) return null;
  // (on the body, over the dragged card's ghost: the prompt's plaque is a stacking context under the drag layer)
  return createPortal(<span className={`attack-drag-hint ${shown.kind}`} role="status" data-testid="block-drag-hint" style={{ left: shown.x + 18, top: shown.y - 34 }}>{shown.text}</span>, document.body);
}
