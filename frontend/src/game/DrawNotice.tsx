import { useEffect, useRef, useState } from "react";
import { imageUrl } from "../services/cards";
import { perspective, settledChange, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, type GameView } from "../types/game";
import { drewLine, mergeBatch, newDraws, noticeFaces, useFreshDraws, wantsNotice, type DrawBatch } from "./drawNotices";
import { gameEnded } from "./nightEnding";
import "./drawNotice.css";

const SHOWN_MS = 4500;

/**
 * -- draw notice -- the cards I just drew, for me only, as MTG Arena shows them: they fan up above my hand for a moment with their art,
 * under "You drew Lightning Bolt, Island", then the notice goes (hover keeps it; Esc, a click or ✕ skips it). A burst of draws (a
 * trigger, Shabraz's loop) is one notice with a count. Built from my own view only (drawNotices.ts): nothing here reaches anyone else,
 * and opponents' draws never show (their hands aren't in my view). Settings: Show what I draw (all / effects only / off).
 */
export function DrawNotice() {
  const [batch, setBatch] = useState<DrawBatch | null>(null);
  const [held, setHeld] = useState(false);
  const live = useRef<DrawBatch | null>(null);
  live.current = batch;
  useEffect(() => {
    let n = 0;
    return useGame.subscribe((s, prev) => {
      const change = settledChange(s, prev); // (-- resolving progress -- not for an interim view: against the last update before it)
      if (!change) return;
      const next = change.after;
      const fresh = useFreshDraws.getState();
      if (fresh.ids.length && next.turn.number !== fresh.turn) fresh.clear(); // the turn moved on
      if (next.viewer === "__spectator__" || s.actingAs !== prev.actingAs) return;
      const me = perspective(next, s.actingAs);
      if (change.before && perspective(change.before, prev.actingAs) !== me) return;
      // -- playtest (nov 16) -- the game ended (decked out drawing): the ending speaks now, not the notice over it
      if (gameEnded(next, me)) { live.current = null; setBatch(null); return; }
      const ev = newDraws(change.before, next, me);
      if (!ev || !wantsNotice(usePrefs.getState().drawNotice, ev)) return;
      useFreshDraws.getState().add(ev.ids, next.turn.number);
      const merged = mergeBatch(live.current, ev.ids, ++n);
      live.current = merged;
      setBatch(merged);
    });
  }, []);
  useEffect(() => {
    if (!batch || held) return;
    const t = window.setTimeout(() => setBatch(null), SHOWN_MS * Math.max(1, Math.min(2, batch.ids.length / 4)));
    return () => window.clearTimeout(t);
  }, [batch, held]);
  useEffect(() => {
    if (!batch) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setBatch(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [batch]);
  const view = useGame((s) => s.view);
  if (!batch || !view) return null;
  const { faces, more } = noticeFaces(batch);
  const names = batch.ids.map((id) => nameOf(view, id)).filter((x): x is string => !!x);
  return (
    <aside className="draw-notice" role="status" aria-live="polite" data-testid="draw-notice"
      onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)} onClick={() => setBatch(null)}>
      <div className="draw-cards" aria-hidden>
        {faces.map((id, i) => <DrawnCard key={id} view={view} id={id} i={i} n={faces.length} />)}
        {more > 0 && <span className="draw-more">+{more}</span>}
      </div>
      <p className="draw-line">
        <span className="draw-count">{batch.ids.length > 1 ? `+${batch.ids.length} cards` : "+1 card"}</span>
        <span>You drew <b>{drewLine(names, batch.ids.length)}</b></span>
        <button className="draw-close" aria-label="Close" onClick={(e) => { e.stopPropagation(); setBatch(null); }}>✕</button>
      </p>
    </aside>
  );
}

function nameOf(view: GameView, id: string): string | null {
  const c = view.cards[id];
  return isVisible(c) ? c.name : null;
}

function DrawnCard({ view, id, i, n }: { view: GameView; id: string; i: number; n: number }) {
  const c = view.cards[id];
  const name = isVisible(c) ? c.name : "A card";
  const cardId = isVisible(c) ? c.card_id : null;
  const fan = i - (n - 1) / 2;
  return (
    <figure className="draw-card" title={name} style={{ ["--i" as string]: i, ["--fan" as string]: fan }}>
      {cardId ? <img src={imageUrl(cardId, 0, "normal")} alt={name} /> : <span className="draw-plain">{name}</span>}
    </figure>
  );
}
