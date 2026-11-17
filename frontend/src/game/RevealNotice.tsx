import { useEffect, useState } from "react";
import { playerName, useGame } from "../state/gameStore";
import { imageUrl } from "../services/cards";
import { freshReveals, type Reveal } from "./reveals";
import "./reveal.css";

const SHOWN_MS = 9000;
const MAX_CARDS = 14;

/**
 * -- public reveals -- 701.20a: cards a spell, an ability or a player revealed, shown to everyone at the table (spectators too) for a few
 * seconds over the board: "Alice revealed · Nissa, Resurgent Animist", the cards, and the card a "reveal … until" found. Read from the log
 * line as this viewer receives it (names and printings only), so it never shows more than the log does. Hover keeps it; Esc or ✕ closes it.
 */
export function RevealNotice() {
  const [shown, setShown] = useState<Reveal | null>(null);
  const [held, setHeld] = useState(false);
  const view = useGame((s) => s.view);
  useEffect(() => {
    const seen = new Set<string>();
    freshReveals(useGame.getState().view?.log ?? [], seen); // (what already happened when you arrived isn't news)
    return useGame.subscribe((s, prev) => {
      const log = s.view?.log;
      if (!log || log === prev.view?.log) return;
      const fresh = freshReveals(log, seen);
      if (fresh.length) setShown(fresh[fresh.length - 1]!);
    });
  }, []);
  useEffect(() => {
    if (!shown || held) return;
    const t = window.setTimeout(() => setShown(null), SHOWN_MS);
    return () => window.clearTimeout(t);
  }, [shown, held]);
  useEffect(() => {
    if (!shown) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setShown(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown]);
  if (!shown) return null;
  const listed = shown.cards.slice(0, MAX_CARDS);
  const more = shown.cards.length - listed.length + shown.hidden;
  const foundAt = shown.found ? shown.cards.length - 1 : -1;
  return (
    <aside className="reveal-notice frame" role="status" aria-live="polite" data-testid="reveal-notice"
      onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)}>
      <header className="reveal-head">
        <span><b>{playerName(view, shown.player)}</b> revealed{shown.source ? <span className="reveal-source"> · {shown.source}</span> : null}</span>
        <button className="reveal-close" aria-label="Close" onClick={() => setShown(null)}>✕</button>
      </header>
      <div className="reveal-cards">
        {listed.map((c, i) => (
          <figure key={i} className={`reveal-card ${i === foundAt ? "found" : ""}`} title={c.name}>
            {c.card_id ? <img src={imageUrl(c.card_id, 0, "small")} alt={c.name} loading="lazy" /> : <span className="reveal-plain">{c.name}</span>}
          </figure>
        ))}
        {more > 0 && <span className="reveal-more">+{more}</span>}
      </div>
      {shown.until && (
        <p className="reveal-found" data-testid="reveal-found">{shown.found ? <>Found <b>{shown.found.name}</b></> : "None found"}</p>
      )}
    </aside>
  );
}
