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
import { castFromZone, zoneCastables } from "./exileCastables";
import "./exile.css";
import { useHoverCard } from "./hoverCard";
import { centreOf, displayOrder, grabHandCard, handCardMenu, playFromHand } from "./Hand";
import { automationOn, castOrCount } from "./rules/intents";
import { legalClass, paying } from "./rules/RulesHud";
import { useFreshDraws } from "./drawNotices";

/**
 * Docked browser for a zone (library search, look at top N, graveyard, exile, sideboard).
 * It is not modal, so cards can be dragged straight onto the battlefield or into a hand.
 */
export function ZoneBrowser({ me }: { me: string }) {
  const browser = useGame((s) => s.browser);
  const view = useGame((s) => s.view);
  const [filter, setFilter] = useState<CardFilter>(NO_FILTER);
  const cards = useCardCache((s) => s.cards);
  // -- playtest (nov 16) -- folded to its header (the cards hidden): by hand, and on its own while I pay a cost, so the land row under it
  // stays clickable (it covered the lands while a flashback Bolt was paid for); null: as the moment says
  const [folded, setFolded] = useState<boolean | null>(null);
  const pay = useGame((s) => paying(s.view, me));

  // a search of my library takes the window over from any zone I was looking at (the Command zone, a graveyard…)
  const search = view?.searches[view.viewer] ?? null;
  const own = browser && (!search || browser.zone === search) ? browser : null; // the opened zone's title and limit
  const zoneKey = search ?? browser?.zone ?? null;
  const searching = !!search;

  const ids = useMemo(() => {
    if (!view || !zoneKey) return [];
    const z = view.zones[zoneKey];
    if (!z) return [];
    // my hand in the order I see it along the bottom (sorted, or my own arrangement); other zones newest/top first
    if (Array.isArray(z)) return zoneKey === `${view.viewer === "__spectator__" ? "" : me}:hand` ? displayOrder(z) : [...z].reverse();
    const known = z.known.map(([, id]) => id);
    return own?.limit ? z.known.filter(([i]) => i < own.limit!).map(([, id]) => id) : known;
  }, [view, zoneKey, own?.limit]);

  if (!view || !zoneKey) return null;
  const { zone, player } = splitZone(zoneKey);
  // my own hand: its cards play exactly as from the hand (drag to cast, double-click / Enter to play)
  const myHand = zone === "hand" && player === me && view.viewer !== "__spectator__";
  // the filters only where there's something to sift: never the Command zone, nor a handful of cards
  const filters = zone !== "command" && (searching || zone === "library" || myHand || ids.length > 8);
  // only what this viewer already sees of each card here (a hidden one has nothing to match: filterCardOf)
  const shown = filterCards(ids.map((id) => {
    const c = view.cards[id];
    return filterCardOf(id, c, c && !c.hidden && c.card_id ? cards[c.card_id] : undefined);
  }), filters ? filter : NO_FILTER).map((c) => c.id);
  // -- playtest (nov 16) -- the hint says what a double-click does here: cast an outlined card
  const castHere = !myHand && zoneCastables(view).some((c) => ids.includes(c.id));
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

  const fold = folded ?? pay;
  return (
    <div className={`zone-browser${fold ? " folded" : ""}`} data-testid="zone-browser" data-folded={fold ? "" : undefined}>
      <div className="zb-head">
        <b>{title}</b>
        <span className="hint">
          {zone === "library" ? `${shown.length} shown · ${libraryCount} in library` : filters && filtering(filter) ? `${shown.length} shown · ${ids.length} cards` : `${ids.length} ${ids.length === 1 ? "card" : "cards"}`}
        </span>
        {filters && <input className="zb-filter" placeholder="Filter by name, type or text…" value={filter.text} onChange={(e) => setFilter({ ...filter, text: e.target.value })} autoFocus
          aria-label="Filter by name, type or text"
          // Esc leaves the box: a view closes, a search only lets go of the box (ending a search is its own button)
          onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); if (searching) e.currentTarget.blur(); else close(); } }} />}
        <span className="spacer" />
        {fold && pay && <span className="hint zb-paying">Folded while you pay: your lands stay in reach</span>}
        <button className="btn small ghost" data-testid="zb-fold" aria-expanded={!fold} title={fold ? "Show the cards again" : "Fold the browser to this bar (the table under it stays clickable)"}
          onClick={() => setFolded(!fold)}>{fold ? "Show cards" : "Fold"}</button>
        {searching ? (
          <>
            <button className="btn small" onClick={() => close(false)}>Done (no shuffle)</button>
            <button className="btn small primary" onClick={() => close(true)}>Done &amp; shuffle</button>
          </>
        ) : (
          <button className="btn small" onClick={() => close()}>Close</button>
        )}
      </div>
      {!fold && filters && <CardFilterBar value={filter} onChange={setFilter} orderLabel={zone === "library" ? "Library order" : myHand ? "Hand order" : "Newest first"} />}
      {!fold && <>
      <div className="zb-hint hint" data-testid="zb-hint">
        {browserHint({ myHand, castHere, command: zone === "command" && player === me && ids.some((id) => commanderHere(view.cards[id] as GameCard | undefined, me)), automation: automationOn(view) })}
      </div>
      <div className={`zb-cards${myHand ? " zb-hand" : ""}`} data-testid={myHand ? "hand-browser" : undefined}>
        {shown.length === 0 && <div className="hint">Nothing to show.</div>}
        {myHand
          ? shown.map((id) => <HandBrowserCard key={id} id={id} me={me} index={ids.length ? (view.zones[zoneKey] as string[]).indexOf(id) : 0} />)
          : shown.map((id) => <BrowserCard key={id} id={id} me={me} owner={player ?? me} />)}
      </div>
      </>}
    </div>
  );
}

/** -- playtest (nov 17) -- a commander of mine in my command zone: a double-click casts it (the command pile's own gesture). */
export function commanderHere(card: GameCard | undefined, me: string): boolean {
  return !!card && !card.hidden && !!card.commander_key && card.zone === `${me}:command`;
}

/** -- playtest (nov 17) -- the browser's hint says what a double-click really does here: in my command zone it casts my commander (the
 * rules check its cost and tax with automation on; by hand it goes to the stack with the tax added), never "put into hand". */
export function browserHint(o: { myHand: boolean; castHere: boolean; command: boolean; automation: boolean }): string {
  if (o.myHand) return "Drag a card onto the table to play or cast it · double-click or Enter plays it · right-click for more";
  if (o.command) {
    return o.automation
      ? "Double-click your commander to cast it (the rules ask for its cost and tax) · drag cards to another zone · right-click for more"
      : "Double-click your commander to put it on the stack (adds commander tax) · drag cards to another zone · right-click for more";
  }
  if (o.castHere) return "Outlined cards you may cast or play now: double-click one · drag cards to another zone · double-click any other to put it into hand · right-click for more";
  return "Drag cards to the battlefield, a hand or another zone · double-click to put into hand · right-click for more";
}

/** A card of my hand in the browser: it plays exactly as from the hand (Hand.tsx: drag to cast, double-click, Enter, menu). */
const HandBrowserCard = memo(function HandBrowserCard({ id, me, index }: { id: string; me: string; index: number }) {
  const card = useCardView(id);
  const hover = useHoverCard();
  const selected = useGame((s) => s.selection.includes(id));
  const legal = useGame((s) => legalClass(s.view, id, me));
  const fresh = useFreshDraws((s) => s.ids.includes(id)); // -- draw notice -- drawn and not looked at yet
  if (!card) return null;
  return (
    <div
      className={`zb-card ${selected ? "selected" : ""} ${fresh ? "fresh-draw" : ""} ${legal}`}
      data-card-id={id}
      tabIndex={0}
      role="button"
      aria-label={card.hidden ? "Hidden card" : card.name}
      aria-pressed={selected}
      onKeyDown={(e) => {
        if (e.key === " ") {
          e.preventDefault();
          useGame.getState().select([id], e.shiftKey || e.ctrlKey || e.metaKey ? "toggle" : undefined);
        } else if (e.key === "Enter" && !card.hidden) {
          e.preventDefault();
          playFromHand(id, me, centreOf(e.currentTarget));
        }
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        grabHandCard(e, id, card, me, index);
      }}
      onDoubleClick={(e) => { if (!card.hidden) playFromHand(id, me, { clientX: e.clientX, clientY: e.clientY }); }}
      onContextMenu={(e) => handCardMenu(e, id, card, me)}
      onMouseEnter={fresh ? () => useFreshDraws.getState().seen(id) : undefined}
      onFocus={fresh ? () => useFreshDraws.getState().seen(id) : undefined}
      {...hover(id)}
    >
      <GameCardFace card={card} />
    </div>
  );
});

const BrowserCard = memo(function BrowserCard({ id, me, owner }: { id: string; me: string; owner: string }) {
  const card = useCardView(id);
  const hover = useHoverCard();
  // a card here you may cast or play now (Ian Malcolm's exile, impulse draw, flashback, Snapcaster's grant, escape, Bolas's Citadel …):
  // outlined, and double-click casts it (-- playtest nov 16 -- a flashback Bolt in the graveyard was put into the hand instead)
  const view = useGame((s) => s.view);
  const castable = useMemo(() => zoneCastables(view).find((c) => c.id === id), [view, id]);
  if (!card) return null;
  const verb = castable?.play ? "Play" : "Cast";
  return (
    <div
      className={`zb-card${castable ? " rules-playable" : ""}`}
      data-castable={castable ? "" : undefined}
      title={castable ? `${verb} it: double-click${castable.free ? " (without paying its mana cost)" : castable.alt ? " (for an alternative cost)" : ""}${castable.source ? ` · Exiled with ${castable.source}` : ""}` : undefined}
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
      onDoubleClick={(e) => {
        const now = useGame.getState().view;
        if (castable && now && castFromZone(card as GameCard, now, me, { clientX: e.clientX, clientY: e.clientY })) return;
        if (commanderHere(card as GameCard, me)) { // (as the command pile: cast it, never into the hand)
          void (automationOn(now) ? castOrCount({ type: "cast_spell", card_id: id, ask_optional: true }) : moveCards([id], "stack"));
          return;
        }
        void moveCards([id], "hand", { player: owner });
      }}
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
      {castable && <span className="zb-exiled-with" data-testid="zb-castable">{verb}{castable.source ? ` · with ${castable.source.split(",")[0]}` : ""}</span>}
    </div>
  );
});
