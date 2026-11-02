import { useEffect, useRef, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { api, ApiError } from "../services/api";
import { effectiveHotkeys, collisions, comboOf, KEY_PRESETS, type HotkeyId } from "../game/hotkeys";
import { play } from "../game/sound";
import { listAssets, type Asset } from "../services/assets";
import { backupSize, whenMade, type AutoBackupStatus, type BackupInfo } from "../services/backups";
import { CardDataSection } from "./CardDataPanel";
import { HAND_SORTS, HAND_SORT_LABEL } from "../game/handSort";
import { pct, podPlayer, podPlayers, type PodPlayerDetail } from "../services/pod";
import { GRAPHICS_NOTES } from "../state/applyPrefs";
import { usePrefs, type Prefs } from "../state/prefs";
import { PLANES, type PlaneTheme } from "../theme/planes";
import "./settings.css";

/** A tiny painting of a plane for its tile: sky, glow and table surface. */
function planePreview(pl: PlaneTheme): string {
  const e = pl.env;
  return [
    `radial-gradient(ellipse 30% 40% at 18% 35%, ${e.glow}66, transparent 70%)`,
    `radial-gradient(ellipse 25% 35% at 82% 30%, ${e.rim}55, transparent 70%)`,
    `linear-gradient(180deg, ${e.skyTop} 0%, ${e.skyBottom} 52%, ${e.surfaceBase} 53%, ${e.surfaceGrain} 100%)`,
  ].join(", ");
}

const AVATARS = ["♠", "♥", "♦", "♣", "★", "☾", "☀", "⚔", "♛", "✦"];

/**
 * Settings: local profile (no account), display & accessibility, sound, table & performance,
 * and keys. Everything is stored in this browser only.
 */
export function SettingsPanel() {
  const p = usePrefs();
  const profile = p.profiles.find((x) => x.id === p.active)!;
  const [stats, setStats] = useState<PodPlayerDetail | null>(null);
  const [backs, setBacks] = useState<Asset[]>([]);
  const [mats, setMats] = useState<Asset[]>([]);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    listAssets("card_back").then(setBacks, () => undefined);
    listAssets("playmat").then(setMats, () => undefined);
  }, []);
  useEffect(() => {
    setStats(null);
    podPlayers().then((all) => {
      const me = all.find((x) => x.name.toLowerCase() === profile.name.toLowerCase());
      if (me) podPlayer(me.id).then(setStats, () => undefined);
    }, () => undefined);
  }, [profile.name]);
  const set = (patch: Partial<Prefs>) => p.set(patch);
  const vol = (k: keyof Prefs["sound"], label: string) => (
    <label className="field">{label} {Math.round(Number(p.sound[k]) * 100)}%
      <input type="range" min={0} max={1} step={0.05} value={Number(p.sound[k])} onChange={(e) => set({ sound: { ...p.sound, [k]: Number(e.target.value) } })} />
    </label>
  );

  return (
    <div className="settings" data-testid="settings">
      <section>
        <h2>Table theme</h2>
        <p className="hint">Each theme is a Magic plane: its table surface, lighting, props, ambient sound and accent colours. Cards and prompts always look the same.</p>
        {[1, 2].map((wave) => (
          <div key={wave} className="theme-grid" style={{ marginBottom: 12 }}>
            {PLANES.filter((pl) => pl.wave === wave).map((pl) => (
              <button key={pl.id} className={`theme-tile ${p.plane === pl.id ? "on" : ""}`} data-testid={`plane-${pl.id}`} onClick={() => set({ plane: pl.id })}>
                <span className="preview" style={{ background: planePreview(pl) }} />
                <span className="name">{pl.name}</span>
                <span className="blurb">{pl.tagline}</span>
                <span className="dots">{pl.swatches.map((c) => <i key={c} style={{ background: c }} />)}</span>
              </button>
            ))}
          </div>
        ))}
        <div className="settings-grid">
          <label className="field">Table
            <select value={p.renderer} data-testid="renderer" onChange={(e) => set({ renderer: e.target.value as Prefs["renderer"] })}>
              <option value="auto">Auto (3D when supported)</option>
              <option value="3d">3D table</option>
              <option value="2d">2D table (lighter, for slow devices)</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={p.ambience} onChange={(e) => set({ ambience: e.target.checked })} /> Ambient sound of the plane (volume: Sound → Ambient)</label>
          <label className="field" title="Big moments: eliminations, commander casts, attacks on you, and spells or abilities aimed at you or your permanents. All moments adds the start of your turn and other players' attacks. The camera glances there and comes back; any input cancels it">3D camera on big moments
            <select value={p.autoCenter} data-testid="auto-center" onChange={(e) => set({ autoCenter: e.target.value as Prefs["autoCenter"] })}>
              <option value="off">Off (you move it)</option>
              <option value="important">Follow big moments</option>
              <option value="on">Follow all moments (also your turn and every attack)</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={p.nudges} onChange={(e) => set({ nudges: e.target.checked })} /> Let other players nudge me when the table waits on me</label>
          <label className="check"><input type="checkbox" checked={p.reactions} onChange={(e) => set({ reactions: e.target.checked })} /> Show spectators' reactions</label>
          <label className="check"><input type="checkbox" checked={p.pings} data-testid="pref-pings" onChange={(e) => set({ pings: e.target.checked })} /> Show pings from other players (G or Alt+click to ping)</label>
          <label className="check"><input type="checkbox" checked={p.turnAlert} data-testid="pref-turn-alert" onChange={(e) => set({ turnAlert: e.target.checked })} /> Flash this tab and chime when the table waits on me in the background</label>
          <label className="check" title="Colors, players, numbers, heads or tails: aim and click, or type its number and press Enter. Esc shows the usual list"><input type="checkbox" checked={p.choiceWheel} data-testid="pref-choice-wheel" onChange={(e) => set({ choiceWheel: e.target.checked })} /> Pick public choices on a quick wheel at the pointer</label>
        </div>
      </section>
      <section>
        <h2>Profile</h2>
        <div className="profile-row">
          <select value={p.active} onChange={(e) => p.switchTo(e.target.value)} aria-label="Profile">
            {p.profiles.map((x) => <option key={x.id} value={x.id}>{x.avatar} {x.name}</option>)}
          </select>
          <button className="tt-btn ghost" onClick={() => p.addProfile("New player")}>New profile</button>
          <button className="tt-btn ghost" onClick={() => {
            const blob = new Blob([p.exportProfile(profile.id)], { type: "application/json" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = `${profile.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "profile"}.json`;
            a.click();
            URL.revokeObjectURL(a.href);
          }}>Export</button>
          <input ref={file} type="file" hidden accept="application/json,.json" onChange={async (e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (!f || f.size > 256 * 1024) return;
            try {
              p.importProfile(JSON.parse(await f.text()));
              toast("Profile imported");
            } catch (err) {
              toastError(err);
            }
          }} />
          <button className="tt-btn ghost" onClick={() => file.current?.click()}>Import…</button>
          {p.profiles.length > 1 && (
            <button className="tt-btn ghost danger" onClick={() => window.confirm(`Delete profile “${profile.name}” from this browser?`) && p.removeProfile(profile.id)}>Delete</button>
          )}
        </div>
        <div className="settings-grid">
          <label className="field">Display name
            <input value={profile.name} maxLength={40} data-testid="profile-name" onChange={(e) => p.updateProfile(profile.id, { name: e.target.value })} />
          </label>
          <label className="field">Icon
            <select value={profile.avatar} onChange={(e) => p.updateProfile(profile.id, { avatar: e.target.value })}>
              {AVATARS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label className="field">Preferred sleeves
            <select value={p.preferredSleeve ?? ""} onChange={(e) => set({ preferredSleeve: e.target.value || null })}>
              <option value="">Default</option>
              {backs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label className="field">Preferred playmat
            <select value={p.preferredPlaymat ?? ""} onChange={(e) => set({ preferredPlaymat: e.target.value || null })}>
              <option value="">None</option>
              {mats.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label className="field">Preferred seat
            <select value={p.preferredSeat ?? ""} onChange={(e) => set({ preferredSeat: e.target.value || null })}>
              <option value="">Any</option>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={`p${n}`}>Seat {n}</option>)}
            </select>
          </label>
        </div>
        {stats && (
          <p className="hint profile-stats">Pod record as {stats.name}: {stats.games} games · {stats.wins} wins · {pct(stats.win_pct)} — <a href="#/stats">Pod stats</a></p>
        )}
      </section>

      <section>
        <h2>Display & accessibility</h2>
        <div className="settings-grid">
          <label className="field">UI scale {Math.round(p.uiScale * 100)}%
            <input type="range" min={0.75} max={1.6} step={0.05} value={p.uiScale} onChange={(e) => set({ uiScale: Number(e.target.value) })} />
          </label>
          <label className="field">Card preview
            <select value={p.inspectSize} onChange={(e) => set({ inspectSize: e.target.value as Prefs["inspectSize"] })}>
              <option value="normal">Normal</option><option value="large">Large</option>
            </select>
          </label>
          <label className="field">HUD
            <select value={p.hud} onChange={(e) => set({ hud: e.target.value as Prefs["hud"] })}>
              <option value="full">Full</option><option value="minimal">Minimal</option>
            </select>
          </label>
          <label className="field">Animation speed {p.animationSpeed}×
            <input type="range" min={0.5} max={2} step={0.25} value={p.animationSpeed} onChange={(e) => set({ animationSpeed: Number(e.target.value) })} />
          </label>
        </div>
        <div className="settings-checks">
          <label><input type="checkbox" checked={p.highContrast} onChange={(e) => set({ highContrast: e.target.checked })} /> High contrast</label>
          <label><input type="checkbox" checked={p.colorblindMarkers} onChange={(e) => set({ colorblindMarkers: e.target.checked })} /> Colorblind-safe seat markers (shapes)</label>
          <label><input type="checkbox" checked={p.reducedMotion} onChange={(e) => set({ reducedMotion: e.target.checked })} /> Reduce motion</label>
          <label><input type="checkbox" checked={p.showTokenSources} onChange={(e) => set({ showTokenSources: e.target.checked })} /> Show token sources</label>
          <label title="On the 3D table: let go of your cards while still moving them and they slide on, nudging your other cards aside"><input type="checkbox" checked={p.cardPhysics} onChange={(e) => set({ cardPhysics: e.target.checked })} data-testid="card-physics" /> Flick cards to slide them (3D)</label>
          <label><input type="checkbox" checked={p.snap} onChange={(e) => set({ snap: e.target.checked })} /> Snap cards when dropping</label>
        </div>
      </section>

      <section>
        <h2>Sound</h2>
        <div className="settings-checks">
          <label><input type="checkbox" checked={p.sound.muted} data-testid="mute" onChange={(e) => set({ sound: { ...p.sound, muted: e.target.checked } })} /> Mute all</label>
          <button className="tt-btn ghost" onClick={() => { play("shuffle"); setTimeout(() => play("dice"), 500); }}>Test</button>
        </div>
        <div className="settings-grid">
          {vol("master", "Master")}{vol("cards", "Cards")}{vol("dice", "Dice")}{vol("ui", "Interface")}{vol("ambient", "Ambient")}
        </div>
      </section>

      <section>
        <h2>Table & performance</h2>
        <div className="settings-grid">
          <label className="field">Graphics
            <select value={p.graphics} data-testid="graphics" onChange={(e) => {
              const g = e.target.value as Prefs["graphics"];
              set({ graphics: g, ...(g === "low" ? { tokenCollapse: 5 as const } : {}) });
            }}>
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
            </select>
            <span className="hint">{GRAPHICS_NOTES[p.graphics]}</span>
          </label>
          <label className="field">Sort my hand
            <select value={p.handSort} data-testid="pref-hand-sort" onChange={(e) => set({ handSort: e.target.value as Prefs["handSort"] })}>
              {HAND_SORTS.map((m) => <option key={m} value={m}>{HAND_SORT_LABEL[m][0]!.toUpperCase() + HAND_SORT_LABEL[m].slice(1)}</option>)}
            </select>
          </label>
          <label className="field">Collapse identical tokens above
            <select value={p.tokenCollapse} onChange={(e) => set({ tokenCollapse: Number(e.target.value) as Prefs["tokenCollapse"] })}>
              <option value={5}>5</option><option value={10}>10</option><option value={20}>20</option><option value={0}>Never</option>
            </select>
            <span className="hint">One card shows ×N; right-click it to split. With rules automation on, every token stays its own card.</span>
          </label>
          <label className="field">Favorite counters
            <input value={p.favoriteCounters.join(", ")} onChange={(e) => set({ favoriteCounters: e.target.value.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 12) })} />
          </label>
        </div>
      </section>

      <KeysSection />
      <CardDataSection />
      <BackupSection />
      <DiagnosticsSection />
    </div>
  );
}

/** A troubleshooting file saved to this computer (host only). Nothing is ever sent anywhere. */
function DiagnosticsSection() {
  const [priv, setPriv] = useState(false);
  const [host, setHost] = useState<boolean | null>(null);
  useEffect(() => {
    fetch("/api/saves").then((r) => setHost(r.ok), () => setHost(false));
  }, []);
  if (!host) return null;
  return (
    <section>
      <h2>Diagnostics</h2>
      <p className="hint">
        Saves a JSON file with versions, connection state, consistency checks and recent warnings, for when something
        goes wrong. It stays on this computer. By default it has no hands, libraries, decklists or notes.
      </p>
      <div className="row">
        <label className="check"><input type="checkbox" checked={priv} onChange={(e) => setPriv(e.target.checked)} data-testid="diag-private" />
          Include private information (full table states and decklists; LAN games still being played stay private)</label>
        <a className="tt-btn ghost" data-testid="diag-download" href={`/api/diagnostics${priv ? "?include_private=true" : ""}`} download>Download diagnostics</a>
      </div>
    </section>
  );
}

function KeysSection() {
  const keymap = usePrefs((s) => s.keymap);
  const [capturing, setCapturing] = useState<HotkeyId | null>(null);
  const table = effectiveHotkeys(keymap);
  const clashes = collisions(table);
  useEffect(() => {
    if (!capturing) return;
    const onKey = (e: KeyboardEvent) => {
      if (["Shift", "Control", "Meta", "Alt"].includes(e.key)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.key !== "Escape") usePrefs.getState().set({ keymap: { ...usePrefs.getState().keymap, [capturing]: [comboOf(e)] } });
      setCapturing(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [capturing]);
  return (
    <section>
      <h2>Keys</h2>
      <div className="row key-presets">
        {KEY_PRESETS.map((pre) => (
          <button key={pre.id} className={`tt-btn ghost ${JSON.stringify(keymap) === JSON.stringify(pre.keymap) ? "on" : ""}`}
            data-testid={`keys-${pre.id}`} onClick={() => usePrefs.getState().set({ keymap: pre.keymap })}>{pre.label}</button>
        ))}
      </div>
      {clashes.length > 0 && <p className="warn">Two actions share a key: {clashes.join("; ")}</p>}
      <table className="keys">
        <tbody>
          {table.map((h) => (
            <tr key={h.id}>
              <td>{h.label}</td>
              <td>
                <button className={`tt-btn ghost ${capturing === h.id ? "on" : ""}`} onClick={() => setCapturing(h.id)}>
                  {capturing === h.id ? "Press a key…" : h.keys.join(" / ")}
                </button>
                {keymap[h.id] && <button className="tt-icon" title="Back to default" onClick={() => {
                  const { [h.id]: _gone, ...rest } = usePrefs.getState().keymap;
                  usePrefs.getState().set({ keymap: rest });
                }}>↺</button>}
              </td>
            </tr>
          ))}
          <tr><td>Recall / save a view</td><td className="hint">Ctrl+1…9 / Ctrl+Shift+1…9</td></tr>
        </tbody>
      </table>
    </section>
  );
}

/** BACKUP FYODOR / restore (host computer only), with automatic backups like a rotating autosave. */
function BackupSection() {
  const [list, setList] = useState<BackupInfo[] | null>(null);
  const [auto, setAuto] = useState<AutoBackupStatus | null>(null);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const load = () => api.get<{ backups: BackupInfo[]; auto: AutoBackupStatus }>("/backups").then((r) => {
    setList(r.backups);
    setAuto(r.auto);
  }, (e: unknown) => {
    if (e instanceof ApiError && e.status === 403) setDenied(true);
  });
  useEffect(() => void load(), []);
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await fn();
      if (done) toast(done);
      await load();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const restore = async (fn: () => Promise<unknown>) => {
    if (!window.confirm("Restore this backup? Decks, saves, pod stats and custom assets are replaced by the backup's when Fyodor restarts. The current data is kept as a copy.")) return;
    await run(async () => {
      await fn();
      setRestartNeeded(true);
    }, "Backup staged — restart Fyodor to finish restoring");
  };
  return (
    <section id="backups" data-testid="backups">
      <h2>Backup &amp; restore</h2>
      {denied ? (
        <p className="hint">Backups are made on the host computer (the one running Fyodor).</p>
      ) : (
        <>
          {auto && (
            <div className={`autobackup ${auto.enabled ? "on" : "off"}`} data-testid="autobackup">
              <span className="autobackup-lamp" aria-hidden />
              <div>
                {auto.enabled ? (
                  <p><b>Automatic backups are on.</b> At start-up, every {auto.interval_minutes} minutes while anything changes, and right after each recorded game. Fyodor keeps the newest 8 and one a day for a week.</p>
                ) : (
                  <p><b>Automatic backups are off</b> (FYODOR_AUTO_BACKUP_MINUTES=0). Only the backups you make here are kept.</p>
                )}
                <p className="hint">
                  {auto.last ? <>Last automatic backup {whenMade(auto.last.mtime)}{auto.last.reason ? ` (${auto.last.reason})` : ""}. </> : null}
                  {auto.copy_dir ? <>Every backup is also copied to <code>{auto.copy_dir}</code>.</> : <>To keep a second copy off this computer's disk, set <code>FYODOR_BACKUP_COPY_DIR</code> to a USB stick or synced folder.</>}
                </p>
                {auto.last_error && <p className="warn">{auto.last_error}</p>}
              </div>
            </div>
          )}
          <p className="hint">A backup holds your decks, saves, live tables, pod stats, macros and custom sleeves / playmats. The card database isn't included; it is rebuilt from card data.</p>
          <div className="row">
            <button className="btn primary" disabled={busy} data-testid="backup-now"
              onClick={() => void run(async () => {
                const made = await api.post<BackupInfo>("/backups", {});
                window.location.href = `/api/backups/${encodeURIComponent(made.name)}`;
              }, "Backup saved")}>Back up Fyodor now</button>
            <button className="btn" disabled={busy} onClick={() => file.current?.click()}>Restore from a file…</button>
            <input ref={file} type="file" hidden accept=".zip,application/zip" onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void restore(() => fetch("/api/backups/restore", { method: "POST", body: f }).then(async (r) => {
                if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? "Restore failed");
              }));
            }} />
          </div>
          {restartNeeded && <p className="warn">Restart Fyodor (close the window running it and start it again) to finish restoring.</p>}
          {list && list.length > 0 && (
            <table className="backups" data-testid="backup-list">
              <tbody>
                {list.map((b) => (
                  <tr key={b.name}>
                    <td className="when" title={b.created_at.replace("T", " ")}>{whenMade(b.mtime)}</td>
                    <td><span className={`slot ${b.auto ? "auto" : "manual"}`}>{b.auto ? "Auto" : "By hand"}</span>{b.reason && <span className="hint"> {b.reason}</span>}</td>
                    <td className="hint size">{backupSize(b.size)}</td>
                    <td className="actions">
                      <a className="tt-btn ghost" href={`/api/backups/${encodeURIComponent(b.name)}`} download>Download</a>
                      <button className="tt-btn ghost" disabled={busy} onClick={() => void restore(() => api.post(`/backups/${encodeURIComponent(b.name)}/restore`, {}))}>Restore</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {list && list.length === 0 && <p className="hint">No backups yet.</p>}
        </>
      )}
    </section>
  );
}
