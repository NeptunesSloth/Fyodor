import { memo, useMemo, useState } from "react";
import { openMenu } from "../components/ContextMenu";
import { useCardCache } from "../state/cardCache";
import { playerName, useCardView, useGame } from "../state/gameStore";
import { splitZone, type GameCard } from "../types/game";
import { moveCards, send } from "./actions";
import { CardFilterBar, filterCardOf } from "./CardFilterBar";
import { NO_FILTER, filterCards, filtering, type CardFilter } from "./cardFilters";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag } from "./dnd";
import { GameCardFace } from "./GameCardFace";
import { exileCastables, playFromExile } from "./exileCastables";
import "./exile.css";
import { useHoverCard } from "./hoverCard";

/**
 * Docked browser for a zone (library search, look at top N, graveyard, exile, sideboard).
 * It is not modal, so cards can be dragged straight onto the battlefield or into a hand.
 */
export function ZoneBrowser({ me }: { me: string }) {
  const browser = useGame((s) => s.browser);
  const view = useGame((s) => s.view);
  const [filter, setFilter] = useState<CardFilter>(NO_FILTER);
  const cards = useCardCache((s) => s.cards);

  // a search of my library takes the window over from any zone I was looking at (the Command zone, a graveyard…)
  const search = view?.searches[view.viewer] ?? null;
  const own = browser && (!search || browser.zone === search) ? browser : null; // the opened zone's title and limit
  const zoneKey = search ?? browser?.zone ?? null;
  const searching = !!search;

  const ids = useMemo(() => {
    if (!view || !zoneKey) return [];
    const z = view.zones[zoneKey];
    if (!z) return [];
    if (Array.isArray(z)) return [...z].reverse(); // newest/top first
    const known = z.known.map(([, id]) => id);
    return own?.limit ? z.known.filter(([i]) => i < own.limit!).map(([, id]) => id) : known;
  }, [view, zoneKey, own?.limit]);

  if (!view || !zoneKey) return null;
  const { zone, player } = splitZone(zoneKey);
  // the filters only where there's something to sift: never the Command zone, nor a handful of cards
  const filters = zone !== "command" && (searching || zone === "library" || ids.length > 8);
  // only what this viewer already sees of each card here (a hidden one has nothing to match: filterCardOf)
  const shown = filterCards(ids.map((id) => {
    const c = view.cards[id];
    return filterCardOf(id, c, c && !c.hidden && c.card_id ? cards[c.card_id] : undefined);
  }), filters ? filter : NO_FILTER).map((c) => c.id);
  const libraryCount = !Array.isArray(view.zones[zoneKey]) ? (view.zones[zoneKey] as { count: number }).count : ids.length;
  const title =
    own?.title ??
    (searching ? `Searching ${player === me ? "your" : `${playerName(view, player)}'s`} ${zone}` : `${playerName(view, player)}'s ${zone}`);

  const close = (shuffle?: boolean) => {
    if (searching) void send({ type: "search_end", shuffle: !!shuffle });
    // Closing a "look at the top N" view hides those cards again (nothing is remembered).
    else if (view.my_views?.some((v) => v.kind === "look" && v.zone === zoneKey)) void send({ type: "end_view" });
    useGame.getState().openBrowser(null);
    setFilter(NO_FILTER);
  };

  return (
    <div className="zone-browser">
      <div className="zb-head">
        <b>{title}</b>
        <span className="hint">
          {zone === "library" ? `${shown.length} shown · ${libraryCount} in library` : filters && filtering(filter) ? `${shown.length} shown · ${ids.length} cards` : `${ids.length} ${ids.length === 1 ? "card" : "cards"}`}
        </span>
        {filters && <input className="zb-filter" placeholder="Filter by name, type or text…" value={filter.text} onChange={(e) => setFilter({ ...filter, text: e.target.value })} autoFocus />}
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
      {filters && <CardFilterBar value={filter} onChange={setFilter} orderLabel={zone === "library" ? "Library order" : "Newest first"} />}
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
  const hover = useHoverCard();
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
      {...hover(id)}
    >
      <GameCardFace card={card} peek />
      {castable && <span className="zb-exiled-with" data-testid="zb-castable">{castable.play ? "Play" : "Cast"}{castable.source ? ` · with ${castable.source.split(",")[0]}` : ""}</span>}
    </div>
  );
});
