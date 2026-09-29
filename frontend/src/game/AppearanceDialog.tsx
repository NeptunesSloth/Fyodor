import { useEffect, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { listAssets, uploadAsset, type Asset, type AssetKind } from "../services/assets";
import { perspective, useGame } from "../state/gameStore";
import type { Playmat } from "../types/game";
import { send } from "./actions";
import { playmatStyle } from "./appearance";
import { useIsHost } from "./HostTools";

const DEFAULT_MAT = (asset_id: string): Playmat => ({
  asset_id, fit: "cover", scale: 1, offset_x: 0, offset_y: 0, rotation: 0, opacity: 1, show_zones: true,
});

/**
 * Settings → Appearance: your card back (sleeves) and playmat, plus the table mat for the host.
 * Images are uploaded to the host's asset library once and cached by every browser at the table.
 */
export function AppearanceDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const isHost = useIsHost();
  const [backs, setBacks] = useState<Asset[]>([]);
  const [mats, setMats] = useState<Asset[]>([]);
  const me = view ? perspective(view, actingAs) : "";
  const player = view?.players.find((p) => p.id === me);
  const [mat, setMat] = useState<Playmat | null>(player?.playmat ?? null);
  const [tableMat, setTableMat] = useState<Playmat | null>(view?.table.playmat ?? null);
  const refresh = () => {
    listAssets("card_back").then(setBacks, toastError);
    listAssets("playmat").then(setMats, toastError);
  };
  useEffect(refresh, []);
  if (!view || !player) return null;
  const gameId = view.game.id;
  const urlOf = (id: string | undefined | null) => (id ? mats.concat(backs).find((a) => a.id === id)?.url ?? view.game.assets?.[id]?.url : undefined);

  const upload = async (file: File, kind: AssetKind) => {
    try {
      const a = await uploadAsset(file, kind, file.name.replace(/\.[^.]+$/, ""), gameId);
      toast(`Added “${a.name}” (${a.width}×${a.height})`);
      refresh();
      return a;
    } catch (e) {
      toastError(e);
      return null;
    }
  };

  return (
    <Modal title="Appearance" onClose={onClose} wide>
      <div className="appearance" data-testid="appearance">
        <section>
          <h3>Card back (sleeves)</h3>
          <p className="hint">Everyone at the table sees your cards' backs in these sleeves. It's only a picture — card identity stays on the host.</p>
          <div className="asset-picks">
            <button className={`asset-pick ${!player.sleeve ? "on" : ""}`} onClick={() => void send({ type: "set_appearance", clear_sleeve: true })}>
              <div className="card-face card-back" />
              <span>Default</span>
            </button>
            {backs.map((a) => (
              <button key={a.id} className={`asset-pick ${player.sleeve === a.id ? "on" : ""}`} data-testid="sleeve-pick"
                onClick={() => void send({ type: "set_appearance", sleeve: a.id })}>
                <div className="card-face card-back sleeved" style={{ backgroundImage: `url("${a.url}")`, backgroundSize: "cover" }} />
                <span>{a.name}</span>
              </button>
            ))}
            <FilePick label="Local image…" testId="sleeve-file" onFile={async (f) => {
              const a = await upload(f, "card_back");
              if (a) void send({ type: "set_appearance", sleeve: a.id });
            }} />
          </div>
        </section>

        <section>
          <h3>Your playmat</h3>
          <MatEditor mats={mats} value={mat} urlOf={urlOf} onChange={setMat} onUpload={(f) => upload(f, "playmat")} testId="mat" />
          <div className="appearance-actions">
            <button className="tt-btn brass" data-testid="mat-save" onClick={() => void send(mat ? { type: "set_appearance", playmat: mat } : { type: "set_appearance", clear_playmat: true })}>
              {mat ? "Use this playmat" : "Remove my playmat"}
            </button>
          </div>
        </section>

        {isHost && (
          <section>
            <h3>Table playmat (host)</h3>
            <MatEditor mats={mats} value={tableMat} urlOf={urlOf} onChange={setTableMat} onUpload={(f) => upload(f, "playmat")} testId="table-mat" />
            <div className="appearance-actions">
              <button className="tt-btn" onClick={() => void send({ type: "set_table_playmat", playmat: tableMat })}>
                {tableMat ? "Put under the whole table" : "Remove table playmat"}
              </button>
            </div>
          </section>
        )}
      </div>
    </Modal>
  );
}

function FilePick({ label, onFile, testId }: { label: string; onFile: (f: File) => void; testId: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={input} type="file" hidden accept="image/png,image/jpeg,image/webp" data-testid={testId}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      <button className="asset-pick add" onClick={() => input.current?.click()}><span>+ {label}</span></button>
    </>
  );
}

function MatEditor({ mats, value, urlOf, onChange, onUpload, testId }: {
  mats: Asset[];
  value: Playmat | null;
  urlOf: (id: string | null | undefined) => string | undefined;
  onChange: (m: Playmat | null) => void;
  onUpload: (f: File) => Promise<Asset | null>;
  testId: string;
}) {
  const set = (patch: Partial<Playmat>) => value && onChange({ ...value, ...patch });
  return (
    <div className="mat-editor">
      <div className="asset-picks">
        <button className={`asset-pick ${!value ? "on" : ""}`} onClick={() => onChange(null)}><div className="mat-thumb none" /><span>None</span></button>
        {mats.map((a) => (
          <button key={a.id} className={`asset-pick ${value?.asset_id === a.id ? "on" : ""}`} data-testid={`${testId}-pick`}
            onClick={() => onChange(value ? { ...value, asset_id: a.id } : DEFAULT_MAT(a.id))}>
            <div className="mat-thumb" style={{ backgroundImage: `url("${a.url}")` }} />
            <span>{a.name}</span>
          </button>
        ))}
        <FilePick label="Local image…" testId={`${testId}-file`} onFile={async (f) => {
          const a = await onUpload(f);
          if (a) onChange(value ? { ...value, asset_id: a.id } : DEFAULT_MAT(a.id));
        }} />
      </div>
      {value && (
        <div className="mat-controls">
          <div className="mat-preview"><div className="playmat-layer" style={playmatStyle(value, urlOf(value.asset_id))} /></div>
          <div className="mat-fields">
            <label className="field">Fit
              <select value={value.fit} onChange={(e) => set({ fit: e.target.value as Playmat["fit"] })}>
                <option value="cover">Fill</option><option value="contain">Fit inside</option><option value="stretch">Stretch</option>
              </select>
            </label>
            <label className="field">Zoom {Math.round(value.scale * 100)}%
              <input type="range" min={0.25} max={4} step={0.05} value={value.scale} onChange={(e) => set({ scale: Number(e.target.value) })} />
            </label>
            <label className="field">Move ←→
              <input type="range" min={-100} max={100} value={value.offset_x} onChange={(e) => set({ offset_x: Number(e.target.value) })} />
            </label>
            <label className="field">Move ↑↓
              <input type="range" min={-100} max={100} value={value.offset_y} onChange={(e) => set({ offset_y: Number(e.target.value) })} />
            </label>
            <label className="field">Rotate
              <select value={value.rotation} onChange={(e) => set({ rotation: Number(e.target.value) as Playmat["rotation"] })}>
                {[0, 90, 180, 270].map((r) => <option key={r} value={r}>{r}°</option>)}
              </select>
            </label>
            <label className="field">Opacity {Math.round(value.opacity * 100)}%
              <input type="range" min={0.1} max={1} step={0.05} value={value.opacity} onChange={(e) => set({ opacity: Number(e.target.value) })} />
            </label>
            <label className="field row-check"><span><input type="checkbox" checked={value.show_zones} onChange={(e) => set({ show_zones: e.target.checked })} /> Show zone outlines</span></label>
            <button className="tt-btn ghost" onClick={() => onChange({ ...DEFAULT_MAT(value.asset_id) })}>Reset</button>
          </div>
        </div>
      )}
    </div>
  );
}
