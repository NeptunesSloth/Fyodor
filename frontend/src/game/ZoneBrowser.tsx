import { memo, useMemo, useState } from "react";
import { openMenu } from "../components/ContextMenu";
import { useCardCache } from "../state/cardCache";
import { playerName, useCardView, useGame } from "../state/gameStore";
import { isVisible, splitZone, type GameCard } from "../types/game";
import { moveCards, send } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag } from "./dnd";
import { GameCardFace } from "./GameCardFace";
import { exileCastables, playFromExile } from "./exileCastables";
import "./exile.css";

/**
 * Docked browser for a zone (library search, look at top N, graveyard, exile, sideboard).
 * It is not modal, so cards can be dragged straight onto the battlefield or into a hand.
 */
export function ZoneBrowser({ me }: { me: string }) {
  const browser = useGame((s) => s.browser);
  const view = useGame((s) => s.view);
  const [filter, setFilter] = useState("");
  const cards = useCardCache((s) => s.cards);

  const zoneKey = browser?.zone ?? view?.searches[view.viewer] ?? null;
  const searching = !!view && !!zoneKey && view.searches[view.viewer] === zoneKey;

  const ids = useMemo(() => {
    if (!view || !zoneKey) return [];
    const z = view.zones[zoneKey];
    if (!z) return [];
    if (Array.isArray(z)) return [...z].reverse(); // newest/top first
    const known = z.known.map(([, id]) => id);
    return browser?.limit ? z.known.filter(([i]) => i < browser.limit!).map(([, id]) => id) : known;
  }, [view, zoneKey, browser?.limit]);

  if (!view || !zoneKey) return null;
  const { zone, player } = splitZone(zoneKey);
  const q = filter.trim().toLowerCase();
  const shown = ids.filter((id) => {
    if (!q) return true;
    const c = view.cards[id];
    if (!c || !isVisible(c)) return false;
    const data = c.card_id ? cards[c.card_id] : undefined;
    return c.name.toLowerCase().includes(q) || (data?.type_line ?? "").toLowerCase().includes(q) || (data?.oracle_text ?? "").toLowerCase().includes(q);
  });
  const libraryCount = !Array.isArray(view.zones[zoneKey]) ? (view.zones[zoneKey] as { count: number }).count : ids.length;
  const title =
    browser?.title ??
    (searching ? `Searching ${player === me ? "your" : `${playerName(view, player)}'s`} ${zone}` : `${playerName(view, player)}'s ${zone}`);

  const close = (shuffle?: boolean) => {
    if (searching) void send({ type: "search_end", shuffle: !!shuffle });
    // Closing a "look at the top N" view hides those cards again (nothing is remembered).
    else if (view.my_views?.some((v) => v.kind === "look" && v.zone === zoneKey)) void send({ type: "end_view" });
    useGame.getState().openBrowser(null);
    setFilter("");
  };

  return (
    <div className="zone-browser">
      <div className="zb-head">
        <b>{title}</b>
        <span className="hint">
          {zone === "library" ? `${shown.length} shown · ${libraryCount} in library` : `${ids.length} cards`}
        </span>
        <input className="zb-filter" placeholder="Filter by name, type or text…" value={filter} onChange={(e) => setFilter(e.target.value)} autoFocus />
        <span className="spacer" />
        {searching ? (
          <>
            <button className="btn small" onClick={() => close(false)}>Done (no shuffle)</button>
            <button className="btn small primary" onClick={() => close(true)}>Done &amp; shuffle</button>
          </>
        ) : (
          <button className="btn small" onClick={() => close()}>Close</button>
        )}
      </div>
      <div className="zb-hint hint">Drag cards to the battlefield, a hand or another zone · double-click to put into hand · right-click for more</div>
      <div className="zb-cards">
        {shown.length === 0 && <div className="hint">Nothing to show.</div>}
        {shown.map((id) => (
          <BrowserCard key={id} id={id} me={me} owner={player ?? me} />
        ))}
      </div>
    </div>
  );
}

const BrowserCard = memo(function BrowserCard({ id, me, owner }: { id: string; me: string; owner: string }) {
  const card = useCardView(id);
  // a card here you may cast or play now (Ian Malcolm's exile, impulse draw …): outlined, and double-click casts it
  const view = useGame((s) => s.view);
  const castable = useMemo(() => exileCastables(view).find((c) => c.id === id), [view, id]);
  if (!card) return null;
  return (
    <div
      className={`zb-card${castable ? " rules-playable" : ""}`}
      title={castable ? `${castable.play ? "Play" : "Cast"} it: double-click${castable.source ? ` · Exiled with ${castable.source}` : ""}` : undefined}
      data-card-id={id}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        beginPointerDrag(e, {
          ids: [id],
          from: card.zone,
          onDrop: (t) => {
            if (!t) return;
            const { zone, player } = splitZone(t.zone);
            void moveCards([id], zone, { player, x: t.x, y: t.y, position: t.position, index: t.index });
          },
        });
      }}
      onDoubleClick={() => void (castable ? playFromExile(castable) : moveCards([id], "hand", { player: owner }))}
      onContextMenu={(e) => {
        e.preventDefault();
        const view = useGame.getState().view;
        if (!view) return;
        useGame.getState().select([id]);
        const { title, items } = cardMenu(card as GameCard, view, me);
        openMenu(e, items, title);
      }}
      onPointerEnter={() => useGame.getState().setHover(id)}
      onPointerLeave={() => useGame.getState().setHover(null)}
    >
      <GameCardFace card={card} peek />
      {castable && <span className="zb-exiled-with" data-testid="zb-castable">{castable.play ? "Play" : "Cast"}{castable.source ? ` · with ${castable.source.split(",")[0]}` : ""}</span>}
    </div>
  );
});
