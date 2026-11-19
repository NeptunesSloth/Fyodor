import { useEffect, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { cacheArt, createDeck, importOptions, previewImport } from "../services/decks";
import { useCard } from "../state/cardCache";
import type { ImportRequest, ParsePreview } from "../types/decks";
import { DeckArt } from "./DeckParts";

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
      // (a card not found needs the player; a printing swapped for one this computer has is only worth a mention)
      const missing = r?.unresolved.length ?? 0;
      const swapped = r?.fallbacks.length ?? 0;
      toast(missing ? `Imported ${deck.name}: ${missing === 1 ? "1 card wasn't found" : `${missing} cards weren't found`}`
        : swapped ? `Imported ${deck.name} (${swapped === 1 ? "1 printing" : `${swapped} printings`} swapped for one on this computer)`
        : `Imported ${deck.name}`, missing ? "warn" : "info");
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
  const tab = (key: Source, label: string) => (
    <button type="button" className={`imp-src ${source === key ? "on" : ""}`} aria-pressed={source === key} onClick={() => setSource(key)}>{label}</button>
  );

  return (
    <Modal
      title="Import a deck"
      onClose={onClose}
      wide
      footer={
        <>
          {options?.archidekt_url && (
            <label className="check imp-cache" title="Download missing card images now so the deck plays offline with full art">
              <input type="checkbox" checked={cacheImages} onChange={(e) => setCacheImages(e.target.checked)} /> Cache all artwork for offline use
            </label>
          )}
          <span className="spacer" />
          <button className="tt-btn ghost" onClick={onClose}>Cancel</button>
          <button className="tt-btn brass imp-go" disabled={!preview || busy || !request()} onClick={() => void submit()}>
            {busy ? "Importing…" : "Import deck"}
          </button>
        </>
      }
    >
      <div className="imp">
        <div className="imp-sources" role="group" aria-label="Where the deck comes from">
          <span className="imp-from">From Archidekt</span>
          {options?.archidekt_url && tab("url", "Deck URL")}
          {tab("paste", "Paste export")}
          {tab("file", "Upload file")}
          <span className="imp-from imp-other">From elsewhere</span>
          {tab("other", "Moxfield · MTGGoldfish · plain text")}
        </div>

        <div className="imp-grid">
          <div className="imp-left">
            {source === "url" && (
              <>
                <form className="imp-url" onSubmit={(e) => { e.preventDefault(); void runPreview(request()); }}>
                  <label className="field grow">
                    Archidekt deck URL
                    <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://archidekt.com/decks/1234567/my_deck" />
                  </label>
                  <button className="tt-btn" type="submit" disabled={!url.trim() || loading}>{loading ? "Fetching…" : "Fetch"}</button>
                </form>
                <p className="imp-hint">{options?.archidekt_url_note} After import the deck is stored locally and never needs Archidekt again.</p>
              </>
            )}
            {(source === "paste" || source === "other") && (
              <textarea
                className="deck-text imp-text"
                autoFocus
                spellCheck={false}
                aria-label={source === "paste" ? "Archidekt text export" : "Deck list"}
                placeholder={
                  source === "paste"
                    ? "In Archidekt: Export → Copy text. Lines look like\n1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]\n1x Sol Ring (cmm) 410 [Ramp]\n1x Opt (eld) 59 [Maybeboard{noDeck}{noPrice}]"
                    : "Commander\n1 Krenko, Mob Boss\n\nDeck\n1 Sol Ring (CMM) 410\n30 Mountain"
                }
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}
            {source === "file" && (
              <div
                className={`imp-drop ${file ? "has-file" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => fileInput.current?.click()}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.current?.click(); } }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  onFile(e.dataTransfer.files[0]);
                }}
              >
                <input ref={fileInput} type="file" accept=".txt,.dek,.json,text/plain,application/json" hidden onChange={(e) => onFile(e.target.files?.[0])} />
                <Icon name="download" size={26} />
                {file ? <b>{file.name}</b> : <b>Drop an Archidekt export here, or click to choose</b>}
                <span>Text export (.txt) or a saved Archidekt deck (.json)</span>
              </div>
            )}
            <label className="field">
              Name
              <input value={name} placeholder={preview?.name ?? "Deck name"} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>

          <div className="imp-right" aria-live="polite">
            <h3 className="imp-right-title">{isArchidekt ? "Archidekt import" : "Import"} preview</h3>
            {loading && <p className="imp-wait">Reading deck…</p>}
            {previewError && <p className="imp-error">{previewError}</p>}
            {!preview && !loading && !previewError && <p className="imp-wait">Nothing to preview yet. {source === "url" ? "Paste a link and choose Fetch." : source === "file" ? "Choose an export file." : "Paste a list on the left."}</p>}
            {preview && r && (
              <>
                <PreviewDeck preview={preview} name={name} />
                <ul className="imp-stats">
                  <li className="ok">{r.cards_total} cards detected{r.sections.maybeboard ? ` (+${r.sections.maybeboard} maybeboard)` : ""}</li>
                  <li className={r.unresolved.length ? "warn" : "ok"}>
                    {r.resolved} card names resolved{r.unresolved.length ? `, ${r.unresolved.length} not found` : ""}
                  </li>
                  <li className="ok">{r.exact_printings} exact printing{r.exact_printings === 1 ? "" : "s"} resolved</li>
                  {r.fallbacks.length > 0 && (
                    <li className="warn">
                      {r.fallbacks.length} printing fallback{r.fallbacks.length > 1 ? "s" : ""}
                      <ul className="imp-sub">
                        {r.fallbacks.slice(0, 8).map((f, i) => (
                          <li key={i}>{f.name}: {f.requested} not in local data → {f.used}</li>
                        ))}
                      </ul>
                    </li>
                  )}
                  <li className={r.commanders.length ? "ok" : "none"}>
                    {r.commanders.length ? `Commander detected: ${r.commanders.join(" & ")}` : "No commander detected"}
                  </li>
                  {r.categories.length > 0 && (
                    <li className="ok">
                      {r.categories.length} categories imported
                      <div className="imp-chips">{r.categories.slice(0, 24).map((c) => <span key={c} className="imp-chip">{c}</span>)}</div>
                    </li>
                  )}
                  {(r.sections.sideboard ?? 0) > 0 && <li className="ok">Sideboard: {r.sections.sideboard}</li>}
                </ul>
                {r.unresolved.length > 0 && (
                  <div className="imp-unresolved">
                    <b>Not found in the local card database</b>
                    {r.unresolved.map((u, i) => (
                      <div key={i}>
                        {u.quantity}× {u.name}
                        {u.suggestions.length > 0 && <span className="imp-dim"> — did you mean {u.suggestions.slice(0, 3).join(", ")}?</span>}
                      </div>
                    ))}
                    <div className="imp-dim">They are kept in the deck and can be fixed in the editor.</div>
                  </div>
                )}
                {r.notes.map((n) => <p key={n} className="imp-hint">{n}</p>)}
                {r.errors.map((e) => <div key={e} className="imp-error">{e}</div>)}
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

/** The deck the preview found: its commander's art (both partners), the name it will get (as the server picks it), its commander and colours. */
function PreviewDeck({ preview, name }: { preview: ParsePreview; name: string }) {
  const ids = preview.entries.filter((e) => e.section === "commander" && e.printing_id).map((e) => e.printing_id!);
  const a = useCard(ids[0]);
  const b = useCard(ids[1]);
  const colours = ["W", "U", "B", "R", "G"].filter((c) => a?.color_identity?.includes(c) || b?.color_identity?.includes(c));
  return (
    <div className="imp-deck">
      <DeckArt ids={ids} className="imp-art" />
      <div className="imp-deck-text">
        <b>{name.trim() || preview.name || preview.report.commanders.join(" & ") || "Imported deck"}</b>
        {(name.trim() || preview.name) && preview.report.commanders.length > 0 && <span>{preview.report.commanders.join(" & ")}</span>}
        {ids.length > 0 && (a || b) && <ColorPips colors={colours} />}
      </div>
    </div>
  );
}
