import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { bagAnchor, CHIT_H, CHIT_W, clearOf, type Box, type Rect } from "./bagAnchor";
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
      if (!log || log === prev.view?.log || s.interim) return; // (-- resolving progress -- an interim view's lines count with the action's own update)
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
  // each drawer's chits stack by their own plaque (the dice lines keep the mats' edges; nothing shares the top centre)
  const drawers = [...new Set(chits.map((c) => c.player))];
  const [places, setPlaces] = useState<Record<string, Box | null>>({});
  const counts = drawers.map((pid) => chits.filter((c) => c.player === pid).length).join();
  useLayoutEffect(() => {
    if (!drawers.length) return;
    const place = () => {
      // under (or beside) the drawer's plaque, then down past any dice result line or other drawer's chits in the way
      // (a line shows once its dice are at rest, and stays put; each die's number chip sits just over the die itself)
      const taken: Rect[] = [...document.querySelectorAll(".dice-line.on")].map((e) => e.getBoundingClientRect());
      for (const e of document.querySelectorAll(".dice-chip.on")) {
        const r = e.getBoundingClientRect();
        taken.push({ left: r.left - 24, right: r.right + 24, top: r.top, bottom: r.bottom + 56 });
      }
      const next: Record<string, Box | null> = {};
      for (const pid of drawers) {
        const plate = document.querySelector(`.t3d-seat[data-player-id="${CSS.escape(pid)}"]`);
        if (!plate) { next[pid] = null; continue; }
        const height = chits.filter((c) => c.player === pid).length * CHIT_H;
        const at = clearOf(bagAnchor(plate.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight }), CHIT_W, height, taken);
        next[pid] = at;
        taken.push({ left: at.left, top: at.top, right: at.left + CHIT_W, bottom: at.top + height });
      }
      setPlaces((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
    };
    place();
    const tick = window.setInterval(place, 400); // a dice line that comes to rest after the chit appeared moves it aside (chits last 5 s)
    window.addEventListener("resize", place);
    return () => { window.clearInterval(tick); window.removeEventListener("resize", place); };
  }, [drawers.join(), counts]);
  if (!chits.length) return null;
  return <>{drawers.map((pid) => {
    const at = places[pid];
    return (
    <div key={pid} className={`bag-draws${at ? " by-plaque" : ""}`} aria-live="polite" data-testid="bag-draws" data-player={pid}
      style={at ? { left: at.left, top: at.top } : undefined}>
      {chits.filter((c) => c.player === pid).map((c) => {
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
  })}</>;
}
