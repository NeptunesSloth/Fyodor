import { useState } from "react";
import { isVisible, type DecisionView, type GameView } from "../../types/game";
import { GameCardFace } from "../GameCardFace";
import { useHoverCard } from "../hoverCard";
import { choose } from "./intents";
import "./looked.css";

/*
 * -- playtest (nov 18) -- "Risen Reef's ability resolves weird": a look-and-choose with a filter ("If it's a land card, you may …",
 * "reveal a creature card from among them") showed only the cards that qualify, so with none the chooser got "Done (none)" and no card.
 * The server now sends every card the chooser looked at (display.kind "looked", display.cards in library order; the options stay the
 * ones that qualify) with why the others don't ("not a land card"), to the chooser alone. Here: each card's face in library order — the ones that qualify pick
 * like any choice, the others dimmed, marked and not clickable — then the answer: the one-card gate's "Put it onto the battlefield tapped" /
 * "No" (display.take / display.otherwise), "OK" when nothing qualifies, or Done.
 */

export interface LookedRow { id: string; cardId: string | null; name: string; eligible: boolean; why: string | null }

export interface LookedPlan {
  rows: LookedRow[];
  /** "ok": nothing qualifies, one OK; "gate": one card that qualifies, take it or not; "pick": choose among the ones that qualify */
  mode: "ok" | "gate" | "pick";
  take: string | null;
  otherwise: string | null;
}

export function lookedPlan(d: DecisionView, view: Pick<GameView, "cards">): LookedPlan {
  const why = typeof d.display?.ineligible === "string" ? d.display.ineligible : "doesn't qualify";
  const options = d.options ?? [];
  const byCard = new Map(options.filter((o) => o.card_id).map((o) => [o.card_id!, o]));
  const shown = Array.isArray(d.display?.cards) ? (d.display.cards as string[]) : options.flatMap((o) => (o.card_id ? [o.card_id] : []));
  const rows = shown.map((cid): LookedRow => {
    const o = byCard.get(cid);
    const c = view.cards[cid];
    const name = c && isVisible(c) && c.name ? c.name : o?.label ?? "Card";
    return { id: o?.id ?? cid, cardId: cid, name, eligible: !!o, why: o ? null : why };
  });
  const answers = rows.filter((r) => r.eligible);
  const take = typeof d.display?.take === "string" ? d.display.take : null;
  const otherwise = typeof d.display?.otherwise === "string" ? d.display.otherwise : null;
  const mode = answers.length === 0 || (d.max_choices ?? 1) === 0 ? "ok" : take && answers.length === 1 && rows.length === 1 ? "gate" : "pick";
  return { rows, mode, take, otherwise };
}

export function LookedChoice({ d, view }: { d: DecisionView; view: GameView }) {
  const plan = lookedPlan(d, view);
  const [picked, setPicked] = useState<string[]>([]);
  const hover = useHoverCard();
  const min = d.min_choices ?? 0;
  const max = d.max_choices ?? 1;
  const send = (ids: string[]) => void choose(d.id, ids);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : max === 1 ? [id] : p.length < max ? [...p, id] : p));
  return (
    <div className="looked-choice" data-testid="looked-choice" data-mode={plan.mode}>
      <ul className="looked-cards" aria-label="The cards you looked at">
        {plan.rows.map((r) => {
          const card = r.cardId ? view.cards[r.cardId] : undefined;
          const face = card ? <GameCardFace card={card} size="small" /> : <span className="looked-name-only">{r.name}</span>;
          const on = picked.includes(r.id);
          return (
            <li key={r.id} className={`looked-card ${r.eligible ? "eligible" : "ineligible"} ${on ? "on" : ""}`}>
              {r.eligible && plan.mode === "pick" ? (
                <button type="button" className="looked-face" data-testid={`option-${r.id}`} aria-pressed={on} title={r.name}
                  onClick={() => toggle(r.id)} {...(r.cardId ? hover(r.cardId) : {})}>{face}</button>
              ) : (
                <div className={`looked-face ${r.eligible ? "" : "dim"}`} data-testid={`looked-${r.id}`} aria-disabled={!r.eligible || undefined}
                  title={r.why ? `${r.name} — ${r.why}` : r.name} {...(r.cardId ? hover(r.cardId) : {})}>{face}</div>
              )}
              <span className="looked-name">{r.name}</span>
              {r.why && <span className="looked-why" data-testid={`looked-why-${r.id}`}>{r.why}</span>}
            </li>
          );
        })}
      </ul>
      <div className="decision-options">
        {plan.mode === "ok" && (
          <button className="tt-btn brass" data-testid="decision-done" autoFocus onClick={() => send([])}>OK</button>
        )}
        {plan.mode === "gate" && (
          <>
            <button className="tt-btn" data-testid="option-take" onClick={() => send([plan.rows[0]!.id])}>{plan.take}</button>
            <button className="tt-btn ghost" data-testid="option-decline" onClick={() => send([])}>
              {plan.otherwise ? `No — ${plan.otherwise.charAt(0).toLowerCase()}${plan.otherwise.slice(1)}` : "No"}
            </button>
          </>
        )}
        {plan.mode === "pick" && (
          <button className="tt-btn brass" data-testid="decision-done" disabled={picked.length < min || picked.length > max} onClick={() => send(picked)}>
            {picked.length === 0 && min === 0 ? "Done (none)" : `Done${max > 1 ? ` (${picked.length})` : ""}`}
          </button>
        )}
      </div>
    </div>
  );
}
