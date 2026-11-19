import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { perspective, useGame } from "../../state/gameStore";
import { usePrefs } from "../../state/prefs";
import type { DecisionOptionView, DecisionView } from "../../types/game";
import { useDrag } from "../dnd";
import { matchHotkey, keyLabel } from "../hotkeys";
import { useHoverCard } from "../hoverCard";
import { attackDeclarations, attackingCount, attackTargetsFor, initialAttackPlan, mustAttack } from "./attackPlan";
import { allAt, attackHint, attackSpot2D, attackerNames, clearPlan, cyclePlan, fronts, openDraft, planAll, reachableTargets, setPlan, summaryLine, useAttackDraft } from "./attackDraft";
import { combatStats, statLine } from "./blockerLabels";
import { send } from "./intents";
import "./attackers.css";

/**
 * The declare-attackers prompt (508.1), docked at the side of the table so the board stays in view. One compact row per creature that
 * may attack: the face that is up, numbered when two share a name ("Human #1"), its power/toughness and combat keywords, and whom it
 * attacks; hovering a row shows that card. Quick actions above the rows: everything at one defender ("All → Bob", one button per player,
 * planeswalker or battle; just "Attack with all" with one), Clear (back to what must attack), and the A key cycling through the
 * defenders. The plan is the same one the table edits by dragging a creature toward an opponent (attackDraft.ts); the main button
 * declares it, and the server says what's wrong (a cost, a requirement) if anything is.
 */
export function DeclareAttackers({ d }: { d: DecisionView }) {
  const opts = d.options ?? [];
  const attackers = opts.filter((o) => o.id.startsWith("a:"));
  const draft = useAttackDraft();
  const live = draft.decision === d.id;
  const plan = live ? draft.plan : initialAttackPlan(d); // (attackPlan.ts: what must attack, 508.1d)
  const counts = live ? draft.counts : {};
  useEffect(() => { openDraft(d); }, [d]);
  const [bandPlan, setBandPlan] = useState<Record<string, string>>({});
  const hover = useHoverCard();
  const cards = useGame((s) => s.view?.cards);
  const sizes = Object.fromEntries(attackers.map((a) => [a.id, Math.max(1, cards?.[a.id.slice(2)]?.quantity ?? 1)]));
  const stats = combatStats(d);
  const names = attackerNames(d);
  const stat = (o: DecisionOptionView) => statLine(o.card_id ? stats[o.card_id] : undefined);
  const banding = new Set(Array.isArray(d.display?.banding) ? d.display.banding as string[] : []);
  const qualities = (Array.isArray(d.display?.band_qualities) ? d.display.band_qualities : []) as {
    holders: string[]; members: string[]; description: string;
  }[];
  const leaders = new Set([...banding, ...qualities.flatMap((q) => q.holders)]);
  const groups = new Map<string, string[]>();
  for (const [a, group] of Object.entries(bandPlan)) {
    if (group && plan[a]) groups.set(group, [...(groups.get(group) ?? []), a]);
  }
  const bands = [...groups.values()];
  const invalidBand = bands.some((members) => {
    const banders = members.filter((a) => banding.has(a.slice(2))).length;
    const ordinary = banders > 0 && members.length - banders <= 1;
    const qualified = qualities.some((q) => members.some((a) => q.holders.includes(a.slice(2)))
      && members.every((a) => q.members.includes(a.slice(2))));
    return (!ordinary && !qualified) || new Set(members.map((a) => plan[a])).size > 1;
  });
  const edit = (next: Record<string, string>) => { openDraft(d); setPlan(next); };
  const set = (a: string, t: string) => {
    const next = { ...plan };
    if (!t) delete next[a];
    else next[a] = t;
    edit(next);
  };
  const declare = () => void send({
    type: "declare_attackers",
    attackers: attackDeclarations(plan, counts, sizes),
    bands: bands.map((members) => members.map((a) => a.slice(2))),
  });
  const reachable = reachableTargets(d);
  const n = attackingCount(plan, counts, sizes);
  const summary = summaryLine(fronts(d, plan, sizes, counts));
  // the A key (hotkeys.ts attack_all): everything at the first defender, then the next, then back to the start
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.repeat || (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)))) return;
      if (matchHotkey(e, usePrefs.getState().keymap) !== "attack_all") return;
      e.preventDefault();
      const s = openDraft(d);
      setPlan(cyclePlan(d, s.plan));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d]);
  const key = keyLabel("attack_all", usePrefs((s) => s.keymap)) ?? "A";
  return (
    <div className="decision-combat attackers" data-testid="attackers-prompt">
      {reachable.length > 0 && (
        <div className="attack-quick" role="group" aria-label="Attack with everything that can">
          {reachable.length === 1 ? (
            <button className={`tt-btn ghost${allAt(d, plan, reachable[0]!.id) ? " on" : ""}`} data-testid={`attack-all-${reachable[0]!.id.slice(2)}`}
              aria-keyshortcuts={key} title={`Every creature that can attack ${reachable[0]!.label} does (${key})`}
              onClick={() => edit(planAll(d, plan, reachable[0]!.id))}>Attack with all <kbd>{key}</kbd></button>
          ) : reachable.map((t, i) => (
            <button key={t.id} className={`tt-btn ghost${allAt(d, plan, t.id) ? " on" : ""}`} data-testid={`attack-all-${t.id.slice(2)}`}
              title={`Every creature that can attack ${t.label} does${i === 0 ? ` (${key}; again: the next defender)` : ""}`}
              onClick={() => edit(planAll(d, plan, t.id))}>All → {t.label}{i === 0 && <kbd>{key}</kbd>}</button>
          ))}
          <button className="tt-btn ghost" data-testid="attack-clear" disabled={JSON.stringify(plan) === JSON.stringify(clearPlan(d))}
            title="Back to the start (a creature that must attack stays)" onClick={() => edit(clearPlan(d))}>Clear</button>
        </div>
      )}
      <div className="attack-rows" role="list">
        {attackers.map((a) => {
          const legal = attackTargetsFor(d, a.id);
          const at = plan[a.id];
          return (
            <label key={a.id} role="listitem" className={`combat-row attacker-row${at ? " attacking" : ""}`} data-card={a.card_id ?? undefined} {...(a.card_id ? hover(a.card_id) : {})}>
              <span className="attacker-name">{names[a.id]}{mustAttack(d, a.id) && <em className="combat-must"> (must attack)</em>}
                {stat(a) && <span className="combat-stat">{stat(a)}</span>}</span>
              <select data-testid={`attack-${a.id.slice(2)}`} value={at ?? ""} onChange={(e) => set(a.id, e.target.value)} aria-label={`${names[a.id]} attacks`}
                disabled={!legal.length} title={legal.length ? undefined : "It can't attack anyone now"}>
                <option value="">Doesn't attack</option>
                {legal.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
              {(sizes[a.id] ?? 1) > 1 && at && (
                <span className="combat-count">
                  <input type="number" min={1} max={sizes[a.id]} step={1} aria-label={`How many of the ${a.label} attack`}
                    data-testid={`attack-count-${a.id.slice(2)}`} value={counts[a.id] ?? sizes[a.id]}
                    onChange={(e) => {
                      const k = Math.floor(Number(e.target.value));
                      openDraft(d);
                      useAttackDraft.setState((s) => ({ counts: { ...s.counts, [a.id]: Math.min(sizes[a.id] ?? 1, Math.max(1, Number.isFinite(k) ? k : 1)) } }));
                    }} />
                  <span className="combat-count-of">of {(sizes[a.id] ?? 1).toLocaleString("en-US")}</span>
                </span>
              )}
              {leaders.size > 0 && at && (
                <select aria-label={`Band for ${a.label}`} data-testid={`band-${a.id.slice(2)}`}
                  value={bandPlan[a.id] ?? ""} onChange={(e) => setBandPlan({ ...bandPlan, [a.id]: e.target.value })}>
                  <option value="">No band</option>
                  {Array.from({ length: leaders.size }, (_, i) => <option key={i + 1} value={String(i + 1)}>Band {i + 1}</option>)}
                </select>
              )}
            </label>
          );
        })}
      </div>
      {invalidBand && <div role="alert">{qualities.length
        ? "Each band needs compatible banding abilities, matching creatures, and the same defender."
        : "Each band needs banding, at most one creature without it, and the same defender."}</div>}
      <div className="decision-options">
        <span className="attack-summary" data-testid="attack-summary" aria-live="polite">{summary || "Or drag a creature toward an opponent"}</span>
        <button className="tt-btn brass" data-testid="declare-attackers" disabled={invalidBand} onClick={declare}>
          {Object.keys(plan).length ? `Attack with ${n.toLocaleString("en-US")}` : "No attack"}
        </button>
      </div>
      <AttackDragHint />
    </div>
  );
}

/** While a creature is dragged on the table during the decision: what letting go does, by the pointer ("Attack Bob"). */
function AttackDragHint() {
  const hint = useAttackDraft((s) => s.hint);
  const drag = useDrag((s) => s.drag); // the 2D table's drag (the 3D table sets `hint` itself)
  const view = useGame((s) => s.view);
  let shown = hint;
  if (drag && view) {
    const spot = attackSpot2D(view, perspective(view, useGame.getState().actingAs), drag.overZone, drag.x, drag.y);
    const h = attackHint(drag.ids, spot);
    shown = h ? { ...h, x: drag.x, y: drag.y } : null;
  }
  if (!shown) return null;
  // (on the body, over the dragged card's ghost: the prompt's plaque is a stacking context under the drag layer)
  return createPortal(<span className={`attack-drag-hint ${shown.kind}`} role="status" data-testid="attack-drag-hint" style={{ left: shown.x + 18, top: shown.y - 34 }}>{shown.text}</span>, document.body);
}
