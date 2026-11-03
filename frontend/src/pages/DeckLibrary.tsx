import { useCallback, useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { createDeck, deleteDeck, duplicateDeck, listDecks } from "../services/decks";
import { podResults } from "../services/pod";
import type { DeckSummary } from "../types/decks";
import type { LobbySeat } from "../types/game";
import { BulkImportDialog } from "./BulkImportDialog";
import { useCommanderPrinting } from "./CommanderArt";
import { deckMatches, deckRecords, playedWhen, recordText, type DeckRecord } from "./deckBits";
import { DeckArt, DeckMenu } from "./DeckParts";
import { ImportDialog } from "./ImportDialog";
import "./decks.css";

const NO_SEATS: LobbySeat[] = [];

/**
 * The deck library as a shelf: each deck stands on a steel plinth under its commander's art (both partners side by side),
 * with its colours, size and how it has done in the pod's recorded games. Play is the one loud action; Edit is quiet; Duplicate
 * and Delete wait behind the deck's menu.
 */
export function DeckLibrary() {
  const [decks, setDecks] = useState<DeckSummary[] | null>(null);
  const [records, setRecords] = useState<Map<string, DeckRecord>>(() => new Map());
  const [importing, setImporting] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const [q, setQ] = useState("");
  const refresh = useCallback(() => listDecks().then(setDecks, toastError), []);
  useEffect(() => void refresh(), [refresh]);
  // the pod's recorded games, for each deck's record (public: Pod stats shows the same); a device that can't read them shows none
  useEffect(() => {
    let live = true;
    podResults(1000).then((r) => live && setRecords(deckRecords(r)), () => undefined);
    return () => { live = false; };
  }, []);

  const onDelete = async (d: DeckSummary) => {
    if (!window.confirm(`Delete "${d.name}"? This cannot be undone.`)) return;
    await deleteDeck(d.id).catch(toastError);
    refresh();
  };
  const onDuplicate = async (d: DeckSummary) => {
    await duplicateDeck(d.id).then(() => toast(`Duplicated ${d.name}`), toastError);
    refresh();
  };
  const onNew = async () => {
    const deck = await createDeck({ name: "New deck", text: "" }).catch(toastError);
    if (deck) navigate(`/decks/${deck.id}`);
  };
  const shown = useMemo(() => decks?.filter((d) => deckMatches(d, q)) ?? null, [decks, q]);
  const empty = decks?.length === 0;

  return (
    <div className="page dk-page">
      <header className="dk-head">
        <div className="dk-title">
          <h1>Decks</h1>
          {decks && decks.length > 0 && <p className="dk-count">{decks.length === 1 ? "One deck" : `${decks.length} decks`}</p>}
        </div>
        {decks && decks.length > 6 && (
          <input type="search" className="dk-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a deck or a commander"
            aria-label="Find a deck or a commander" />
        )}
        <div className="dk-head-acts">
          <button className="tt-btn ghost" onClick={onNew}><Icon name="plus" size={15} />New empty deck</button>
          <button className="tt-btn ghost" onClick={() => setBulkImporting(true)}><Icon name="cards" size={15} />Import multiple decks</button>
          {/* with no decks yet the empty shelf carries this button */}
          {!empty && <button className="tt-btn brass dk-import" onClick={() => setImporting(true)}><Icon name="download" size={16} />Import a deck</button>}
        </div>
      </header>

      {empty && <EmptyShelf onImport={() => setImporting(true)} />}
      {shown && shown.length > 0 && (
        <ul className="dk-grid">
          {shown.map((d) => (
            <DeckTile key={d.id} deck={d} record={records.get(d.id)} onDelete={() => void onDelete(d)} onDuplicate={() => void onDuplicate(d)} />
          ))}
        </ul>
      )}
      {q && shown?.length === 0 && <p className="dk-none">No deck or commander matches “{q.trim()}”.</p>}

      {bulkImporting && <BulkImportDialog onClose={() => setBulkImporting(false)} onSaved={() => void refresh()} />}
      {importing && (
        <ImportDialog
          onClose={() => setImporting(false)}
          onCreated={(id, jobId) => {
            setImporting(false);
            navigate(`/decks/${id}${jobId ? `?job=${jobId}` : ""}`);
          }}
        />
      )}
    </div>
  );
}

function DeckTile({ deck, record, onDelete, onDuplicate }: { deck: DeckSummary; record: DeckRecord | undefined; onDelete: () => void; onDuplicate: () => void }) {
  const [menu, setMenu] = useState(false);
  // the cover is the first commander's printing; a partner's comes from the card database
  const partner = useCommanderPrinting(deck.commanders.length > 1 ? deck.commanders[1]! : null, NO_SEATS);
  const total = (deck.counts.main ?? 0) + (deck.counts.commander ?? 0);
  const cmdrs = deck.commanders.join(" & ");
  const href = `#/decks/${deck.id}`;
  return (
    <li className={`dk-deck ${menu ? "menu-open" : ""}`}>
      <a className="dk-art-link" href={href} tabIndex={-1} aria-hidden>
        <DeckArt ids={deck.commanders.length > 1 ? [deck.cover_id, partner] : [deck.cover_id]} />
      </a>
      <div className="dk-text">
        <h2 className="dk-name"><a href={href}>{deck.name}</a></h2>
        {deck.commanders.length > 0 && cmdrs !== deck.name && <p className="dk-cmdr">{cmdrs}</p>}
        {deck.commanders.length === 0 && <p className="dk-cmdr none">No commander chosen</p>}
        <p className="dk-facts">
          <ColorPips colors={deck.color_identity} />
          <span>{total} cards</span>
          {deck.unresolved > 0 && <span className="dk-warn">{deck.unresolved} not found</span>}
        </p>
        {record && (
          <p className="dk-record">
            <span>{recordText(record)}</span>
            <span>Played {playedWhen(record.last)}</span>
          </p>
        )}
      </div>
      <div className="dk-acts">
        <a className="tt-btn dk-play" href={`#/play?deck=${deck.id}`} aria-label={`Play ${deck.name}`}><Icon name="swords" size={15} />Play</a>
        <a className="tt-btn ghost dk-edit" href={href} aria-label={`Edit ${deck.name}`}><Icon name="pen" size={14} />Edit</a>
        <DeckMenu label={`More for ${deck.name}`} open={menu} onOpenChange={setMenu} className="dk-more" items={[
          { label: "Duplicate", icon: "cards", onClick: onDuplicate },
          "separator",
          { label: "Delete…", icon: "trash", danger: true, onClick: onDelete },
        ]} />
      </div>
    </li>
  );
}

/** No decks yet: three face-down cards and the way to fill the shelf. */
function EmptyShelf({ onImport }: { onImport: () => void }) {
  return (
    <section className="dk-empty" aria-labelledby="dk-empty-title">
      <div className="dk-empty-cards" aria-hidden>
        {[0, 1, 2].map((i) => <span key={i} className="dk-empty-card" style={{ "--i": i } as React.CSSProperties}><CardFace faceDown /></span>)}
      </div>
      <div className="dk-empty-text">
        <h2 id="dk-empty-title">No decks on the shelf yet</h2>
        <p>Paste an Archidekt link or a list from Moxfield, MTGGoldfish, Arena or plain text. The deck is kept on this computer, so the pod can play it without the Internet.</p>
        <button className="tt-btn brass" onClick={onImport}><Icon name="download" size={16} />Import your first deck</button>
        <p className="dk-empty-more">Bringing a whole collection? Use <b>Import multiple decks</b> above.</p>
      </div>
    </section>
  );
}
