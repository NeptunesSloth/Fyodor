/**
 * Play: the card room's front door. On the left the table you're setting up (hot-seat at this computer, or a LAN night the
 * pod joins from their own computers), its seats showing each commander; on the right the door (join with a room code) and
 * the shelf of tables in progress and saved games, each shown with its commanders.
 */
import { activeProfile, usePrefs } from "../state/prefs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { CONFIGURABLE_RULES, MULLIGAN_RULES, MulliganEditor, draftPolicy, rememberPolicy } from "../components/MulliganEditor";
import type { AutomationLevel, MulliganPolicy } from "../types/game";
import { toast, toastError } from "../components/Toasts";
import { navigate, type Route } from "../hooks/useHashRoute";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import {
  closeGame,
  createGame,
  deleteSave,
  joinGame,
  lanInfo,
  listGames,
  listSaves,
  importPackage,
  packageUrl,
  loadSave,
  rememberSeat,
  type CreatePlayer,
} from "../services/games";
import type { DeckSummary } from "../types/decks";
import type { GameSummary, SaveSummary } from "../types/game";
import { CommanderArt } from "./CommanderArt";
import { DeckPicker } from "./DeckPicker";
import { deckTitle, shelfSaves } from "./playBits";
import { SEAT_COLORS, SeatChip, TableMosaic, chipStyle, whenSaved } from "./tableBits";

const COLORS = SEAT_COLORS;

/** The automation levels by the names the table uses (the rules HUD, the lobby's house rules). */
const AUTOMATION_NAME: Record<AutomationLevel, string> = { off: "Off", assisted: "Assisted", full: "Full" };
const AUTOMATION_HINT: Record<AutomationLevel, string> = {
  off: "Pure sandbox: nothing is enforced; you move everything by hand.",
  assisted: "The rules engine validates and prepares, and asks before important steps.",
  full: "Supported rules happen by themselves; you're asked only when Magic needs a choice.",
};

export function PlayPage({ route }: { route: Route }) {
  const [host, setHost] = useState<boolean | null>(null);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [decks, setDecks] = useState<DeckSummary[]>([]);

  const refresh = useCallback(() => {
    listGames().then(setGames, toastError);
    listSaves().then(
      (s) => {
        listDecks().then(setDecks, toastError); // the deck library lives on the host only
        setSaves(shelfSaves(s));
        setHost(true);
      },
      (e) => {
        if (e instanceof ApiError && e.status === 403) setHost(false);
        else toastError(e);
      },
    );
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  // "Resume a game" on the launcher opens the shelf
  const shelf = useRef<HTMLElement>(null);
  const wantsShelf = route.query.get("tab") === "saves";
  useEffect(() => {
    if (!wantsShelf || host === null) return;
    shelf.current?.scrollIntoView({ block: "start" });
    shelf.current?.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
  }, [wantsShelf, host]);

  return (
    <div className="page play">
      <div className="pg-grid">
        <div className="pg-main">
          {host !== false && <NewGame decks={decks} preselect={route.query.get("deck")} lanParam={route.query.get("mode") === "lan"} />}
          {host === false && (
            <section className="pg-remote" aria-labelledby="pg-remote-title">
              <Icon name="table" size={30} />
              <h1 id="pg-remote-title">You're connected to a host</h1>
              <p>Games are created on the host computer. Join one with its room code: ask the host for it, or find it among the open tables.</p>
            </section>
          )}
        </div>
        <aside className="pg-side">
          <JoinGame />
          <section className="pg-shelf" ref={shelf} aria-labelledby="pg-shelf-title">
            <h2 id="pg-shelf-title" tabIndex={-1}>Tables in progress</h2>
            {games.length === 0 ? (
              <p className="pg-empty">No tables are open. A game shows up here while it's being played.</p>
            ) : (
              <ul className="pg-tiles">
                {games.map((g) => <TableTile key={g.id} game={g} host={!!host} onClosed={refresh} />)}
              </ul>
            )}
            {host && (
              <>
                <div className="pg-shelf-head">
                  <h2>Saved games</h2>
                  <label className="tt-btn ghost pg-import" title="Import a .fyodor.zip game package from another pod computer">
                    Import package…
                    <input type="file" accept=".zip,application/zip" hidden data-testid="package-import" onChange={async (e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (!file) return;
                      try {
                        const r = await importPackage(file);
                        toast(`Imported “${r.save.name}” · ${r.assets_added} image(s), ${r.macros_added} macro(s) added`);
                        refresh();
                      } catch (err) {
                        toastError(err);
                      }
                    }} />
                  </label>
                </div>
                {saves.length === 0 ? (
                  <p className="pg-empty">Nothing saved yet. Games autosave while you play.</p>
                ) : (
                  <ul className="pg-tiles">
                    {saves.map((s) => <SaveTile key={s.id} save={s} onDeleted={refresh} />)}
                  </ul>
                )}
              </>
            )}
          </section>
          {host && <LanHint />}
        </aside>
      </div>
    </div>
  );
}

type Mode = "local" | "lan";

const MODES: { id: Mode; title: string; sub: string; icon: "swords" | "table" }[] = [
  { id: "local", title: "Hot-seat", sub: "Everyone plays here, passing the seat.", icon: "swords" },
  { id: "lan", title: "Host a LAN night", sub: "The pod joins from their own computers.", icon: "table" },
];

function NewGame({ decks, preselect, lanParam }: { decks: DeckSummary[]; preselect: string | null; lanParam: boolean }) {
  const [name, setName] = useState("Commander night");
  const [mode, setMode] = useState<Mode>(() => (window.location.hash.includes("mode=lan") ? "lan" : "local"));
  useEffect(() => {
    if (lanParam) setMode("lan");
  }, [lanParam]);
  const [password, setPassword] = useState("");
  const [first, setFirst] = useState<string>("random");
  const [life, setLife] = useState<string>("40");
  const [lobby, setLobby] = useState(true);
  const [seats, setSeats] = useState(4);
  const [privacy, setPrivacy] = useState<"private" | "commander_only" | "public">("commander_only");
  const [mulligan, setMulligan] = useState("commander_london");
  const [policy, setPolicy] = useState<MulliganPolicy | null>(null);
  const configurable = CONFIGURABLE_RULES.has(mulligan);
  const chooseRule = (rule: string) => {
    setMulligan(rule);
    setPolicy(CONFIGURABLE_RULES.has(rule) ? draftPolicy(rule) : null);
  };
  const [helper, setHelper] = useState<"off" | "simple">("simple");
  const [automation, setAutomation] = useState<AutomationLevel>("off");
  const useLobby = mode === "lan" && lobby;
  const [players, setPlayers] = useState<CreatePlayer[]>([
    { name: "Player 1", deck_id: preselect, color: COLORS[0] },
    { name: "Player 2", deck_id: null, color: COLORS[1] },
  ]);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState<number | null>(null);

  useEffect(() => {
    if (preselect) setPlayers((ps) => ps.map((p, i) => (i === 0 ? { ...p, deck_id: preselect } : p)));
  }, [preselect]);
  useEffect(() => {
    // default the second player to another deck when decks load
    setPlayers((ps) => ps.map((p, i) => (p.deck_id || !decks.length ? p : { ...p, deck_id: decks[Math.min(i, decks.length - 1)]!.id })));
  }, [decks]);

  const update = (i: number, patch: Partial<CreatePlayer>) => setPlayers((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const usedBy = useMemo(() => {
    const m = new Map<string, string[]>();
    players.forEach((p, i) => {
      if (!p.deck_id || i === picking) return;
      m.set(p.deck_id, [...(m.get(p.deck_id) ?? []), p.name.trim() || `Player ${i + 1}`]);
    });
    return m;
  }, [players, picking]);

  const start = async () => {
    setBusy(true);
    try {
      const res = await createGame({
        name: name.trim() || "Game",
        format: "commander",
        mode,
        password: mode === "lan" ? password || null : null,
        players: useLobby ? [{ name: players[0]?.name.trim() || "Host", deck_id: null }] : players.map((p) => ({ ...p, name: p.name.trim() || "Player" })),
        shuffle: true,
        lobby: useLobby,
        turn_order: "pod", // the pod's own rule is the default for game nights (Table settings can change it)
        seats,
        deck_privacy: privacy,
        mulligan_rule: mulligan,
        mulligan_policy: configurable ? policy : null,
        priority_helper: helper,
        automation,
        first_player: first === "random" ? "random" : Number(first),
        starting_life: life ? Number(life) : null,
        auto_untap: true,
      });
      if (configurable && policy) rememberPolicy(mulligan, policy);
      if (res.seat) rememberSeat(res.game.id, res.seat.token);
      navigate(`/game/${res.game.id}`);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const picked = picking !== null ? players[picking] : undefined;

  return (
    <section className="pg-new" aria-labelledby="pg-new-title">
      <h1 id="pg-new-title" className="sr-only">New game</h1>
      <div className="pg-modes" role="radiogroup" aria-label="How the pod plays" data-testid="table-mode">
        {MODES.map((m) => (
          <label key={m.id} className={`pg-mode ${mode === m.id ? "on" : ""}`}>
            <input type="radio" name="table-mode" value={m.id} checked={mode === m.id} onChange={() => setMode(m.id)} data-testid={`table-mode-${m.id}`} />
            <span className="pg-mode-icon"><Icon name={m.icon} size={26} /></span>
            <span className="pg-mode-text">
              <b>{m.title}</b>
              <span>{m.sub}</span>
            </span>
          </label>
        ))}
      </div>

      <div className="pg-table" data-mode={mode}>
        <header className="pg-head">
          <label className="pg-title" title="Rename this table">
            <span className="sr-only">Table name</span>
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} spellCheck={false} />
            <Icon name="pen" size={15} className="pg-title-pen" />
          </label>
          {mode === "lan" && (
            <div className="pg-lan-opts">
              <label className="pg-toggle">
                <span className="switch"><input type="checkbox" checked={lobby} onChange={(e) => setLobby(e.target.checked)} data-testid="use-lobby" /><span /></span>
                Players bring their own decks
              </label>
              <label className="pg-pass">
                <span>Password</span>
                <input type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} placeholder="None" autoComplete="new-password" />
              </label>
            </div>
          )}
        </header>

        {useLobby ? (
          <ul className="pg-seats lobby" aria-label="Seats">
            <li className="pg-seat host">
              <div className="pg-plate">
                <SeatChip color={COLORS[0]} text="1" />
                <label className="pg-name-field">
                  <span className="pg-name-label">Your name</span>
                  <input className="pg-name" data-testid="host-name" value={players[0]?.name ?? ""} maxLength={40} onChange={(e) => update(0, { name: e.target.value })} />
                </label>
              </div>
              <div className="pg-art empty"><span className="pg-slot"><Icon name="cards" size={26} /></span></div>
              <div className="pg-deck"><p className="pg-note">You host. You bring your deck in the lobby, like everyone else.</p></div>
            </li>
            <li className="pg-chairs">
              <ul aria-label="Open seats">
                {Array.from({ length: seats - 1 }, (_, k) => (
                  <li key={k} className="pg-chair">
                    <span className="pg-chair-seat"><Icon name="table" size={22} /><b>{k + 2}</b></span>
                    <span className="pg-chair-text"><b>Open seat</b><span>A player joins with the room code and brings a deck.</span></span>
                    {seats > 2 && (
                      <button className="tt-icon pg-remove" onClick={() => setSeats((n) => n - 1)} aria-label="Remove a seat" title="Remove a seat"><Icon name="close" size={14} /></button>
                    )}
                  </li>
                ))}
                {seats < 6 && (
                  <li className="pg-add-wrap">
                    <button className="pg-add" onClick={() => setSeats((n) => n + 1)}><Icon name="plus" size={18} />Add a seat</button>
                  </li>
                )}
              </ul>
            </li>
          </ul>
        ) : (
          <ul className="pg-seats" aria-label="Players">
            {players.map((p, i) => {
              const deck = decks.find((d) => d.id === p.deck_id);
              return (
                <li key={i} className="pg-seat" style={chipStyle(p.color)}>
                  <div className="pg-plate">
                    <label className="pg-chip pg-chip-edit" title="Player colour: click to change it">
                      <span aria-hidden>{i + 1}</span>
                      <input type="color" value={p.color} onChange={(e) => update(i, { color: e.target.value })} aria-label={`Player ${i + 1} colour`} />
                    </label>
                    <input className="pg-name" value={p.name} maxLength={40} onChange={(e) => update(i, { name: e.target.value })} aria-label={`Player ${i + 1} name`} />
                  </div>
                  <button className={`pg-art ${deck ? "" : "empty"}`} onClick={() => setPicking(i)}
                    aria-label={`Player ${i + 1} deck: ${deck ? `${deck.name}${deck.commanders.length ? `, ${deck.commanders.join(" & ")}` : ""}` : "none"}. Choose a deck`}>
                    {deck ? (deck.commanders.length && deck.cover_id ? <CommanderArt id={deck.cover_id} /> : <CommanderArt back />) : (
                      <span className="pg-slot"><Icon name="cards" size={26} /><span>Choose a deck</span></span>
                    )}
                  </button>
                  <div className="pg-deck">
                    {deck ? (
                      <>
                        <p className="pg-cmdr" title={deckTitle(deck)}>{deckTitle(deck)}</p>
                        <p className="pg-sub">{deck.commanders.length > 0 && <span className="pg-deckname">{deck.name}</span>}<ColorPips colors={deck.color_identity} /></p>
                      </>
                    ) : (
                      <p className="pg-note">{decks.length ? "No deck: an empty library." : <>No decks yet. <a href="#/decks">Import some decks</a>, or play with empty libraries.</>}</p>
                    )}
                  </div>
                  <div className="pg-seat-foot">
                    {decks.length > 0 && <button className="tt-btn" onClick={() => setPicking(i)}>{deck ? "Change deck" : "Choose deck"}</button>}
                    {players.length > 1 && (
                      <button className="tt-icon pg-remove" onClick={() => setPlayers((ps) => ps.filter((_, j) => j !== i))} aria-label="Remove player" title={`Remove ${p.name || "this player"}`}>
                        <Icon name="close" size={14} />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
            {players.length < 6 && (
              <li className="pg-add-wrap">
                <button className="pg-add" onClick={() => setPlayers((ps) => [...ps, { name: `Player ${ps.length + 1}`, deck_id: null, color: COLORS[ps.length % COLORS.length] }])}>
                  <Icon name="plus" size={18} />Add player
                </button>
              </li>
            )}
          </ul>
        )}

        {configurable && policy && <div className="pg-mull"><MulliganEditor value={policy} onChange={setPolicy} /></div>}

        <footer className="pg-rail">
          <div className="pg-rules">
            <label className="pg-rule">
              <span>Starting life</span>
              <input type="number" value={life} min={1} onChange={(e) => setLife(e.target.value)} placeholder="40" />
            </label>
            <label className="pg-rule">
              <span>Opening hands</span>
              <select value={mulligan} onChange={(e) => chooseRule(e.target.value)} data-testid="mulligan-rule">
                {MULLIGAN_RULES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="pg-rule">
              <span>Automation</span>
              <select data-testid="automation-level" value={automation} onChange={(e) => setAutomation(e.target.value as AutomationLevel)} aria-describedby="pg-auto-hint">
                {(["off", "assisted", "full"] as const).map((lv) => <option key={lv} value={lv}>{AUTOMATION_NAME[lv]}</option>)}
              </select>
            </label>
            {!useLobby && (
              <label className="pg-rule">
                <span>Who starts</span>
                <select data-testid="first-player" value={first} onChange={(e) => setFirst(e.target.value)}>
                  <option value="random">Random</option>
                  {players.map((p, i) => <option key={i} value={i}>{p.name}</option>)}
                </select>
              </label>
            )}
            {useLobby && (
              <label className="pg-rule">
                <span>Deck privacy</span>
                <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} data-testid="deck-privacy">
                  <option value="private">Private</option>
                  <option value="commander_only">Commander only</option>
                  <option value="public">Public</option>
                </select>
              </label>
            )}
            {mode === "lan" && automation === "off" && (
              <label className="pg-rule">
                <span>Response helper</span>
                <select value={helper} onChange={(e) => setHelper(e.target.value as typeof helper)}>
                  <option value="simple">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
            )}
          </div>
          <p className="pg-rail-note">
            <span id="pg-auto-hint"><b>Automation {AUTOMATION_NAME[automation]}.</b> {AUTOMATION_HINT[automation]}</span>{" "}
            {useLobby ? "The pod takes seats and brings decks in the lobby; you start the game from there."
              : mulligan === "none" ? "Libraries are shuffled; with “None” everyone draws by hand (D or double-click your library)."
              : "Libraries are shuffled and opening hands dealt automatically."}
          </p>
          <button className="pg-start" disabled={busy} onClick={() => void start()} data-testid="create-game">
            {busy ? "Setting up…" : useLobby ? "Open the table" : "Start game"}
          </button>
        </footer>
      </div>

      {picked && picking !== null && (
        <DeckPicker decks={decks} value={picked.deck_id ?? null} seat={picked.name.trim() || `Player ${picking + 1}`} usedBy={usedBy}
          onClose={() => setPicking(null)} onPick={(id) => { update(picking, { deck_id: id }); setPicking(null); }} />
      )}
    </section>
  );
}

function JoinGame() {
  // an invite link (#/play?code=ABC123) fills the room code in
  const [code, setCode] = useState(() => new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("code") ?? "");
  const [name, setName] = useState(() => activeProfile().name === "Player" ? "" : activeProfile().name);
  const [password, setPassword] = useState("");
  const join = async (spectate: boolean) => {
    try {
      const body = { code: code.trim().toUpperCase(), name: name.trim() || undefined, password: password || undefined, spectate };
      const preferred = usePrefs.getState().preferredSeat;
      // sit in the profile's preferred seat when it's free, otherwise anywhere
      const res = preferred && !spectate
        ? await joinGame({ ...body, seat: preferred }).catch(() => joinGame(body))
        : await joinGame(body);
      rememberSeat(res.game_id, res.token);
      navigate(`/game/${res.game_id}`);
    } catch (e) {
      toastError(e);
    }
  };
  const ready = code.trim().length >= 4;
  return (
    <section className="pg-door" aria-labelledby="pg-join-title">
      <h2 id="pg-join-title"><Icon name="resume" size={18} />Join with a code</h2>
      <form onSubmit={(e) => { e.preventDefault(); void join(false); }}>
        <label className="pg-code">
          <span>Room code</span>
          <input data-testid="join-code" value={code} maxLength={12} onChange={(e) => setCode(e.target.value)} placeholder="The code on the host's screen" autoComplete="off" spellCheck={false} />
        </label>
        <label className="pg-field pg-field-name">
          <span>Your name</span>
          <input data-testid="join-name" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="pg-field pg-field-pass">
          <span>Password</span>
          <input type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} placeholder="If the host set one" autoComplete="off" />
        </label>
        <div className="pg-door-acts">
          <button className="tt-btn brass" type="submit" disabled={!ready} data-testid="join-submit">Join</button>
          <button className="tt-btn" type="button" disabled={!ready} onClick={() => void join(true)}>Spectate</button>
        </div>
      </form>
    </section>
  );
}

/** A table being played right now: its commanders, how it's played, who's there. */
function TableTile({ game: g, host, onClosed }: { game: GameSummary; host: boolean; onClosed: () => void }) {
  const lan = g.mode === "lan";
  const lobby = g.phase === "lobby";
  const who = g.players.map((p) => `${p.name}${lan ? (p.connected ? "" : p.claimed ? " (away)" : " (open)") : ""}`);
  return (
    <li className="pg-tile">
      <TableMosaic seats={g.players.map((p) => ({ ...p, open: lan && !p.claimed }))} />
      <div className="pg-tile-main">
        <h3><span className="pg-tile-name">{g.name}</span></h3>
        <p className="pg-meta">
          <span>{lan ? "LAN" : "Hot-seat"}</span>
          {lan && g.code && <span>Room <b className="pg-room">{g.code}</b></span>}
          <span>{lobby ? "In the lobby" : `Turn ${g.turn}`}</span>
        </p>
        <p className="pg-who">{who.join(", ")}</p>
      </div>
      {host && (
        <div className="pg-tile-acts">
          <button className="tt-btn pg-go" onClick={() => navigate(`/game/${g.id}`)}>Open</button>
          <button className="tt-btn ghost" onClick={async () => {
            if (!window.confirm(`Close “${g.name}”? It is autosaved first and can be loaded later.`)) return;
            await closeGame(g.id).catch(toastError);
            onClosed();
          }}>Close</button>
        </div>
      )}
    </li>
  );
}

/** A saved game: its commanders and life totals, when it was saved, and how to bring it back. */
function SaveTile({ save: s, onDeleted }: { save: SaveSummary; onDeleted: () => void }) {
  const open = (id: string) => navigate(`/game/${id}`);
  return (
    <li className="pg-tile list-row">
      <TableMosaic seats={s.players} />
      <div className="pg-tile-main">
        <h3 title={s.name}><span className="pg-tile-name">{s.autosave ? s.game_name || s.name : s.name}</span>{s.autosave && <span className="pg-tag">Autosave</span>}</h3>
        <p className="pg-meta">
          <span>{whenSaved(s.created_at)}</span>
          <span>Turn {s.turn}</span>
        </p>
        <p className="pg-who">{s.players.map((p) => `${p.name} ${p.life}`).join(", ")}</p>
      </div>
      <div className="pg-tile-acts">
        <button className="tt-btn pg-go" onClick={async () => {
          try {
            const res = await loadSave(s.id);
            open(res.game.id);
          } catch (e) {
            toastError(e);
          }
        }}>Load</button>
        <span className="pg-tile-more">
          <button className="tt-btn" title="Load as a LAN game: the pod joins with a room code" aria-label={`Load “${s.name}” as a LAN game`} onClick={async () => {
            try {
              const res = await loadSave(s.id, "lan");
              if (res.seat) rememberSeat(res.game.id, res.seat.token);
              toast(`LAN room ${res.game.code} ready`);
              open(res.game.id);
            } catch (e) {
              toastError(e);
            }
          }}>Load as LAN</button>
          <a className="tt-icon" href={packageUrl(s.id)} download title="Download a portable package (save + custom images + macros)" aria-label={`Download “${s.name}” as a package`}>
            <Icon name="download" size={16} />
          </a>
          <button className="tt-icon pg-delete" aria-label={`Delete save “${s.name}”`} title="Delete this save" onClick={async () => {
            if (!window.confirm(`Delete save “${s.name}”?`)) return;
            await deleteSave(s.id).catch(toastError);
            onDeleted();
          }}><Icon name="trash" size={16} /></button>
        </span>
      </div>
    </li>
  );
}

/** How the rest of the pod reaches this computer, in one line. */
function LanHint() {
  const [info, setInfo] = useState<{ addresses: string[]; port: number; reachable: boolean } | null>(null);
  useEffect(() => {
    lanInfo().then(setInfo, () => setInfo(null));
  }, []);
  if (!info) return null;
  return (
    <p className={`pg-lan ${info.reachable ? "" : "local-only"}`}>
      <Icon name="table" size={16} />
      {info.reachable ? (
        <span>
          The pod opens{" "}
          {info.addresses.map((a) => <code key={a}>http://{a}:{info.port}</code>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " or ", el] : [el]), [])}
          {" "}on their own computers and joins with the room code.
        </span>
      ) : (
        <span>
          Only this computer can reach Fyodor right now. To let the pod join a LAN night, restart it with <code>FYODOR_HOST=0.0.0.0 scripts/serve.sh</code>.
        </span>
      )}
    </p>
  );
}
