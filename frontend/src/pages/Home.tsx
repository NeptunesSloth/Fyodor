/**
 * The launcher: a title screen. The selected plane's table fills the screen (the live 3D table, or a drawn table where 3D
 * is off or unavailable, with the pod's own commanders lying on it); the menu stands on the left: continue the last table,
 * start a game, resume, host a LAN night, and the pod's decks a click from a new game. First-run setup opens on top until
 * it is done.
 */
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { getHealth, type Health } from "../services/api";
import { listDecks } from "../services/decks";
import { listGames, listSaves, loadSave, seatToken } from "../services/games";
import { useCard } from "../state/cardCache";
import { usePrefs } from "../state/prefs";
import { plane, PLANES } from "../theme/planes";
import { resolveRenderer } from "../table3d/renderer";
import type { DeckSummary } from "../types/decks";
import type { GameSummary, SaveSummary } from "../types/game";
import { CommanderArt } from "./CommanderArt";
import { NearbyLine } from "./NearbyGames";
import { deckTitle, lastTable, type LastTable } from "./playBits";
import { TableMosaic, whenSaved } from "./tableBits";
import { Welcome, resetWelcome, welcomeDone } from "./Welcome";
import "./home.css";
import { Icon, type IconName } from "../components/Icon";

const ShowcaseView = lazy(() => import("./ShowcaseView"));

const MENU: { href: string; label: string; icon: IconName; testid: string; resume?: boolean }[] = [
  { href: "#/play", label: "Start a game", icon: "swords", testid: "menu-new" },
  { href: "#/play", label: "Resume a game", icon: "resume", testid: "menu-resume", resume: true },
  { href: "#/play?mode=lan", label: "Host a LAN night", icon: "table", testid: "menu-lan" },
];
const MINOR: { href: string; label: string; icon: IconName; testid: string }[] = [
  { href: "#/decks", label: "Deck library", icon: "cards", testid: "menu-decks" },
  { href: "#/stats", label: "Pod stats", icon: "crown", testid: "menu-stats" },
  { href: "#/settings", label: "Settings", icon: "gear", testid: "menu-settings" },
];


export function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saves, setSaves] = useState<SaveSummary[] | null>(null);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const planeId = usePrefs((s) => s.plane);
  const renderer = usePrefs((s) => s.renderer);
  const setPrefs = usePrefs((s) => s.set);
  const [showWelcome, setShowWelcome] = useState(!welcomeDone());
  useEffect(() => {
    getHealth().then(setHealth, (e: unknown) => setError(String(e)));
    listSaves().then((s) => {
      setSaves(s);
      listDecks().then(setDecks, () => undefined); // the deck library lives on the host
    }, () => undefined);
    listGames().then(setGames, () => undefined);
  }, []);
  const p = plane(planeId);
  const idx = PLANES.findIndex((x) => x.id === p.id);
  const step = (d: number) => setPrefs({ plane: PLANES[(idx + d + PLANES.length) % PLANES.length]!.id });
  const db = health?.card_database;
  const three = resolveRenderer(renderer) === "3d";
  const host = saves !== null;

  // a table this device can open: any on the host, a seat this browser holds elsewhere
  const last = useMemo(() => lastTable(games, saves, (g) => host || !!seatToken(g.id)), [games, saves, host]);
  const recent = useMemo(() => [...decks].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 4), [decks]);
  const savedCount = saves?.length ?? 0;

  return (
    <div className="home-launch">
      {three ? (
        <Suspense fallback={null}>
          <ShowcaseView planeId={p.id} />
        </Suspense>
      ) : (
        <HomeScene decks={recent} />
      )}
      <div className="home-vignette" />
      <div className="home-col">
        <header className="home-head">
          <h1 className="home-title">Fyodor</h1>
          <p className="home-sub">Commander tabletop</p>
        </header>
        {last && <Continue last={last} />}
        <nav className="home-menu" aria-label="Main menu">
          {MENU.map((m) => (
            <a key={m.testid} href={m.resume && savedCount ? "#/play?tab=saves" : m.href} className={`home-item ${m.testid === "menu-new" ? "primary" : ""}`} data-testid={m.testid}>
              <span className="home-icon"><Icon name={m.icon} size={20} /></span>
              <span className="home-label">{m.label}</span>
              {m.resume && savedCount > 0 && <span className="home-count" aria-label={`${savedCount} saved`}>{savedCount}</span>}
            </a>
          ))}
          <div className="home-minor">
            {MINOR.map((m) => (
              <a key={m.testid} href={m.href} data-testid={m.testid}><Icon name={m.icon} size={16} />{m.label}</a>
            ))}
          </div>
        </nav>
        {/* a lobby with a free seat on another computer (the host computer asks the network; never another device) */}
        <NearbyLine enabled={host} />
        {recent.length > 0 && (
          <section className="home-decks" aria-labelledby="home-decks-title">
            <h2 id="home-decks-title">Play a deck</h2>
            <ul>
              {recent.map((d) => (
                <li key={d.id}>
                  <a href={`#/play?deck=${d.id}`} title={`New game with ${d.name}`}>
                    <span className="home-art">{d.commanders.length && d.cover_id ? <CommanderArt id={d.cover_id} /> : <CommanderArt back />}</span>
                    <span className="home-deck-cmdr">{deckTitle(d)}</span>
                    {d.commanders.length > 0 && <span className="home-deck-name">{d.name}</span>}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <footer className="home-foot">
        <p className="home-status" role="status">
          {error ? (
            <span className="home-db warn"><i aria-hidden />Can't reach the Fyodor server. Is it still running?</span>
          ) : health ? (
            db?.available ? (
              <span className="home-db" title={`${db.printings.toLocaleString()} printings, ${db.images.toLocaleString()} images cached`}>
                <i aria-hidden />{db.oracle_cards.toLocaleString()} cards ready to play offline
              </span>
            ) : (
              <span className="home-db warn"><i aria-hidden />No card database yet. <a href="#/settings">Download it in Settings</a> while online.</span>
            )
          ) : (
            <span className="home-db idle"><i aria-hidden />Checking the card database…</span>
          )}
          <span className="home-version">v{health?.version ?? "…"}</span>
        </p>
        {!showWelcome && <button className="tt-link home-guide" onClick={() => { resetWelcome(); setShowWelcome(true); }}>Setup guide</button>}
      </footer>

      {(health?.recovery || health?.recovered_tables?.length) && (
        <section className="home-notice frame" data-testid="home-notice">
          {health.recovery && (
            <p className="warn">
              Fyodor's database was damaged, so it started with a fresh one (the damaged file is kept as {health.recovery.moved_to}).{" "}
              <a href="#/settings">Restore a backup</a>{health.recovery.backups.length ? ` — ${health.recovery.backups.length} available` : ""}.
            </p>
          )}
          {!!health.recovered_tables?.length && (
            <p>
              Restored after a restart:{" "}
              {health.recovered_tables.map((t, i) => (
                <span key={t.game_id}>{i > 0 && ", "}<a href={`#/game/${t.game_id}`}>{t.name}</a></span>
              ))}
              . Players reconnect to their seats automatically.
            </p>
          )}
        </section>
      )}
      <section className="home-plane" aria-label="Table theme">
        <div className="home-plane-row">
          <button className="home-arrow" onClick={() => step(-1)} aria-label="Previous table theme"><Icon name="left" size={18} /></button>
          <div>
            <div className="home-plane-label">Table</div>
            <div className="home-plane-name" data-testid="home-plane">{p.name}</div>
          </div>
          <button className="home-arrow" onClick={() => step(1)} aria-label="Next table theme"><Icon name="right" size={18} /></button>
        </div>
        <p className="home-plane-tag">{p.tagline}</p>
      </section>
      {showWelcome && (
        <div className="home-welcome">
          <Welcome health={health} onClose={() => setShowWelcome(false)} />
        </div>
      )}
    </div>
  );
}

/** One click back to the last table: open it if it's still running, or load the newest save. */
function Continue({ last }: { last: LastTable }) {
  const [busy, setBusy] = useState(false);
  const table = last.kind === "table" ? last.game : null;
  const save = last.kind === "save" ? last.save : null;
  const name = table ? table.name : save!.autosave ? save!.game_name || save!.name : save!.name;
  const seats = table ? table.players.map((p) => ({ ...p, open: table.mode === "lan" && !p.claimed })) : save!.players;
  const go = async () => {
    if (table) return navigate(`/game/${table.id}`);
    setBusy(true);
    try {
      const res = await loadSave(save!.id);
      navigate(`/game/${res.game.id}`);
    } catch (e) {
      toastError(e);
      setBusy(false);
    }
  };
  return (
    <button className="home-continue" onClick={() => void go()} disabled={busy} data-testid="home-continue"
      aria-label={`Continue “${name}”, ${table ? `${table.mode === "lan" ? "LAN" : "hot-seat"}, ${table.phase === "lobby" ? "in the lobby" : `turn ${table.turn}`}` : `saved ${whenSaved(save!.created_at)}, turn ${save!.turn}`}`}>
      <TableMosaic seats={seats} />
      <span className="home-continue-text">
        <span className="home-continue-name">{name}</span>
        <span className="home-continue-meta">
          {table ? (
            <>
              <span>{table.mode === "lan" ? "LAN" : "Hot-seat"}</span>
              <span>{table.phase === "lobby" ? "In the lobby" : `Turn ${table.turn}`}</span>
            </>
          ) : (
            <>
              <span>{whenSaved(save!.created_at)}</span>
              <span>Turn {save!.turn}</span>
            </>
          )}
        </span>
      </span>
      <span className="home-continue-go"><span className="home-continue-word">{busy ? "Loading…" : "Continue"}</span><Icon name="right" size={18} /></span>
    </button>
  );
}

/** Card positions on the drawn table's mat: a small battlefield, slightly askew, as a game left mid-turn. */
const SPOTS = [
  { x: 9, y: 30, r: -4 },
  { x: 27, y: 24, r: 2 },
  { x: 45, y: 31, r: -1.5 },
  { x: 63, y: 25, r: 3.5 },
];

/**
 * The launcher's table where the live 3D table is off or unavailable (a slow laptop, the 2D preference, no WebGL): the
 * plane's wood and baize drawn in perspective, lit from the top left, with the pod's most recent commanders lying on the
 * mat beside a library. Static: nothing moves.
 */
function HomeScene({ decks }: { decks: DeckSummary[] }) {
  const ids = decks.filter((d) => d.commanders.length && d.cover_id).map((d) => d.cover_id!);
  return (
    <div className="home-scene" aria-hidden>
      <div className="hs-table">
        <div className="hs-mat">
          {SPOTS.map((s, i) => (
            <div key={i} className="hs-card" style={{ left: `${s.x}%`, top: `${s.y}%`, ["--r" as string]: `${s.r}deg` }}>
              {ids[i] ? <SceneCard id={ids[i]!} /> : <CardFace faceDown />}
            </div>
          ))}
          <div className="hs-library">
            {Array.from({ length: 6 }, (_, i) => <div key={i} className="hs-back" style={{ ["--i" as string]: i }}><CardFace faceDown /></div>)}
          </div>
        </div>
      </div>
      <div className="hs-light" />
    </div>
  );
}

function SceneCard({ id }: { id: string }) {
  const card = useCard(id);
  return <CardFace card={card} size="normal" />;
}
