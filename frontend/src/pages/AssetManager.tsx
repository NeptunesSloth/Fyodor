import { useCallback, useEffect, useId, useRef, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { askText } from "../components/Prompt";
import { ApiError } from "../services/api";
import {
  ASSET_KINDS,
  deleteAsset,
  duplicateAsset,
  fmtSize,
  listAssets,
  renameAsset,
  replaceAsset,
  uploadAsset,
  type Asset,
  type AssetKind,
} from "../services/assets";
import "./assets.css";

/** What each kind of image is for, in a line (playmats and card backs are chosen at the table and in Settings). */
const KIND_NOTE: Partial<Record<AssetKind, string>> = {
  playmat: "A playmat lies under a player's battlefield. Choose yours in Settings → Profile, or from Appearance at the table.",
  card_back: "Sleeves: the backs of your cards. Choose yours in Settings → Profile, or from Appearance at the table.",
};
const OTHER_NOTE = "Images you keep on this computer for your games.";
const ACCEPT = "image/png,image/jpeg,image/webp";

/** One tidy place for every custom image: playmats, card backs, token art and more. */
export function AssetManager() {
  const [kind, setKind] = useState<AssetKind>("playmat");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [dropping, setDropping] = useState(false);
  const add = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState<string | null>(null);
  const addId = useId();
  const refresh = useCallback(() => listAssets().then((a) => { setAssets(a); setLoaded(true); }, toastError), []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const shown = assets.filter((a) => a.kind === kind);
  const count = (k: AssetKind) => assets.filter((a) => a.kind === k).length;
  const label = ASSET_KINDS.find(([k]) => k === kind)?.[1] ?? "";

  const addFiles = async (files: File[]) => {
    for (const f of files) {
      await uploadAsset(f, kind, f.name.replace(/\.[^.]+$/, "")).then((a) => toast(`Added “${a.name}”`), toastError);
    }
    void refresh();
  };

  const remove = async (a: Asset) => {
    const used = a.used_by ?? [];
    const msg = used.length
      ? `“${a.name}” is in use:\n${used.join("\n")}\n\nDelete it anyway? Those tables fall back to the default look.`
      : `Delete “${a.name}”?`;
    if (!window.confirm(msg)) return;
    try {
      await deleteAsset(a.id, used.length > 0);
      toast("Deleted");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) toast(e.message, "error");
      else toastError(e);
    }
    void refresh();
  };

  return (
    <div className="page asset-manager" data-testid="asset-manager">
      <header className="am-head">
        <h1>Assets</h1>
        <p>Your own sleeves, playmats and table art, stored on this computer.</p>
      </header>
      <nav className="am-kinds" aria-label="Kinds of image">
        {ASSET_KINDS.map(([k, name]) => (
          <button key={k} type="button" className={`am-kind ${kind === k ? "on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>
            {name} {count(k) ? <span className="am-count">{count(k)}</span> : null}
          </button>
        ))}
      </nav>
      <p className="am-note">
        {KIND_NOTE[kind] ?? OTHER_NOTE} <span>PNG, JPEG or WEBP, up to 20 MB and 8192×8192, checked by content.</span>
      </p>
      <input ref={add} type="file" hidden multiple accept={ACCEPT} data-testid="asset-upload"
        onChange={async (e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          await addFiles(files);
        }} />
      <input ref={replaceInput} type="file" hidden accept={ACCEPT}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f && replacing) await replaceAsset(replacing, f).then(() => toast("Replaced — tables using it update"), toastError);
          e.target.value = "";
          setReplacing(null);
          void refresh();
        }} />
      <div className={`am-grid ${kind}`}>
        {shown.map((a) => {
          const used = a.used_by ?? [];
          return (
            <article key={a.id} className="am-item" data-testid="asset-item">
              <div className="am-preview" aria-hidden><span className="am-img" style={{ backgroundImage: `url("${a.url}")` }} /></div>
              <div className="am-meta">
                <b title={a.name}>{a.name}</b>
                <span className="am-facts"><span>{a.width}×{a.height}</span><span>{fmtSize(a.size)}</span><span>{a.mime.split("/")[1]}</span></span>
                <span className={`am-use ${used.length ? "used" : ""}`}>{used.length ? `Used by ${used.join("; ")}` : "Not in use"}</span>
              </div>
              <div className="am-buttons">
                <button className="tt-btn ghost" onClick={async () => {
                  const n = await askText("Name", a.name);
                  if (n) await renameAsset(a.id, n).then(() => refresh(), toastError);
                }}>Rename</button>
                <button className="tt-btn ghost" onClick={() => { setReplacing(a.id); replaceInput.current?.click(); }}>Replace</button>
                <button className="tt-btn ghost" onClick={() => void duplicateAsset(a.id).then(() => refresh(), toastError)}>Duplicate</button>
                <button className="tt-btn ghost am-delete" onClick={() => void remove(a)}>Delete</button>
              </div>
            </article>
          );
        })}
        {/* the empty slot at the end of the shelf: click to choose images, or drop them on it */}
        <button type="button" className={`am-add ${shown.length === 0 ? "alone" : ""} ${dropping ? "dropping" : ""}`}
          aria-labelledby={`${addId}-name`} aria-describedby={`${addId}-hint`} onClick={() => add.current?.click()}
          onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDropping(true); } }}
          onDragLeave={() => setDropping(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDropping(false);
            void addFiles(Array.from(e.dataTransfer.files).filter((f) => ACCEPT.split(",").includes(f.type)));
          }}>
          <span className="am-add-plus" aria-hidden>+</span>
          <span className="am-add-name" id={`${addId}-name`}>Add images…</span>
          <span className="am-add-hint" id={`${addId}-hint`}>
            {loaded && shown.length === 0 ? `No ${label.toLowerCase()} yet. Choose images, or drop them here.` : "Or drop them here"}
          </span>
        </button>
      </div>
    </div>
  );
}
