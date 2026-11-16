import { useEffect, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import {
  addArtFolder, artFolderCount, artFolders, artSourceLabel, removeArtFolder, rescanArtFolders, type ArtFolder,
} from "../services/cardData";

/** -- art folders -- Settings → Card database: more folders of card pictures, read in place on the host (docs/OFFLINE.md). */
export function ArtFoldersSetting() {
  const [list, setList] = useState<ArtFolder[] | null>(null);
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    artFolders().then((r) => setList(r.folders), () => setList([]));
  }, []);
  const run = async <T extends { folders: ArtFolder[] }>(work: () => Promise<T>, done?: (r: T) => void) => {
    setBusy(true);
    try {
      const r = await work();
      setList(r.folders);
      done?.(r);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const add = () => run(() => addArtFolder(path), (r) => {
    setPath("");
    toast(`Art folder added: ${artFolderCount(r.added)}`);
  });
  if (list === null) return null;
  return (
    <div className="artfolders" data-testid="art-folders">
      <h4>Art folders</h4>
      <p className="hint">Folders of card pictures Fyodor reads in place, after its own. Nothing is copied or changed in them.</p>
      {list.length > 0 && (
        <ul className="artfolders-list">
          {list.map((f) => (
            <li key={`${f.source}:${f.path}`} data-testid="art-folder">
              <span className="artfolders-path" title={f.folder !== f.path ? `Pictures from ${f.folder}` : undefined}>{f.path}</span>
              <span className={`artfolders-count ${f.exists ? "" : "warn"}`}>{artFolderCount(f)}</span>
              <span className="artfolders-source">{artSourceLabel(f.source)}</span>
              {f.source === "added" && (
                <button className="tt-btn" disabled={busy} aria-label={`Remove ${f.path}`}
                  onClick={() => void run(() => removeArtFolder(f.path))}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form className="artfolders-add" onSubmit={(e) => { e.preventDefault(); if (path.trim()) void add(); }}>
        <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\Users\you\Fyodor\images" spellCheck={false}
          aria-label="Folder path" data-testid="art-folder-path" />
        <button className="tt-btn brass" type="submit" disabled={busy || !path.trim()} data-testid="art-folder-add">Add</button>
        <button className="tt-btn" type="button" disabled={busy} onClick={() => void run(rescanArtFolders)} data-testid="art-folder-rescan">
          Rescan
        </button>
      </form>
      <p className="hint">Paste a folder's path from File Explorer. Fyodor looks for its cards and tokens folders, an images folder
        inside it, or pictures named by Scryfall id.</p>
    </div>
  );
}
