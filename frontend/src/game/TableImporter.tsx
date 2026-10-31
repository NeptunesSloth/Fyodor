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

/** Open the table's importer (the 3D table's importer tile and the 2D rail's button send this). */
export const openImporter = () => window.dispatchEvent(new CustomEvent("fyodor:importer"));

/**
 * The scripted tables' card importer, at the table (Oops I Baked a Pie): find any card, put a whole new deck in your
 * seat, reset your deck or restart the game, without leaving the table or going through a menu. Docked on the left
 * of the table, so the game stays in view.
 */
export function TableImporter() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("fyodor:importer", show);
    return () => window.removeEventListener("fyodor:importer", show);
  }, []);
  if (!open) return null;
  return <ImporterPanel onClose={() => setOpen(false)} />;
}

function ImporterPanel({ onClose }: { onClose: () => void }) {
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
    <aside className="table-importer frame" role="dialog" aria-label="Card importer" data-testid="table-importer">
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

/** A whole new deck in your seat: pasted, from Archidekt, from your decks (this browser) or the host's library. */
function PlaceDeck({ gameId, me, local }: { gameId: string; me: string; local: boolean }) {
  const [text, setText] = useState("");
  const [hostDecks, setHostDecks] = useState<DeckSummary[] | null>(null);
  const [pick, setPick] = useState("");
  const [draw, setDraw] = useState(true);
  const [busy, setBusy] = useState(false);
  const mine = useMemo(() => myDecks(), []);
  useEffect(() => { listDecks().then(setHostDecks, () => setHostDecks(null)); }, []);
  const place = async () => {
    const saved = mine.find((d) => `my:${d.id}` === pick);
    const body = pick.startsWith("host:") ? { deck_id: pick.slice(5) }
      : saved ? { ...saved.body }
      : /archidekt\.com\/decks\/\d+/.test(text.trim()) ? { archidekt: text.trim() } : { text };
    setBusy(true);
    try {
      const r = await loadDeckAtTable(gameId, { ...body, draw: draw ? 7 : 0, ...(local ? { seat: me } : {}) });
      toast(`${r.deck} is at your seat`);
      setText("");
      setPick("");
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const ready = !!pick || text.trim().length > 0;
  return (
    <section className="ti-section">
      <label className="field">Your decks
        <select value={pick} onChange={(e) => setPick(e.target.value)} data-testid="ti-deck-pick">
          <option value="">Paste a list below…</option>
          {mine.length > 0 && <optgroup label="Brought from this computer">{mine.map((d) => <option key={d.id} value={`my:${d.id}`}>{d.name}</option>)}</optgroup>}
          {hostDecks && hostDecks.length > 0 && <optgroup label="Deck library">{hostDecks.map((d) => <option key={d.id} value={`host:${d.id}`}>{d.name}</option>)}</optgroup>}
        </select>
      </label>
      {!pick && (
        <textarea className="ti-list" rows={7} placeholder={"Paste a deck list or an Archidekt link\n\nCommander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n…"}
          value={text} onChange={(e) => setText(e.target.value)} data-testid="ti-deck-text" />
      )}
      <label className="ti-check"><input type="checkbox" checked={draw} onChange={(e) => setDraw(e.target.checked)} /> Shuffle and draw 7</label>
      <button className="btn primary" disabled={!ready || busy} onClick={() => void place()} data-testid="ti-place-deck">{busy ? "Placing…" : "Place deck"}</button>
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
