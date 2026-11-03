import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { importOptions, previewImport } from "../services/decks";
import { saveDeckForOffline } from "../services/offlineDecks";
import type { ImportRequest, ParsePreview } from "../types/decks";

interface Item {
  label: string;
  request: ImportRequest;
  preview?: ParsePreview;
  error?: string;
  state: "ready" | "saving" | "saved" | "failed";
  deckId?: string;
  artwork?: string;
}

export function BulkImportDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [online, setOnline] = useState(false);
  const [urls, setUrls] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [download, setDownload] = useState(true);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { importOptions().then(o => setOnline(o.archidekt_url), () => undefined); }, []);
  const close = () => { if (!busy) onClose(); };
  const invalidate = () => { setItems([]); setFinished(false); setError(""); };
  const patch = (index: number, values: Partial<Item>) => setItems(old => old.map((item, i) => i === index ? { ...item, ...values } : item));

  const preview = async () => {
    setBusy(true);
    setError("");
    setItems([]);
    const results: Item[] = [];
    try {
      const inputs: { label: string; file?: File; url?: string }[] = [
        ...files.map(file => ({ label: file.name, file })),
        ...Array.from(new Set(urls.split(/\r?\n/).map(url => url.trim()).filter(Boolean))).map(url => ({ label: url, url })),
      ];
      for (const input of inputs) {
        let request: ImportRequest = {};
        try {
          if (input.file) {
            if (input.file.size > 5_000_000) throw new Error("File is too large (maximum 5 MB per deck).");
            const content = await input.file.text();
            request = { ...(content.trimStart().startsWith("{") ? { json: content } : { text: content }) };
          } else request = { archidekt: input.url };
          const parsed = await previewImport(request);
          if (parsed.entries.length === 0) throw new Error("No cards found in this export.");
          request.name = parsed.name || (input.file ? input.file.name.replace(/\.[^.]+$/, "") : undefined);
          results.push({ label: input.label, request, preview: parsed, state: "ready" });
        } catch (e) {
          results.push({ label: input.label, request, state: "failed", error: e instanceof Error ? e.message : String(e) });
        }
        setItems([...results]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  const save = async () => {
    setBusy(true);
    try {
      for (let index = 0; index < items.length; index++) {
        const item = items[index];
        if (!item || item.state !== "ready") continue;
        patch(index, { state: "saving" });
        try {
          const result = await saveDeckForOffline(item.request, online && download);
          const unresolved = result.deck.import_report?.unresolved.length ?? 0;
          patch(index, {
            state: "saved", deckId: result.deck.id,
            artwork: result.artwork === "ready" ? "Artwork available offline" : result.artwork === "incomplete" ? "Artwork incomplete" : "Artwork not downloaded",
            error: [result.notice, unresolved ? `${unresolved} unresolved card(s): review this deck before playing.` : undefined].filter(Boolean).join(" "),
          });
          onSaved();
        } catch (e) {
          patch(index, { state: "failed", error: e instanceof Error ? e.message : String(e) });
        }
      }
      setFinished(true);
    } finally { setBusy(false); }
  };

  const ready = items.some(i => i.state === "ready");
  const STATE: Record<Item["state"], string> = { ready: "Ready to import", saving: "Saving…", saved: "Saved to this host", failed: "Import failed" };
  return (
    <Modal title="Import multiple decks" onClose={close} wide footer={
      <>
        <span className="spacer" />
        <button className="tt-btn ghost" disabled={busy} onClick={close}>{finished ? "Done" : "Cancel"}</button>
        {!finished && <button className={`tt-btn ${ready ? "" : "brass"}`} disabled={busy || (!files.length && !urls.trim())} onClick={() => void preview()}>Preview decks</button>}
        {!finished && <button className={`tt-btn ${ready ? "brass" : ""}`} disabled={busy || !ready} onClick={() => void save()}>Save decks</button>}
      </>
    }>
      <div className="bulk">
        <p className="bulk-lead">Import your decks while connected to the internet. Deck lists are saved on this Fyodor host and stay available after restarting. Connect to this host to use them without internet.</p>
        {!finished && <div className={`bulk-inputs ${online ? "two" : ""}`}>
          <label className={`bulk-drop ${files.length ? "has-files" : ""}`}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); if (busy) return; setFiles(Array.from(e.dataTransfer.files)); invalidate(); }}>
            <input className="bulk-file" type="file" multiple accept=".txt,.csv,.json,.dek" disabled={busy} aria-label="Deck export files"
              onChange={e => { setFiles(Array.from(e.target.files ?? [])); invalidate(); }} />
            <Icon name="cards" size={26} />
            <b>Deck export files</b>
            <span>{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}: ${files.map(f => f.name).join(", ")}` : "Choose files, or drop them here"}</span>
            <span className="bulk-dim">Exports from Archidekt, Moxfield, MTGGoldfish, Arena, or plain text. Each file becomes a separate deck.</span>
          </label>
          {online && <label className="field bulk-urls">Archidekt deck URLs (one per line)<textarea value={urls} disabled={busy} rows={5} onChange={e => { setUrls(e.target.value); invalidate(); }} placeholder="https://archidekt.com/decks/…" /></label>}
        </div>}
        {!finished && online && <label className="check bulk-art"><input type="checkbox" checked={download} disabled={busy} onChange={e => setDownload(e.target.checked)} /> Download artwork for offline play</label>}
        {error && <p role="alert" className="bulk-error">{error}</p>}
        {busy && <p role="status" className="bulk-status">{items.some(i => i.state === "saving") ? "Saving decks and downloading artwork… Keep this window open." : "Previewing decks…"}</p>}
        {items.length > 0 && <ul className="bulk-list">{items.map((item, i) => <li key={i} className={`bulk-item ${item.state}`}>
          <span className="bulk-mark" aria-hidden>{item.state === "failed" ? "!" : item.state === "saved" ? <Icon name="check" size={14} /> : ""}</span>
          <div className="bulk-body">
            <strong>{item.preview?.name || item.request.name || item.label}</strong>
            <div className="bulk-state">{STATE[item.state]}</div>
            {item.preview && <div className="bulk-dim">{item.preview.report.cards_total} cards · {item.preview.report.unresolved.length} unresolved · {item.preview.report.fallbacks.length} printing substitutions</div>}
            {item.artwork && <div className="bulk-dim">{item.artwork}</div>}
            {item.error && <div className="bulk-warn">{item.error}</div>}
          </div>
          {item.deckId && <a className="tt-btn ghost bulk-review" href={`#/decks/${item.deckId}`} onClick={e => { if (busy) e.preventDefault(); else close(); }}>Review saved deck</a>}
        </li>)}</ul>}
      </div>
    </Modal>
  );
}
