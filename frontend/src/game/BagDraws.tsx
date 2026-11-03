import { useEffect, useRef, useState } from "react";
import { useGame } from "../state/gameStore";
import type { LogEntryView } from "../types/game";
import "./tabletoys.css";

/**
 * -- table toys -- a chit drawn from the draw bag, on both tables: it pops out of the bag at the top of the table by the
 * drawer's name, with its word (or a blank chit for a hidden draw, which only its drawer sees the word of), and goes after
 * a few seconds or a click. Read from the log as the dice are (draws already in the log when the table opens aren't
 * shown again); the chit is in this viewer's log line only when they may see it (app/game/views.py).
 */
const SHOWN_MS = 5000;
const MAX = 3;

interface Shown { key: string; player: string; chit: string | null; hidden: boolean; out: boolean }

const keyOf = (e: LogEntryView) => `${e.seq}:${e.ts}`;

export function BagDraws() {
  const [chits, setChits] = useState<Shown[]>([]);
  const timers = useRef<number[]>([]);
  const players = useGame((s) => s.view?.players);
  const viewer = useGame((s) => s.view?.viewer);
  useEffect(() => {
    const seen = new Set((useGame.getState().view?.log ?? []).filter((e) => e.bag).map(keyOf));
    const unsub = useGame.subscribe((s, prev) => {
      const log = s.view?.log;
      if (!log || log === prev.view?.log) return;
      for (const e of log) {
        if (!e.bag || seen.has(keyOf(e))) continue;
        seen.add(keyOf(e));
        const shown: Shown = { key: keyOf(e), player: e.bag.player, chit: e.bag.chit, hidden: e.bag.hidden, out: false };
        setChits((all) => [...all, shown].slice(-MAX));
        timers.current.push(window.setTimeout(() => dismiss(shown.key), SHOWN_MS));
      }
    });
    return () => {
      unsub();
      timers.current.forEach((t) => window.clearTimeout(t));
    };
  }, []);
  const dismiss = (key: string) => {
    setChits((all) => all.map((c) => (c.key === key ? { ...c, out: true } : c)));
    timers.current.push(window.setTimeout(() => setChits((all) => all.filter((c) => c.key !== key)), 280));
  };
  if (!chits.length) return null;
  return (
    <div className="bag-draws" aria-live="polite" data-testid="bag-draws">
      {chits.map((c) => {
        const who = players?.find((p) => p.id === c.player);
        const mine = c.player === viewer;
        const label = c.chit ? `${mine ? "You" : who?.name ?? ""} drew “${c.chit}”${c.hidden ? " (only you see it)" : ""}` : `${who?.name ?? ""} drew a hidden chit`;
        return (
          <button key={c.key} type="button" className={`bag-chit${c.out ? " out" : ""}`} style={{ ["--seat" as string]: who?.color }}
            onClick={() => dismiss(c.key)} title="From the draw bag (click to dismiss)" aria-label={label} data-testid="bag-chit">
            <span className={`token${c.chit ? "" : " hidden"}`} aria-hidden>{c.chit ?? "?"}</span>
            <span className="who">{mine ? "You drew" : `${who?.name ?? ""} drew`}</span>
            <span className="what">{c.chit ? c.chit : "a hidden chit"}</span>
            {c.hidden && c.chit && <span className="who">(only you)</span>}
          </button>
        );
      })}
    </div>
  );
}
