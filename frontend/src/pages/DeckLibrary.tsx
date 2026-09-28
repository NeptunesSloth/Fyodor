import { useCallback, useEffect, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ColorPips } from "../components/ColorPips";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { createDeck, deleteDeck, duplicateDeck, listDecks, parseDeck } from "../services/decks";
import { useCard } from "../state/cardCache";
import type { DeckFormat, DeckSummary, ParsePreview } from "../types/decks";

export function DeckLibrary() {
  const [decks, setDecks] = useState<DeckSummary[] | null>(null);
  const [importing, setImporting] = useState(false);
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
        <button className="btn primary" onClick={() => setImporting(true)}>Import deck</button>
      </div>
      {decks && decks.length === 0 && (
        <div className="empty">
          <p>No decks yet.</p>
          <p className="hint">Paste a list from Moxfield, Archidekt, MTGGoldfish, Arena or plain text.</p>
          <button className="btn primary" onClick={() => setImporting(true)}>Import your first deck</button>
        </div>
      )}
      <div className="deck-grid">
        {decks?.map((d) => (
          <DeckTile key={d.id} deck={d} onDelete={() => onDelete(d)} onDuplicate={() => onDuplicate(d)} />
        ))}
      </div>
      {importing && (
        <ImportDialog
          onClose={() => setImporting(false)}
          onCreated={(id) => {
            setImporting(false);
            navigate(`/decks/${id}`);
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
          <span>{deck.format}</span>
          <span>{total} cards</span>
        </div>
        {deck.commanders.length > 0 && <div className="deck-cmdr">{deck.commanders.join(" & ")}</div>}
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

export function ImportDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [format, setFormat] = useState<DeckFormat>("commander");
  const [preview, setPreview] = useState<ParsePreview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!text.trim()) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => parseDeck(text).then(setPreview, () => setPreview(null)), 350);
    return () => clearTimeout(t);
  }, [text]);

  const count = (s: string) => preview?.entries.filter((e) => e.section === s).reduce((n, e) => n + e.quantity, 0) ?? 0;

  const submit = async () => {
    setBusy(true);
    try {
      const deck = await createDeck({ text, name: name.trim() || preview?.name || undefined, format });
      const bad = deck.import_report?.unresolved.length ?? 0;
      toast(bad ? `Imported with ${bad} unresolved card(s) — fix them in the editor` : `Imported ${deck.name}`, bad ? "warn" : "info");
      onCreated(deck.id);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Import deck"
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!text.trim() || busy} onClick={submit}>
            {busy ? "Importing…" : "Import"}
          </button>
        </>
      }
    >
      <div className="import-grid">
        <div className="import-left">
          <div className="row">
            <label className="field grow">
              Name
              <input value={name} placeholder={preview?.name ?? "Deck name"} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </label>
            <label className="field">
              Format
              <select value={format} onChange={(e) => setFormat(e.target.value as DeckFormat)}>
                <option value="commander">Commander</option>
                <option value="constructed">60-card constructed</option>
                <option value="sandbox">Sandbox</option>
              </select>
            </label>
          </div>
          <textarea
            className="deck-text"
            autoFocus
            spellCheck={false}
            placeholder={"Commander\n1 Krenko, Mob Boss\n\nDeck\n1 Sol Ring (CMM) 410\n1x Arcane Signet\n30 Mountain"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="import-right">
          <h4>Preview</h4>
          {!preview && <p className="hint">Paste a decklist to see how it will be read.</p>}
          {preview && (
            <>
              <p>
                {count("commander") > 0 && <>Commander {count("commander")} · </>}
                Deck {count("main")}
                {count("sideboard") > 0 && <> · Sideboard {count("sideboard")}</>}
                {count("maybeboard") > 0 && <> · Maybe {count("maybeboard")}</>}
              </p>
              {preview.notes.map((n) => <p key={n} className="hint">{n}</p>)}
              {preview.unresolved.length > 0 && (
                <div className="unresolved">
                  <b className="warn">Not found ({preview.unresolved.length})</b>
                  {preview.unresolved.map((u) => (
                    <div key={u.name}>
                      {u.name}
                      {u.suggestions.length > 0 && <span className="hint"> — did you mean {u.suggestions.slice(0, 3).join(", ")}?</span>}
                    </div>
                  ))}
                </div>
              )}
              {preview.errors.map((e) => <div key={e} className="error small">{e}</div>)}
              <ul className="preview-list">
                {preview.entries.slice(0, 200).map((e, i) => (
                  <li key={i} className={e.printing_id ? "" : "warn"}>
                    <span className="qty">{e.quantity}</span> {e.name}
                    <span className="hint"> {e.section !== "main" ? `· ${e.section}` : ""} {e.set_code ? `(${e.set_code.toUpperCase()})` : ""}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
