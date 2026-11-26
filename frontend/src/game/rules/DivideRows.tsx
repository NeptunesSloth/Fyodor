import { useState } from "react";
import type { DecisionOptionView, DecisionView } from "../../types/game";
import { useHoverCard } from "../hoverCard";
import { divide } from "./intents";
import { statLine, type CombatStats } from "./blockerLabels";
import "./attackers.css";

/*
 * -- playtest (nov 18) -- "divide N among …" (601.2d spells and abilities, 510.1c-d combat damage), as compact rows like the attackers and
 * blockers prompts: one row per recipient in the server's order (510.1c: the damage assignment order), with − [n] + and, in combat, each
 * blocker's power/toughness, damage already marked and the damage that is lethal to it now (deathtouch: 1); a trampler's player or
 * planeswalker row comes last and takes the rest. Quick fills on top; a live total; the server judges the division and says what's wrong.
 */

interface Row extends DecisionOptionView { need: number | null; stats?: CombatStats & { damage?: number }; free: boolean }

export function divideRows(d: DecisionView): { rows: Row[]; total: number; least: number; combat: boolean; deathtouch: boolean } {
  const options = d.options ?? [];
  const total = Number(d.display?.total ?? 0);
  const least = Number(d.display?.least ?? 1);
  const lethal = (d.display?.lethal as number[] | undefined) ?? [];
  const need = (d.display?.need as number[] | undefined) ?? lethal;
  const free = typeof d.display?.free === "number" ? d.display.free : lethal.length && options.length > lethal.length ? lethal.length : -1;
  const stats = (d.display?.stats ?? {}) as Record<string, CombatStats & { damage?: number }>;
  const many = new Map<string, number>();
  for (const o of options) many.set(o.label, (many.get(o.label) ?? 0) + 1);
  const seen = new Map<string, number>();
  const rows = options.map((o, i) => {
    const k = (seen.get(o.label) ?? 0) + 1;
    seen.set(o.label, k);
    const label = (many.get(o.label) ?? 0) > 1 ? `${o.label} #${k}` : o.label; // three Soldier tokens: Soldier #1, #2, #3
    return { ...o, label, need: i !== free && need[i] != null ? need[i]! : null, stats: o.card_id ? stats[o.card_id] : undefined, free: i === free };
  });
  return { rows, total, least, combat: d.display?.what === "damage" && need.length > 0, deathtouch: d.display?.deathtouch === true };
}

/** Lethal damage to each blocker in order while it lasts; the rest to what a trampler attacks, else to the first blocker. */
export function lethalFill(rows: Row[], total: number, least: number): number[] {
  let left = total;
  const out = rows.map((r) => {
    if (r.free) return 0;
    const n = Math.max(least, Math.min(left, r.need ?? least));
    left -= n;
    return n;
  });
  const rest = rows.findIndex((r) => r.free);
  out[rest >= 0 ? rest : 0]! += Math.max(0, left);
  return out;
}

/** Everything to the first row (the others at their least). */
export function firstFill(rows: Row[], total: number, least: number): number[] {
  return rows.map((_, i) => (i === 0 ? Math.max(least, total - (rows.length - 1) * least) : least));
}

/** As evenly as it goes, the odd ones to the first rows. */
export function evenFill(rows: Row[], total: number, least: number): number[] {
  const n = rows.length || 1;
  const base = Math.max(least, Math.floor(total / n));
  let extra = total - base * n;
  return rows.map(() => base + (extra-- > 0 ? 1 : 0));
}

export function DivideRows({ d }: { d: DecisionView }) {
  const { rows, total, least, combat, deathtouch } = divideRows(d);
  const hover = useHoverCard();
  const [amounts, setAmounts] = useState<number[]>(() => (combat ? lethalFill(rows, total, least) : firstFill(rows, total, least)));
  const sum = amounts.reduce((a, b) => a + b, 0);
  const upto = d.display?.upto === true; // 115.6: "distribute up to N" may divide fewer than N
  const ok = upto ? sum <= total : sum === total;
  const set = (i: number, v: number) => setAmounts((xs) => xs.map((x, k) => (k === i ? Math.max(least, Math.min(total, Math.floor(v) || 0)) : x)));
  const others = (i: number) => amounts.reduce((a, b, k) => (k === i ? a : a + b), 0);
  const freeRow = rows.find((r) => r.free);
  const short = freeRow && (amounts[rows.indexOf(freeRow)] ?? 0) > 0 && rows.some((r, i) => r.need != null && (amounts[i] ?? 0) < r.need);
  const fmt = (n: number) => n.toLocaleString("en-US");
  const noun = d.display?.what === "counters" ? "counters" : "damage";
  const submit = () => { if (ok) void divide(d.id, amounts); };
  return (
    <div className="decision-combat divide-rows" data-testid="divide-rows" onKeyDown={(e) => { if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") submit(); }}>
      <div className="attack-quick" role="group" aria-label="Quick fills">
        {combat && (
          <button className="tt-btn ghost" data-testid="divide-lethal" onClick={() => setAmounts(lethalFill(rows, total, least))}>
            {freeRow ? `Lethal to each, rest to ${freeRow.label}` : "Lethal to each in order"}
          </button>
        )}
        {rows.length > 1 && (
          <button className="tt-btn ghost" data-testid="divide-first" onClick={() => setAmounts(firstFill(rows, total, least))}>All to {rows[0]!.label}</button>
        )}
        {!combat && rows.length > 1 && <button className="tt-btn ghost" data-testid="divide-even" onClick={() => setAmounts(evenFill(rows, total, least))}>Evenly</button>}
      </div>
      <div className="attack-rows" role="list">
        {rows.map((r, i) => {
          const n = amounts[i] ?? least;
          const facts = [r.stats ? statLine(r.stats) : "", r.stats?.damage ? `${fmt(r.stats.damage)} marked` : "",
            r.need != null ? `lethal ${fmt(r.need)}${deathtouch ? " (deathtouch)" : ""}` : "", r.free ? "takes the rest (trample)" : ""].filter(Boolean).join(" · ");
          const lethalOk = r.need != null && n >= r.need;
          return (
            <div key={r.id} role="listitem" className={`combat-row divide-row${r.free ? " free" : ""}${lethalOk ? " lethal" : ""}`} {...(r.card_id ? hover(r.card_id) : {})}>
              <span className="attacker-name"><span className="divide-order" aria-hidden>{i + 1}</span>{r.label}
                {facts && <span className="combat-stat">{facts}</span>}</span>
              <span className="divide-step">
                <button className="tt-btn" aria-label={`One less to ${r.label}`} disabled={n <= least} onClick={() => set(i, n - 1)}>−</button>
                <input type="number" min={least} max={total} value={n} data-testid={`divide-${r.id}`} aria-label={`${noun} to ${r.label}`}
                  onFocus={(e) => e.currentTarget.select()} onChange={(e) => set(i, Number(e.target.value))} />
                <button className="tt-btn" aria-label={`One more to ${r.label}`} disabled={n >= total} onClick={() => set(i, n + 1)}>+</button>
                {r.need != null && <button className="tt-btn ghost" data-testid={`divide-lethal-${r.id}`} title={`Exactly lethal: ${fmt(r.need)}`} onClick={() => set(i, r.need!)}>Lethal</button>}
                {r.free && <button className="tt-btn ghost" data-testid={`divide-rest-${r.id}`} title="All that's left" onClick={() => set(i, total - others(i))}>Rest</button>}
              </span>
            </div>
          );
        })}
      </div>
      {short && <div className="divide-warn" role="alert">{freeRow!.label} can take damage only once every blocker has lethal damage (702.19b).</div>}
      <div className="decision-options">
        <span className={`attack-summary${ok ? "" : " off"}`} data-testid="divide-total" aria-live="polite">
          {fmt(sum)} / {fmt(total)} assigned{sum < total && !upto ? ` · ${fmt(total - sum)} left` : sum > total ? ` · ${fmt(sum - total)} too many` : ""}
        </span>
        <button className="tt-btn brass" data-testid="decision-done" disabled={!ok} onClick={submit}>
          {combat ? `Assign ${fmt(sum)}` : `Done (${fmt(sum)}/${fmt(total)})`}
        </button>
      </div>
    </div>
  );
}
