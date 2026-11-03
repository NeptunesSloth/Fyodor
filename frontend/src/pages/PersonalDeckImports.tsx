import { useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { toastError } from "../components/Toasts";
import { exportPersonalLibrary, personalDeckFile } from "../services/personalLibrary";
import { ApiError } from "../services/api";
import { importPersonalDeck, rememberMyDeck, type LobbyDeckBody } from "../services/games";
import "./decks.css";

/** Personal, device-local imports: URLs are resolved now, lists remain usable offline. */
export function PersonalDeckImports({ gameId, onSaved, disabled = false, onBusyChange }: { gameId: string; onSaved: () => void | Promise<void>; disabled?: boolean; onBusyChange?: (busy: boolean) => void }) {
  const files = useRef<HTMLInputElement>(null);
  const [urls, setUrls] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<string[]>([]);

  const save = async (requests: { label: string; body: () => Promise<LobbyDeckBody> }[]) => {
    setBusy(true);
    onBusyChange?.(true);
    setResults([]);
    try {
      for (const request of requests) {
        try {
          const body = await request.body();
          let imported;
          try { imported = await importPersonalDeck(gameId, body); }
          catch (e) {
            if (!(e instanceof ApiError && e.status === 429)) throw e;
            await new Promise(resolve => setTimeout(resolve, 3100));
            imported = await importPersonalDeck(gameId, body);
          }
          if (imported.entries.some(e => !e.printing_id && e.section !== "tokens" && e.section !== "maybeboard")) {
            throw new Error("Some cards could not be resolved. Correct the list and import it again.");
          }
          rememberMyDeck(imported.name, body, imported.commanders, imported);
          await onSaved();
          setResults(old => [...old, `${request.label}: saved for offline play`]);
        } catch (e) {
          setResults(old => [...old, `${request.label}: not saved — ${e instanceof Error ? e.message : String(e)}`]);
        }
      }
    } finally { setBusy(false); onBusyChange?.(false); }
  };

  return <div className="deck-form pdi">
    <p className="hint">Import your decks here while online. Lists are saved on this device and supplied as your private collection when you choose a deck. Internet is not needed to reuse saved lists at a table.</p>
    <input ref={files} hidden type="file" multiple accept=".txt,.dec,.dek,.json,.csv,text/plain,application/json"
      onChange={e => {
        const chosen = Array.from(e.target.files ?? []);
        e.target.value = "";
        setBusy(true);
        onBusyChange?.(true);
        void (async () => {
          const requests: { label: string; body: () => Promise<LobbyDeckBody> }[] = [];
          for (const file of chosen) {
            try {
              if (file.size > 20 * 1024 * 1024) throw new Error("File exceeds 20 MB");
              for (const parsed of personalDeckFile(await file.text(), file.name)) {
                requests.push({ label: parsed.label, body: async () => parsed.body });
              }
            } catch (error) { requests.push({ label: file.name, body: async () => { throw error; } }); }
          }
          await save(requests);
        })();
      }} />
    <div className="pdi-row">
      <button className="tt-btn" disabled={busy || disabled} onClick={() => files.current?.click()}><Icon name="cards" size={15} />Import multiple deck files…</button>
      <button className="tt-btn ghost" disabled={busy || disabled} onClick={() => {
        try {
          const url = URL.createObjectURL(new Blob([exportPersonalLibrary()], { type: "application/json" }));
          const a = document.createElement("a");
          a.href = url; a.download = "fyodor-my-decks.json"; a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { toastError(error); }
      }}><Icon name="download" size={15} />Export My decks</button>
    </div>
    <p className="hint">Export a backup to move your saved decks to another device or table address. Import it here without Internet.</p>
    <label className="field">Public Archidekt deck URLs, one per line
      <textarea value={urls} disabled={busy || disabled} maxLength={15000} rows={3} onChange={e => setUrls(e.target.value)} placeholder="https://archidekt.com/decks/…" />
    </label>
    <button className="tt-btn" disabled={busy || disabled || !urls.trim()} onClick={() => void save(
      urls.split(/\r?\n/).map(u => u.trim()).filter(Boolean).map(url => ({ label: url, body: async () => ({ archidekt: url }) }))
    )}>{busy ? "Saving decks…" : "Save these decks"}</button>
    {results.length > 0 && <ul className="pdi-results" aria-live="polite">{results.map((result, i) => <li key={i} className={result.includes(": not saved") ? "bad" : "good"}>{result}</li>)}</ul>}
  </div>;
}
