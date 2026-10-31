import { useEffect, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { cacheArt, createDeck, importOptions, previewImport } from "../services/decks";
import type { ImportRequest, ParsePreview } from "../types/decks";

type Source = "url" | "paste" | "file" | "other";

interface Options {
  archidekt_url: boolean;
  archidekt_url_note: string;
}

/**
 * Deck import with Archidekt first: paste a deck URL, paste Archidekt's text export, or
 * upload an exported file. Every path shows a preview (printings, fallbacks, categories)
 * before anything is saved.
 */
export function ImportDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string, jobId?: string) => void }) {
  const [options, setOptions] = useState<Options | null>(null);
  const [source, setSource] = useState<Source>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<ParsePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cacheImages, setCacheImages] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    importOptions().then(
      (o) => {
        setOptions(o);
        if (!o.archidekt_url) setSource("paste");
      },
      () => setOptions({ archidekt_url: false, archidekt_url_note: "Could not check import options." }),
    );
  }, []);

  const request = (): ImportRequest | null => {
    if (source === "url") return url.trim() ? { archidekt: url.trim() } : null;
    if (source === "file") {
      if (!file) return null;
      return file.content.trimStart().startsWith("{") ? { json: file.content } : { text: file.content };
    }
    return text.trim() ? { text } : null;
  };

  const runPreview = async (req: ImportRequest | null) => {
    setPreviewError(null);
    if (!req) {
      setPreview(null);
      return;
    }
    setLoading(true);
    try {
      setPreview(await previewImport(req));
    } catch (e) {
      setPreview(null);
      setPreviewError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // Text previews update as you type; URL previews only on request (they use the network).
  useEffect(() => {
    if (source !== "paste" && source !== "other") return;
    const t = setTimeout(() => void runPreview(request()), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, source]);

  useEffect(() => {
    if (source === "file") void runPreview(request());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, source]);

  const submit = async () => {
    const req = request();
    if (!req) return;
    setBusy(true);
    try {
      const deck = await createDeck({ ...req, name: name.trim() || undefined, });
      const r = deck.import_report;
      const issues = (r?.unresolved.length ?? 0) + (r?.fallbacks.length ?? 0);
      toast(issues ? `Imported ${deck.name} — ${issues} card(s) need a look` : `Imported ${deck.name}`, issues ? "warn" : "info");
      let jobId: string | undefined;
      if (cacheImages && options?.archidekt_url) {
        jobId = (await cacheArt(deck.id).catch(() => null))?.id;
      }
      onCreated(deck.id, jobId);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    if (f.size > 5_000_000) {
      toast("That file is too large for a deck export", "error");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setFile({ name: f.name, content: String(reader.result ?? "") });
    reader.readAsText(f);
  };

  const r = preview?.report;
  const isArchidekt = source !== "other";

  return (
    <Modal
      title="Import deck"
      onClose={onClose}
      wide
      footer={
        <>
          {options?.archidekt_url && (
            <label className="check" title="Download missing card images now so the deck plays offline with full art">
              <input type="checkbox" checked={cacheImages} onChange={(e) => setCacheImages(e.target.checked)} /> Cache all artwork for offline use
            </label>
          )}
          <span className="spacer" />
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!preview || busy || !request()} onClick={() => void submit()}>
            {busy ? "Importing…" : "Import deck"}
          </button>
        </>
      }
    >
      <div className="import-sources">
        <div className="source-group">
          <span className="source-brand">Import from Archidekt</span>
          <div className="seg">
            {options?.archidekt_url && (
              <button className={source === "url" ? "on" : ""} onClick={() => setSource("url")}>Deck URL</button>
            )}
            <button className={source === "paste" ? "on" : ""} onClick={() => setSource("paste")}>Paste export</button>
            <button className={source === "file" ? "on" : ""} onClick={() => setSource("file")}>Upload file</button>
          </div>
        </div>
        <div className="source-group">
          <span className="source-brand dim">Other</span>
          <div className="seg">
            <button className={source === "other" ? "on" : ""} onClick={() => setSource("other")}>Moxfield · MTGGoldfish · plain text</button>
          </div>
        </div>
      </div>

      <div className="import-grid">
        <div className="import-left">
          {source === "url" && (
            <>
              <form className="row" onSubmit={(e) => { e.preventDefault(); void runPreview(request()); }}>
                <label className="field grow">
                  Archidekt deck URL
                  <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://archidekt.com/decks/1234567/my_deck" />
                </label>
                <button className="btn primary" type="submit" disabled={!url.trim() || loading}>{loading ? "Fetching…" : "Fetch"}</button>
              </form>
              <p className="hint">{options?.archidekt_url_note} After import the deck is stored locally and never needs Archidekt again.</p>
            </>
          )}
          {(source === "paste" || source === "other") && (
            <>
              <textarea
                className="deck-text"
                autoFocus
                spellCheck={false}
                placeholder={
                  source === "paste"
                    ? "In Archidekt: Export → Copy text. Lines look like\n1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]\n1x Sol Ring (cmm) 410 [Ramp]\n1x Opt (eld) 59 [Maybeboard{noDeck}{noPrice}]"
                    : "Commander\n1 Krenko, Mob Boss\n\nDeck\n1 Sol Ring (CMM) 410\n30 Mountain"
                }
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </>
          )}
          {source === "file" && (
            <div
              className="drop-file"
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                onFile(e.dataTransfer.files[0]);
              }}
            >
              <input ref={fileInput} type="file" accept=".txt,.dek,.json,text/plain,application/json" hidden onChange={(e) => onFile(e.target.files?.[0])} />
              {file ? <b>{file.name}</b> : <b>Drop an Archidekt export here, or click to choose</b>}
              <span className="hint">Text export (.txt) or a saved Archidekt deck (.json)</span>
            </div>
          )}
          <div className="row">
            <label className="field grow">
              Name
              <input value={name} placeholder={preview?.name ?? "Deck name"} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>
        </div>

        <div className="import-right">
          <h4>{isArchidekt ? "Archidekt import" : "Import"} preview</h4>
          {loading && <p className="hint">Reading deck…</p>}
          {previewError && <p className="error">{previewError}</p>}
          {!preview && !loading && !previewError && <p className="hint">Nothing to preview yet.</p>}
          {preview && r && (
            <>
              {preview.name && <div className="preview-name">{preview.name}</div>}
              <ul className="import-stats">
                <li className="ok">✓ {r.cards_total} cards detected{r.sections.maybeboard ? ` (+${r.sections.maybeboard} maybeboard)` : ""}</li>
                <li className={r.unresolved.length ? "warn" : "ok"}>
                  {r.unresolved.length ? "!" : "✓"} {r.resolved} card names resolved{r.unresolved.length ? `, ${r.unresolved.length} not found` : ""}
                </li>
                <li className="ok">✓ {r.exact_printings} exact printings resolved</li>
                {r.fallbacks.length > 0 && (
                  <li className="warn">
                    ! {r.fallbacks.length} printing fallback{r.fallbacks.length > 1 ? "s" : ""}
                    <ul className="sub">
                      {r.fallbacks.slice(0, 8).map((f, i) => (
                        <li key={i}>{f.name}: {f.requested} not in local data → {f.used}</li>
                      ))}
                    </ul>
                  </li>
                )}
                <li className={r.commanders.length ? "ok" : "hint"}>
                  {r.commanders.length ? `✓ Commander detected: ${r.commanders.join(" & ")}` : "No commander detected"}
                </li>
                {r.categories.length > 0 && (
                  <li className="ok">
                    ✓ {r.categories.length} categories imported
                    <div className="cat-chips">{r.categories.slice(0, 24).map((c) => <span key={c} className="chip">{c}</span>)}</div>
                  </li>
                )}
                {(r.sections.sideboard ?? 0) > 0 && <li className="ok">✓ Sideboard: {r.sections.sideboard}</li>}
              </ul>
              {r.unresolved.length > 0 && (
                <div className="unresolved">
                  <b className="warn">Not found in the local card database</b>
                  {r.unresolved.map((u, i) => (
                    <div key={i}>
                      {u.quantity}× {u.name}
                      {u.suggestions.length > 0 && <span className="hint"> — did you mean {u.suggestions.slice(0, 3).join(", ")}?</span>}
                    </div>
                  ))}
                  <div className="hint">They are kept in the deck and can be fixed in the editor.</div>
                </div>
              )}
              {r.notes.map((n) => <p key={n} className="hint">{n}</p>)}
              {r.errors.map((e) => <div key={e} className="error small">{e}</div>)}
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
