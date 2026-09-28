import { useCallback, useEffect, useRef, useState } from "react";
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

/** One tidy place for every custom image: playmats, card backs, token art and more. */
export function AssetManager() {
  const [kind, setKind] = useState<AssetKind>("playmat");
  const [assets, setAssets] = useState<Asset[]>([]);
  const add = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState<string | null>(null);
  const refresh = useCallback(() => listAssets().then(setAssets, toastError), []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const shown = assets.filter((a) => a.kind === kind);
  const count = (k: AssetKind) => assets.filter((a) => a.kind === k).length;

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
        <span className="hint">PNG, JPEG or WEBP · up to 20 MB and 8192×8192 · checked by content · stored on this computer</span>
      </header>
      <nav className="am-kinds">
        {ASSET_KINDS.map(([k, label]) => (
          <button key={k} className={`tt-tab ${kind === k ? "on" : ""}`} onClick={() => setKind(k)}>
            {label} <span className="hint">{count(k) || ""}</span>
          </button>
        ))}
      </nav>
      <div className="am-actions">
        <input ref={add} type="file" hidden multiple accept="image/png,image/jpeg,image/webp" data-testid="asset-upload"
          onChange={async (e) => {
            for (const f of Array.from(e.target.files ?? [])) {
              await uploadAsset(f, kind, f.name.replace(/\.[^.]+$/, "")).then((a) => toast(`Added “${a.name}”`), toastError);
            }
            e.target.value = "";
            void refresh();
          }} />
        <input ref={replaceInput} type="file" hidden accept="image/png,image/jpeg,image/webp"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f && replacing) await replaceAsset(replacing, f).then(() => toast("Replaced — tables using it update"), toastError);
            e.target.value = "";
            setReplacing(null);
            void refresh();
          }} />
        <button className="tt-btn brass" onClick={() => add.current?.click()}>Add images…</button>
      </div>
      {shown.length === 0 && <p className="hint">Nothing here yet.</p>}
      <div className="am-grid">
        {shown.map((a) => (
          <article key={a.id} className="am-item" data-testid="asset-item">
            <div className={`am-preview ${a.kind === "card_back" ? "tall" : ""}`} style={{ backgroundImage: `url("${a.url}")` }} />
            <div className="am-meta">
              <b title={a.name}>{a.name}</b>
              <span className="hint">{a.width}×{a.height} · {fmtSize(a.size)} · {a.mime.split("/")[1]}</span>
              <span className={`hint ${a.used_by?.length ? "used" : ""}`}>{a.used_by?.length ? `Used by ${a.used_by.join("; ")}` : "Not in use"}</span>
            </div>
            <div className="am-buttons">
              <button className="tt-btn ghost" onClick={async () => {
                const n = await askText("Name", a.name);
                if (n) await renameAsset(a.id, n).then(() => refresh(), toastError);
              }}>Rename</button>
              <button className="tt-btn ghost" onClick={() => { setReplacing(a.id); replaceInput.current?.click(); }}>Replace</button>
              <button className="tt-btn ghost" onClick={() => void duplicateAsset(a.id).then(() => refresh(), toastError)}>Duplicate</button>
              <button className="tt-btn ghost danger" onClick={() => void remove(a)}>Delete</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
