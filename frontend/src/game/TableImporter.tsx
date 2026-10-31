import { useEffect, useMemo, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { CardFace } from "../cards/CardFace";
import { useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { searchCards } from "../services/cards";
import { listDecks } from "../services/decks";
import { loadDeckAtTable, myDecks } from "../services/games";
import type { CardData } from "../types/cards";
import type { DeckSummary } from "../types/decks";
import { send } from "./actions";
import { useIsHost } from "./HostTools";

/** Open (or close) the importer from the top bar's button, under it. */
export const openImporter = (e?: React.MouseEvent) => {
  const r = (e?.currentTarget as HTMLElement | undefined)?.getBoundingClientRect();
  window.dispatchEvent(new CustomEvent("fyodor:importer", { detail: r ? { right: r.right, bottom: r.bottom } : null }));
};

/**
 * The scripted tables' card importer (Oops I Baked a Pie): find any card, put a saved or pasted deck in your seat,
 * reset your deck or restart the game, without leaving the table. It drops down under its button in the top bar,
 * so the game stays in view.
 */
export function TableImporter() {
  const [at, setAt] = useState<{ right: number; bottom: number } | null | false>(false);
  useEffect(() => {
    const toggle = (e: Event) => setAt((open) => (open !== false ? false : (e as CustomEvent<{ right: number; bottom: number } | null>).detail));
    window.addEventListener("fyodor:importer", toggle);
    return () => window.removeEventListener("fyodor:importer", toggle);
  }, []);
  if (at === false) return null;
  return <ImporterPanel at={at} onClose={() => setAt(false)} />;
}

function ImporterPanel({ at, onClose }: { at: { right: number; bottom: number } | null; onClose: () => void }) {
  const view = useGame((s) => s.view);
  const gameId = useGame((s) => s.gameId);
  const actingAs = useGame((s) => s.actingAs);
  const [tab, setTab] = useState<"card" | "deck">("card");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!view || !gameId) return null;
  const me = perspective(view, actingAs);
  return (
    <aside className="table-importer frame" role="dialog" aria-label="Card importer" data-testid="table-importer"
      style={at ? { top: at.bottom + 6, right: Math.max(12, window.innerWidth - at.right - 120) } : undefined}>
      <header className="ti-head">
        <b>Card importer</b>
        <div className="ti-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "card"} className={tab === "card" ? "on" : ""} onClick={() => setTab("card")}>Find a card</button>
          <button role="tab" aria-selected={tab === "deck"} className={tab === "deck" ? "on" : ""} onClick={() => setTab("deck")} data-testid="ti-tab-deck">Place a deck</button>
        </div>
        <button className="tt-btn ghost ti-close" onClick={onClose} aria-label="Close the importer">✕</button>
      </header>
      {tab === "card" ? <FindCard me={me} /> : <PlaceDeck gameId={gameId} me={me} local={view.game.mode !== "lan"} />}
      <Restart me={me} />
    </aside>
  );
}

/** Any card from the card database, into your hand or onto the battlefield (a test object, as the table allows). */
function FindCard({ me }: { me: string }) {
  const allowed = useGame((s) => !!s.view?.game.settings.allow_test_objects);
  const isHost = useIsHost();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<CardData[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return; }
    let live = true;
    const t = window.setTimeout(() => {
      searchCards(q.trim(), { limit: 24 }).then((r) => {
        if (!live) return;
        useCardCache.getState().put(r.results);
        setResults(r.results);
      }, toastError);
    }, 160);
    return () => { live = false; window.clearTimeout(t); };
  }, [q]);
  const add = (card: CardData, zone: "hand" | "battlefield") =>
    void send({ type: "spawn_card", card_id: card.id, zone, player: me }).then((ok) => ok && toast(`${card.name} → your ${zone}`));
  return (
    <section className="ti-section">
      <input className="ti-search" autoFocus placeholder="Search for Magic cards" value={q} onChange={(e) => setQ(e.target.value)} data-testid="ti-search" />
      {!allowed && (
        <p className="hint">
          Adding single cards is off at this table.{" "}
          {isHost ? <button className="linkish" onClick={() => void send({ type: "configure", allow_test_objects: true })}>Allow it</button> : "The host can allow it."}
        </p>
      )}
      <div className="ti-results">
        {results.map((c) => (
          <button key={c.id} className="ti-card" title={`${c.name}: click for your hand, Shift-click for the battlefield`} disabled={!allowed}
            onClick={(e) => add(c, e.shiftKey ? "battlefield" : "hand")} data-testid="ti-result">
            <CardFace card={c} size="small" />
          </button>
        ))}
      </div>
      {results.length > 0 && <p className="hint">Click: into your hand · Shift-click: onto the battlefield. Added cards are marked TEST.</p>}
    </section>
  );
}

/** A whole new deck in your seat: one of your saved decks (one click), or a pasted list or Archidekt link. */
function PlaceDeck({ gameId, me, local }: { gameId: string; me: string; local: boolean }) {
  const [text, setText] = useState("");
  const [hostDecks, setHostDecks] = useState<DeckSummary[] | null>(null);
  const [draw, setDraw] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const mine = useMemo(() => myDecks(), []);
  useEffect(() => { listDecks().then(setHostDecks, () => setHostDecks(null)); }, []);
  const place = async (key: string, body: Parameters<typeof loadDeckAtTable>[1]) => {
    setBusy(key);
    try {
      const r = await loadDeckAtTable(gameId, { ...body, draw: draw ? 7 : 0, ...(local ? { seat: me } : {}) });
      toast(`${r.deck} is at your seat`);
      if (key === "paste") setText("");
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(null);
    }
  };
  const saved = [
    ...(hostDecks ?? []).map((d) => ({ key: `host:${d.id}`, name: d.name, sub: d.commanders.join(" & ") || `${d.counts.main ?? 0} cards`, cover: d.cover_id, body: { deck_id: d.id } })),
    ...mine.map((d) => ({ key: `my:${d.id}`, name: d.name, sub: d.commanders.join(" & ") || "brought from this computer", cover: null as string | null, body: { ...d.body } })),
  ];
  return (
    <section className="ti-section">
      <label className="ti-check"><input type="checkbox" checked={draw} onChange={(e) => setDraw(e.target.checked)} /> Shuffle and draw 7</label>
      {saved.length > 0 && (
        <>
          <h4 className="ti-sub">Your saved decks</h4>
          <ul className="ti-decks" data-testid="ti-saved-decks">
            {saved.map((d) => (
              <li key={d.key}>
                {d.cover && <span className="ti-deck-art" style={{ backgroundImage: `url("/api/images/${d.cover}?size=normal")` }} aria-hidden />}
                <span className="ti-deck-text"><b>{d.name}</b><small>{d.sub}</small></span>
                <button className="btn" disabled={!!busy} onClick={() => void place(d.key, d.body)} data-testid="ti-place-saved">
                  {busy === d.key ? "Placing…" : "Place"}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <h4 className="ti-sub">Or paste a list</h4>
      <textarea className="ti-list" rows={5} placeholder={"A deck list or an Archidekt link\n\nCommander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n…"}
        value={text} onChange={(e) => setText(e.target.value)} data-testid="ti-deck-text" />
      <button className="btn primary" disabled={!text.trim() || !!busy} data-testid="ti-place-deck"
        onClick={() => void place("paste", /archidekt\.com\/decks\/\d+/.test(text.trim()) ? { archidekt: text.trim() } : { text })}>
        {busy === "paste" ? "Placing…" : "Place this deck"}
      </button>
      <p className="hint">Your current cards leave the table; your life goes back to the start. Undo brings the old deck back.</p>
    </section>
  );
}

/** Reset your deck, or restart the whole game, from the table (each asks twice). */
function Restart({ me }: { me: string }) {
  const isHost = useIsHost();
  const [armed, setArmed] = useState<"reset" | "restart" | null>(null);
  useEffect(() => {
    if (!armed) return;
    const t = window.setTimeout(() => setArmed(null), 4000);
    return () => window.clearTimeout(t);
  }, [armed]);
  return (
    <footer className="ti-restart">
      <button className={`btn ${armed === "reset" ? "danger" : ""}`} data-testid="ti-reset"
        onClick={() => { if (armed !== "reset") return setArmed("reset"); setArmed(null); void send({ type: "reset_deck", player: me, draw: 7 }); }}>
        {armed === "reset" ? "Click again: reset my deck" : "Reset my deck"}
      </button>
      {isHost && (
        <button className={`btn ${armed === "restart" ? "danger" : ""}`} data-testid="ti-restart"
          onClick={() => { if (armed !== "restart") return setArmed("restart"); setArmed(null); void send({ type: "restart_game", draw: 7 }); }}>
          {armed === "restart" ? "Click again: restart for everyone" : "Restart game"}
        </button>
      )}
    </footer>
  );
}
