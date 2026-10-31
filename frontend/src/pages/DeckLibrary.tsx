import { useCallback, useEffect, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ColorPips } from "../components/ColorPips";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { createDeck, deleteDeck, duplicateDeck, listDecks } from "../services/decks";
import { ImportDialog } from "./ImportDialog";
import { BulkImportDialog } from "./BulkImportDialog";
import { useCard } from "../state/cardCache";
import type { DeckSummary } from "../types/decks";

export function DeckLibrary() {
  const [decks, setDecks] = useState<DeckSummary[] | null>(null);
  const [importing, setImporting] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const refresh = useCallback(() => listDecks().then(setDecks, toastError), []);
  useEffect(() => void refresh(), [refresh]);

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

  return (
    <div className="page decks">
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>Decks</h1>
        <span className="spacer" />
        <button className="btn" onClick={onNew}>New empty deck</button>
        <button className="btn" onClick={() => setBulkImporting(true)}>Import multiple decks</button>
        <button className="btn primary" onClick={() => setImporting(true)}>Import from Archidekt</button>
      </div>
      {decks && decks.length === 0 && (
        <div className="empty">
          <p>No decks yet.</p>
          <p className="hint">Paste an Archidekt deck URL, its text export, or a list from Moxfield, MTGGoldfish, Arena or plain text.</p>
          <button className="btn primary" onClick={() => setImporting(true)}>Import your first deck</button>
        </div>
      )}
      <div className="deck-grid">
        {decks?.map((d) => (
          <DeckTile key={d.id} deck={d} onDelete={() => onDelete(d)} onDuplicate={() => onDuplicate(d)} />
        ))}
      </div>
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

function DeckTile({ deck, onDelete, onDuplicate }: { deck: DeckSummary; onDelete: () => void; onDuplicate: () => void }) {
  const cover = useCard(deck.cover_id);
  const total = (deck.counts.main ?? 0) + (deck.counts.commander ?? 0);
  return (
    <div className="deck-tile">
      <a className="deck-cover" href={`#/decks/${deck.id}`}>
        {cover ? <CardFace card={cover} size="normal" /> : <div className="card-face card-back" />}
      </a>
      <div className="deck-info">
        <a href={`#/decks/${deck.id}`} className="deck-name">{deck.name}</a>
        <div className="deck-meta">
          <ColorPips colors={deck.color_identity} />
          <span className="deck-format">{deck.format}</span>
          <span>{total} cards</span>
        </div>
        {deck.commanders.length > 0 && deck.commanders.join(" & ") !== deck.name && <div className="deck-cmdr">{deck.commanders.join(" & ")}</div>}
        {deck.unresolved > 0 && <div className="warn small">{deck.unresolved} unresolved</div>}
        <div className="deck-actions">
          <a className="btn small primary" href={`#/play?deck=${deck.id}`}>Play</a>
          <a className="btn small" href={`#/decks/${deck.id}`}>Edit</a>
          <button className="btn small" onClick={onDuplicate}>Duplicate</button>
          <button className="btn small danger" onClick={onDelete}>Delete</button>
        </div>
      </div>
    </div>
  );
}
