import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { toast, toastError } from "../components/Toasts";
import { api, ApiError } from "../services/api";
import { effectiveHotkeys, collisions, comboOf, KEY_PRESETS, type HotkeyId } from "../game/hotkeys";
import { play } from "../game/sound";
import { DICE_LOOKS } from "../game/dice";
import { listAssets, type Asset } from "../services/assets";
import { backupSize, whenMade, type AutoBackupStatus, type BackupInfo } from "../services/backups";
import { CardDataSection } from "./CardDataPanel";
import { HAND_SORTS, HAND_SORT_LABEL } from "../game/handSort";
import { pct, podPlayer, podPlayers, type PodPlayerDetail } from "../services/pod";
import { GRAPHICS_NOTES } from "../state/applyPrefs";
import { usePrefs, type Prefs } from "../state/prefs";
import { PLANES, type PlaneTheme } from "../theme/planes";
import { activeSection, keyCaps, keyWords, settingsSections } from "./settingsBits";
import { SettingsSection } from "./SettingsSection";
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
 * One setting: its name and a short line on what it does, the control on the right (under it on a phone).
 * The control gets the row's id (its label) and the hint's id (its description).
 */
function Row({ title, hint, control, className }: {
  title: ReactNode; hint?: ReactNode; className?: string;
  control: (id: string, hintId: string | undefined) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={`st-row ${className ?? ""}`}>
      <div className="st-text">
        <label htmlFor={id}>{title}</label>
        {hint && <p id={hintId}>{hint}</p>}
      </div>
      <div className="st-ctl">{control(id, hintId)}</div>
    </div>
  );
}

/** An on/off setting: a checkbox drawn as a brass switch (screen readers hear a switch). */
function Switch({ id, hintId, checked, onChange, testId }: { id: string; hintId?: string | undefined; checked: boolean; onChange: (on: boolean) => void; testId?: string | undefined }) {
  return (
    <span className="st-switch">
      <input id={id} type="checkbox" role="switch" checked={checked} aria-describedby={hintId} data-testid={testId}
        onChange={(e) => onChange(e.target.checked)} />
      <i aria-hidden />
    </span>
  );
}

function ToggleRow({ title, hint, checked, onChange, testId }: { title: ReactNode; hint?: ReactNode; checked: boolean; onChange: (on: boolean) => void; testId?: string }) {
  return <Row className="st-toggle" title={title} hint={hint} control={(id, hintId) => <Switch id={id} hintId={hintId} checked={checked} onChange={onChange} testId={testId} />} />;
}

/** The side index on wide screens: every section, the one being read marked. */
function SectionIndex({ ids, titles }: { ids: string[]; titles: Record<string, string> }) {
  const [active, setActive] = useState(ids[0] ?? "");
  const key = ids.join(" ");
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const order = key.split(" ");
    const visible = new Set<string>();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) visible.add(e.target.id);
        else visible.delete(e.target.id);
      }
      setActive((cur) => activeSection(order, visible, cur));
    }, { rootMargin: "-12% 0px -62% 0px" });
    for (const id of order) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [key]);
  const go = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const still = document.body.classList.contains("reduced-motion") || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    setActive(id);
  };
  return (
    <nav className="st-index" aria-label="Settings sections">
      <ul>
        {ids.map((id) => (
          <li key={id}>
            <button type="button" className={active === id ? "on" : ""} aria-current={active === id ? "true" : undefined} onClick={() => go(id)}>
              {titles[id]}
            </button>
          </li>
        ))}
      </ul>
      <p className="st-index-note">Your settings are saved in this browser as you change them.</p>
    </nav>
  );
}

/**
 * Settings: the table theme, the table and sound, alerts, the local profile (no account), display & accessibility, keys,
 * and the host's card database, backups and diagnostics. Player settings are stored in this browser only.
 */
export function SettingsPanel() {
  const p = usePrefs();
  const profile = p.profiles.find((x) => x.id === p.active)!;
  const [stats, setStats] = useState<PodPlayerDetail | null>(null);
  const [backs, setBacks] = useState<Asset[]>([]);
  const [mats, setMats] = useState<Asset[]>([]);
  const [host, setHost] = useState<boolean | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const iconId = useId();
  useEffect(() => {
    listAssets("card_back").then(setBacks, () => undefined);
    listAssets("playmat").then(setMats, () => undefined);
    fetch("/api/saves").then((r) => setHost(r.ok), () => setHost(false));
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
    <Row className="st-range" title={label} control={(id) => (
      <>
        <input id={id} type="range" min={0} max={1} step={0.05} value={Number(p.sound[k])}
          onChange={(e) => set({ sound: { ...p.sound, [k]: Number(e.target.value) } })} />
        <output htmlFor={id}>{Math.round(Number(p.sound[k]) * 100)}%</output>
      </>
    )} />
  );
  const sections = settingsSections(host === true);
  const sleeve = backs.find((a) => a.id === p.preferredSleeve);
  const mat = mats.find((a) => a.id === p.preferredPlaymat);

  return (
    <div className="settings" data-testid="settings">
      <div className="st-layout">
        <SectionIndex ids={sections.map((s) => s.id)} titles={Object.fromEntries(sections.map((s) => [s.id, s.title]))} />
        <div className="st-sections">
          <SettingsSection id="st-theme" className="st-theme">
            {[1, 2].map((wave) => (
              <div key={wave} className="theme-grid">
                {PLANES.filter((pl) => pl.wave === wave).map((pl) => (
                  <button key={pl.id} type="button" className={`theme-tile ${p.plane === pl.id ? "on" : ""}`} aria-pressed={p.plane === pl.id}
                    data-testid={`plane-${pl.id}`} onClick={() => set({ plane: pl.id })}>
                    <span className="preview" style={{ background: planePreview(pl) }} />
                    <span className="name">{pl.name}</span>
                    <span className="blurb">{pl.tagline}</span>
                    <span className="dots">{pl.swatches.map((c) => <i key={c} style={{ background: c }} />)}</span>
                  </button>
                ))}
              </div>
            ))}
          </SettingsSection>

          <SettingsSection id="st-table">
            <div className="st-plate">
              <Row title="Table" hint="Auto draws the 3D table when this computer supports it. The 2D table is lighter for slow devices."
                control={(id, hintId) => (
                  <select id={id} aria-describedby={hintId} value={p.renderer} data-testid="renderer" onChange={(e) => set({ renderer: e.target.value as Prefs["renderer"] })}>
                    <option value="auto">Auto (3D when supported)</option>
                    <option value="3d">3D table</option>
                    <option value="2d">2D table (lighter, for slow devices)</option>
                  </select>
                )} />
              <Row title="Board layout (2D table)" hint="Arranged: each board sorts itself into rows on your screen, creatures in front, lands at the back, identical cards stacked. Free placement: cards stay where they were put, as on the 3D table."
                control={(id, hintId) => (
                  <select id={id} aria-describedby={hintId} value={p.boardLayout} data-testid="board-layout" onChange={(e) => set({ boardLayout: e.target.value as Prefs["boardLayout"] })}>
                    <option value="arranged">Arranged</option>
                    <option value="free">Free placement</option>
                  </select>
                )} />
              <Row title="Graphics" hint={GRAPHICS_NOTES[p.graphics]} control={(id, hintId) => (
                <select id={id} aria-describedby={hintId} value={p.graphics} data-testid="graphics" onChange={(e) => {
                  const g = e.target.value as Prefs["graphics"];
                  set({ graphics: g, ...(g === "low" ? { tokenCollapse: 5 as const } : {}) });
                }}>
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                </select>
              )} />
              <Row title="3D camera on big moments"
                hint="Big moments: eliminations, commander casts, attacks on you, and spells or abilities aimed at you or your permanents. All moments adds the start of your turn and other players' attacks. The camera glances there and comes back; any input cancels it."
                control={(id, hintId) => (
                  <select id={id} aria-describedby={hintId} value={p.autoCenter} data-testid="auto-center" onChange={(e) => set({ autoCenter: e.target.value as Prefs["autoCenter"] })}>
                    <option value="off">Off (you move it)</option>
                    <option value="important">Follow big moments</option>
                    <option value="on">Follow all moments (also your turn and every attack)</option>
                  </select>
                )} />
              <Row title="Dice" hint="What thrown dice are made of on this screen. Every player's dice keep their seat colour."
                control={(id, hintId) => (
                  <select id={id} aria-describedby={hintId} value={p.diceLook} data-testid="dice-look" onChange={(e) => set({ diceLook: e.target.value as Prefs["diceLook"] })}>
                    {DICE_LOOKS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                  </select>
                )} />
              <ToggleRow title="Flick cards to slide them (3D)" hint="Let go of your cards while still moving them and they slide on, nudging your other cards aside."
                checked={p.cardPhysics} onChange={(v) => set({ cardPhysics: v })} testId="card-physics" />
            </div>
          </SettingsSection>

          <SettingsSection id="st-hand">
            <div className="st-plate">
              <Row title="Sort my hand" hint="On your screen only: nobody else sees your hand's order." control={(id, hintId) => (
                <select id={id} aria-describedby={hintId} value={p.handSort} data-testid="pref-hand-sort" onChange={(e) => set({ handSort: e.target.value as Prefs["handSort"] })}>
                  {HAND_SORTS.map((m) => <option key={m} value={m}>{HAND_SORT_LABEL[m][0]!.toUpperCase() + HAND_SORT_LABEL[m].slice(1)}</option>)}
                </select>
              )} />
              <Row title="Collapse identical tokens above" hint="One card shows ×N; right-click it to split. With rules automation on, every token stays its own card."
                control={(id, hintId) => (
                  <select id={id} aria-describedby={hintId} value={p.tokenCollapse} onChange={(e) => set({ tokenCollapse: Number(e.target.value) as Prefs["tokenCollapse"] })}>
                    <option value={5}>5</option><option value={10}>10</option><option value={20}>20</option><option value={0}>Never</option>
                  </select>
                )} />
              <ToggleRow title="Show token sources" hint="Each token names the card that made it." checked={p.showTokenSources} onChange={(v) => set({ showTokenSources: v })} />
              <ToggleRow title="Snap cards when dropping" checked={p.snap} onChange={(v) => set({ snap: v })} />
              <ToggleRow title="Pick public choices on a quick wheel" hint="Colours, players, numbers, heads or tails: aim and click at the pointer, or type its number and press Enter. Esc shows the usual list."
                checked={p.choiceWheel} onChange={(v) => set({ choiceWheel: v })} testId="pref-choice-wheel" />
              <Row title="Favourite counters" hint="Offered first when you add a counter. Separate them with commas." control={(id, hintId) => (
                <input id={id} aria-describedby={hintId} value={p.favoriteCounters.join(", ")}
                  onChange={(e) => set({ favoriteCounters: e.target.value.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 12) })} />
              )} />
            </div>
          </SettingsSection>

          <SettingsSection id="st-sound">
            <div className="st-plate">
              <ToggleRow title="Mute all" checked={p.sound.muted} onChange={(v) => set({ sound: { ...p.sound, muted: v } })} testId="mute" />
              <div className={`st-volumes ${p.sound.muted ? "muted" : ""}`}>
                {vol("master", "Master")}{vol("cards", "Cards")}{vol("dice", "Dice")}{vol("ui", "Interface")}{vol("ambient", "Ambient")}
              </div>
              <ToggleRow title="Ambient sound of the plane" hint="The table theme's room sound. Its volume is Ambient, above." checked={p.ambience} onChange={(v) => set({ ambience: v })} />
              <div className="st-foot">
                <button type="button" className="tt-btn" onClick={() => { play("shuffle"); setTimeout(() => play("dice"), 500); }}>Test sound</button>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection id="st-alerts">
            <div className="st-plate">
              <ToggleRow title="Let other players nudge me" hint="When the table waits on you, the others can give you a nudge." checked={p.nudges} onChange={(v) => set({ nudges: v })} />
              <ToggleRow title="Show pings from other players" hint="A ping points at something for everyone: G, or Alt+click." checked={p.pings} onChange={(v) => set({ pings: v })} testId="pref-pings" />
              <ToggleRow title="Flash this tab and chime" hint="When the table waits on you while Fyodor is in a background tab." checked={p.turnAlert} onChange={(v) => set({ turnAlert: v })} testId="pref-turn-alert" />
              <ToggleRow title="Show spectators' reactions" hint="Reactions from people watching the table and players who are out." checked={p.reactions} onChange={(v) => set({ reactions: v })} />
            </div>
          </SettingsSection>

          <SettingsSection id="st-profile">
            <div className="st-plate st-profile">
              <div className="st-player">
                <span className="st-avatar" aria-hidden>{profile.avatar}</span>
                <div className="st-player-main">
                  <label className="st-name">
                    <span>Display name</span>
                    <input value={profile.name} maxLength={40} data-testid="profile-name" onChange={(e) => p.updateProfile(profile.id, { name: e.target.value })} />
                  </label>
                  {stats && (
                    <p className="st-record">
                      <span>Pod record as {stats.name}</span>
                      <span>{stats.games} games</span>
                      <span>{stats.wins} wins</span>
                      <span>{pct(stats.win_pct)}</span>
                      <a href="#/stats">Pod stats</a>
                    </p>
                  )}
                </div>
                <label className="st-switcher">
                  <span>Profile on this browser</span>
                  <select value={p.active} onChange={(e) => p.switchTo(e.target.value)} aria-label="Profile">
                    {p.profiles.map((x) => <option key={x.id} value={x.id}>{x.avatar} {x.name}</option>)}
                  </select>
                </label>
              </div>
              <div className="st-row st-icons">
                <div className="st-text"><span id={iconId} className="st-label">Icon</span></div>
                <div className="st-ctl" role="radiogroup" aria-labelledby={iconId}>
                  {AVATARS.map((a) => (
                    <label key={a} className={profile.avatar === a ? "on" : ""}>
                      <input type="radio" name={`avatar-${profile.id}`} value={a} checked={profile.avatar === a}
                        onChange={() => p.updateProfile(profile.id, { avatar: a })} />
                      <span>{a}</span>
                    </label>
                  ))}
                </div>
              </div>
              <Row title="Preferred sleeves" hint="Your card backs at a new table. Add your own in Assets." control={(id, hintId) => (
                <>
                  {sleeve && <span className="st-thumb back" style={{ backgroundImage: `url("${sleeve.url}")` }} aria-hidden />}
                  <select id={id} aria-describedby={hintId} value={p.preferredSleeve ?? ""} onChange={(e) => set({ preferredSleeve: e.target.value || null })}>
                    <option value="">Default</option>
                    {backs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </>
              )} />
              <Row title="Preferred playmat" hint="Lies under your battlefield at a new table." control={(id, hintId) => (
                <>
                  {mat && <span className="st-thumb mat" style={{ backgroundImage: `url("${mat.url}")` }} aria-hidden />}
                  <select id={id} aria-describedby={hintId} value={p.preferredPlaymat ?? ""} onChange={(e) => set({ preferredPlaymat: e.target.value || null })}>
                    <option value="">None</option>
                    {mats.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </>
              )} />
              <Row title="Preferred seat" control={(id) => (
                <select id={id} value={p.preferredSeat ?? ""} onChange={(e) => set({ preferredSeat: e.target.value || null })}>
                  <option value="">Any</option>
                  {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={`p${n}`}>Seat {n}</option>)}
                </select>
              )} />
              <div className="st-foot st-profile-acts">
                <button type="button" className="tt-btn" onClick={() => p.addProfile("New player")}>New profile</button>
                <button type="button" className="tt-btn ghost" onClick={() => {
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
                <button type="button" className="tt-btn ghost" onClick={() => file.current?.click()}>Import…</button>
                {p.profiles.length > 1 && (
                  <button type="button" className="tt-btn ghost st-danger" onClick={() => window.confirm(`Delete profile “${profile.name}” from this browser?`) && p.removeProfile(profile.id)}>Delete</button>
                )}
              </div>
            </div>
          </SettingsSection>

          <SettingsSection id="st-display">
            <div className="st-plate">
              <Row className="st-range" title="UI scale" control={(id) => (
                <>
                  <input id={id} type="range" min={0.75} max={1.6} step={0.05} value={p.uiScale} onChange={(e) => set({ uiScale: Number(e.target.value) })} />
                  <output htmlFor={id}>{Math.round(p.uiScale * 100)}%</output>
                </>
              )} />
              <Row className="st-range" title="Animation speed" control={(id) => (
                <>
                  <input id={id} type="range" min={0.5} max={2} step={0.25} value={p.animationSpeed} onChange={(e) => set({ animationSpeed: Number(e.target.value) })} />
                  <output htmlFor={id}>{p.animationSpeed}×</output>
                </>
              )} />
              <Row title="Card preview" hint="The big card shown when you inspect one." control={(id, hintId) => (
                <select id={id} aria-describedby={hintId} value={p.inspectSize} onChange={(e) => set({ inspectSize: e.target.value as Prefs["inspectSize"] })}>
                  <option value="normal">Normal</option><option value="large">Large</option>
                </select>
              )} />
              <Row title="HUD" hint="The player counters and tools around the table." control={(id, hintId) => (
                <select id={id} aria-describedby={hintId} value={p.hud} onChange={(e) => set({ hud: e.target.value as Prefs["hud"] })}>
                  <option value="full">Full</option><option value="minimal">Minimal</option>
                </select>
              )} />
              <ToggleRow title="High contrast" hint="Brighter text and edges." checked={p.highContrast} onChange={(v) => set({ highContrast: v })} />
              <ToggleRow title="Colorblind-safe seat markers" hint="Each seat colour also gets a shape." checked={p.colorblindMarkers} onChange={(v) => set({ colorblindMarkers: v })} />
              <ToggleRow title="Reduce motion" hint="Cards and panels change place without animating." checked={p.reducedMotion} onChange={(v) => set({ reducedMotion: v })} />
            </div>
          </SettingsSection>

          <KeysSection />
          <CardDataSection />
          <BackupSection />
          {host && <DiagnosticsSection />}
        </div>
      </div>
    </div>
  );
}

/** A troubleshooting file saved to this computer (host only). Nothing is ever sent anywhere. */
function DiagnosticsSection() {
  const [priv, setPriv] = useState(false);
  return (
    <SettingsSection id="st-diag">
      <div className="st-plate">
        <p className="st-note">
          Versions, connection state, consistency checks and recent warnings, in a JSON file that stays on this computer.
          By default it has no hands, libraries, decklists or notes.
        </p>
        <ToggleRow title="Include private information" hint="Full table states and decklists. LAN games still being played stay private."
          checked={priv} onChange={setPriv} testId="diag-private" />
        <div className="st-foot">
          <a className="tt-btn" data-testid="diag-download" href={`/api/diagnostics${priv ? "?include_private=true" : ""}`} download>Download diagnostics</a>
        </div>
      </div>
    </SettingsSection>
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
    <SettingsSection id="st-keys">
      <div className="st-presets" role="group" aria-label="Key presets">
        {KEY_PRESETS.map((pre) => {
          const on = JSON.stringify(keymap) === JSON.stringify(pre.keymap);
          return (
            <button key={pre.id} type="button" className={on ? "on" : ""} aria-pressed={on}
              data-testid={`keys-${pre.id}`} onClick={() => usePrefs.getState().set({ keymap: pre.keymap })}>{pre.label}</button>
          );
        })}
      </div>
      {clashes.length > 0 && <p className="warn st-clash">Two actions share a key: {clashes.join("; ")}</p>}
      <ul className="st-keys">
        {table.map((h) => (
          <li key={h.id} className={capturing === h.id ? "capturing" : ""}>
            <span className="st-key-label">{h.label}</span>
            <span className="st-key-ctl">
              <button type="button" className="st-keycaps" onClick={() => setCapturing(h.id)}
                aria-label={capturing === h.id ? `${h.label}: press a key` : `${h.label}: ${h.keys.map(keyWords).join(" or ")}. Change`}>
                {capturing === h.id ? "Press a key…" : h.keys.map((k, i) => (
                  <span key={i} className="st-combo">{keyCaps(k).map((c, j) => <kbd key={j}>{c}</kbd>)}</span>
                ))}
              </button>
              {keymap[h.id] && <button type="button" className="tt-icon" title="Back to default" aria-label={`${h.label}: back to the default key`} onClick={() => {
                const { [h.id]: _gone, ...rest } = usePrefs.getState().keymap;
                usePrefs.getState().set({ keymap: rest });
              }}>↺</button>}
            </span>
          </li>
        ))}
        <li>
          <span className="st-key-label">Recall / save a view</span>
          <span className="st-key-ctl st-key-static">
            <span className="st-combo"><kbd>Ctrl</kbd><kbd>1…9</kbd></span>
            <span className="st-combo"><kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>1…9</kbd></span>
          </span>
        </li>
      </ul>
    </SettingsSection>
  );
}

const BACKUPS_SHOWN = 4;

/** BACKUP FYODOR / restore (host computer only), with automatic backups like a rotating autosave. */
function BackupSection() {
  const [list, setList] = useState<BackupInfo[] | null>(null);
  const [auto, setAuto] = useState<AutoBackupStatus | null>(null);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [all, setAll] = useState(false);
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
  const shown = list ? (all ? list : list.slice(0, BACKUPS_SHOWN)) : [];
  return (
    <SettingsSection id="backups" testId="backups">
      {denied ? (
        <p className="st-note st-away">Backups are made on the host computer (the one running Fyodor).</p>
      ) : (
        <div className="st-plate">
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
          <div className="st-backup-acts">
            <button className="tt-btn brass" disabled={busy} data-testid="backup-now"
              onClick={() => void run(async () => {
                const made = await api.post<BackupInfo>("/backups", {});
                window.location.href = `/api/backups/${encodeURIComponent(made.name)}`;
              }, "Backup saved")}>Back up Fyodor now</button>
            <button className="tt-btn" disabled={busy} onClick={() => file.current?.click()}>Restore from a file…</button>
            <input ref={file} type="file" hidden accept=".zip,application/zip" onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void restore(() => fetch("/api/backups/restore", { method: "POST", body: f }).then(async (r) => {
                if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? "Restore failed");
              }));
            }} />
            <span className="st-note">The card database isn't in a backup; it is rebuilt from card data.</span>
          </div>
          {restartNeeded && <p className="warn st-restart">Restart Fyodor (close the window running it and start it again) to finish restoring.</p>}
          {list && list.length > 0 && (
            <>
              <table className="backups" data-testid="backup-list">
                <tbody>
                  {shown.map((b) => (
                    <tr key={b.name}>
                      <td className="when" title={b.created_at.replace("T", " ")}>{whenMade(b.mtime)}</td>
                      <td className="what"><span className={`slot ${b.auto ? "auto" : "manual"}`}>{b.auto ? "Auto" : "By hand"}</span>{b.reason && <span className="hint"> {b.reason}</span>}</td>
                      <td className="hint size">{backupSize(b.size)}</td>
                      <td className="actions">
                        <a className="tt-btn ghost" href={`/api/backups/${encodeURIComponent(b.name)}`} download>Download</a>
                        <button className="tt-btn ghost" disabled={busy} onClick={() => void restore(() => api.post(`/backups/${encodeURIComponent(b.name)}/restore`, {}))}>Restore</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {list.length > BACKUPS_SHOWN && (
                <button type="button" className="tt-link st-more" aria-expanded={all} onClick={() => setAll(!all)}>
                  {all ? "Show the newest only" : `Show all ${list.length} backups`}
                </button>
              )}
            </>
          )}
          {list && list.length === 0 && <p className="st-note">No backups yet.</p>}
        </div>
      )}
    </SettingsSection>
  );
}
