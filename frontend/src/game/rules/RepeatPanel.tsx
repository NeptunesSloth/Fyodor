/**
 * REPEAT (AUTOMATION_UX.md "Repeat a combo"): after doing a loop once by hand, do it again ×N or until a target. The server replays the
 * player's own actions, and the answers they gave to the questions in between, iteration by iteration through the rules engine; it stops
 * at the first iteration that is illegal, random or asks something new, and leaves the table after the last whole one (one undo).
 * The list is the player's own actions this turn in words (``rules.repeatable``, nobody else's).
 */
import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Modal } from "../../components/Modal";
import type { GameView } from "../../types/game";
import { send } from "./intents";
import "./repeat.css";

export const REPEAT_TIMES = [1, 5, 10, 100, 500] as const;
export const MAX_REPEAT = 500;
export type UntilKind = "none" | "mana" | "tokens" | "life_at_most" | "life_at_least";
export interface Until { kind: UntilKind; value: number; player?: string }

const isChoice = (label: string) => label.startsWith("Choose:");

/**
 * Where the loop most likely starts. If the newest actions are the same block done twice, that block; otherwise the newest action
 * that isn't an answer or a pass (a loop starts with an action: a choice belongs to the action before it).
 */
export function defaultStart(labels: string[]): number {
  const n = labels.length;
  for (let len = Math.floor(n / 2); len >= 1; len--) {
    const a = labels.slice(n - len), b = labels.slice(n - 2 * len, n - len);
    if (a.every((x, i) => x === b[i]) && !isChoice(a[0]!)) return n - len;
  }
  for (let i = n - 1; i >= 0; i--) if (!isChoice(labels[i]!) && labels[i] !== "Pass priority") return i;
  return Math.max(0, n - 1);
}

/** The repeat_sequence intent for the actions from ``start`` to the newest. */
export function repeatAction(total: number, start: number, times: number, until: Until): Record<string, unknown> {
  const count = Math.max(1, total - start);
  const t = Math.min(MAX_REPEAT, Math.max(1, Math.round(times) || 1));
  return {
    type: "repeat_sequence", count, times: t,
    ...(until.kind !== "none" ? { until: { kind: until.kind, value: Math.round(until.value) || 0, ...(until.player ? { player: until.player } : {}) } } : {}),
  };
}

export function RepeatButton({ view, me, disabled }: { view: GameView; me: string; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const labels = view.rules?.repeatable ?? [];
  if (!labels.some((l) => !isChoice(l))) return null;
  return (
    <>
      <button className="tt-btn ghost" data-testid="open-repeat" disabled={disabled} onClick={() => setOpen(true)}
        title="Repeat what you just did (a combo or a loop) ×N, or until a target. The rules check every repeat.">
        Repeat…
      </button>
      {/* over the page, not inside the turn dial (its plaque clips and traps a fixed overlay) */}
      {open && createPortal(<RepeatPanel view={view} me={me} labels={labels} onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

export function RepeatPanel({ view, me, labels, onClose }: { view: GameView; me: string; labels: string[]; onClose: () => void }) {
  const [start, setStart] = useState(() => defaultStart(labels));
  const [times, setTimes] = useState(10);
  const [until, setUntil] = useState<Until>({ kind: "none", value: 10 });
  const [busy, setBusy] = useState(false);
  const opponents = useMemo(() => view.players.filter((p) => p.id !== me), [view.players, me]);
  const loop = labels.slice(start);
  const go = async () => {
    setBusy(true);
    const player = until.kind === "life_at_most" ? until.player ?? opponents[0]?.id : undefined;
    const ok = await send(repeatAction(labels.length, start, until.kind === "none" ? times : MAX_REPEAT, { ...until, player }) as never);
    setBusy(false);
    if (ok) onClose();
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !busy && (e.target as HTMLElement).tagName !== "SELECT") {
      e.preventDefault();
      void go();
    }
  };
  // -- resolving progress -- while the repeats are worked out the dialog steps aside, so the table shows them as they go (the turn
  // dial's Resolving plaque counts them); it comes back with its choices only if the server refused the repeat
  if (busy) return null;
  return (
    <Modal title="Repeat" onClose={onClose} footer={
      <>
        <span className="hint">One undo puts the whole repeat back.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={onClose}>Cancel</button>
        <button className="tt-btn brass" data-testid="repeat-go" disabled={busy || !loop.length} onClick={() => void go()}>
          {until.kind === "none" ? `Repeat ×${Math.min(MAX_REPEAT, Math.max(1, times))}` : "Repeat until"}
        </button>
      </>
    }>
      <div className="repeat-panel" onKeyDown={onKey}>
        <p className="hint">Pick where the loop starts. Each repeat does {loop.length === 1 ? "this action" : `these ${loop.length} actions`} again, with
          the same answers, and stops on its own if something is no longer legal, is random or asks something new.</p>
        <ol className="repeat-steps" data-testid="repeat-steps" aria-label="Your actions this turn, newest last">
          {labels.map((label, i) => {
            const choice = isChoice(label);
            return (
              <li key={i} className={`${i >= start ? "in" : ""}${i === start ? " first" : ""}${choice ? " choice" : ""}`}>
                <button type="button" disabled={choice} aria-pressed={i === start}
                  title={choice ? "An answer belongs to the action before it" : "Start the loop here"} onClick={() => setStart(i)}>
                  <span className="repeat-mark" aria-hidden>{i === start ? "▶" : i > start ? "│" : ""}</span>
                  {label}
                </button>
              </li>
            );
          })}
        </ol>
        <div className="repeat-row" role="group" aria-label="How many times">
          <span className="repeat-label">Times</span>
          {REPEAT_TIMES.map((n) => (
            <button key={n} type="button" className={`tt-btn ${times === n && until.kind === "none" ? "brass" : "ghost"}`} aria-pressed={times === n}
              data-testid={`repeat-times-${n}`} onClick={() => { setTimes(n); setUntil((u) => ({ ...u, kind: "none" })); }}>×{n}</button>
          ))}
          <input type="number" min={1} max={MAX_REPEAT} value={times} aria-label="Times" className="repeat-num"
            onChange={(e) => setTimes(Number(e.target.value))} />
        </div>
        <div className="repeat-row" role="group" aria-label="Or until">
          <span className="repeat-label">Or until</span>
          <select value={until.kind} aria-label="Stop condition" data-testid="repeat-until"
            onChange={(e) => setUntil((u) => ({ ...u, kind: e.target.value as UntilKind }))}>
            <option value="none">no target (just the times)</option>
            <option value="mana">I have this much mana</option>
            <option value="tokens">I have this many tokens</option>
            <option value="life_at_most">a player is at this life or less</option>
            <option value="life_at_least">I'm at this life or more</option>
          </select>
          {until.kind !== "none" && (
            <input type="number" value={until.value} aria-label="Target" className="repeat-num" data-testid="repeat-target"
              onChange={(e) => setUntil((u) => ({ ...u, value: Number(e.target.value) }))} />
          )}
          {until.kind === "life_at_most" && (
            <select value={until.player ?? opponents[0]?.id ?? ""} aria-label="Player" onChange={(e) => setUntil((u) => ({ ...u, player: e.target.value }))}>
              {view.players.map((p) => <option key={p.id} value={p.id}>{p.id === me ? "me" : p.name}</option>)}
            </select>
          )}
        </div>
        {until.kind !== "none" && <p className="hint">Up to {MAX_REPEAT} times, stopping as soon as the target is reached.</p>}
      </div>
    </Modal>
  );
}
