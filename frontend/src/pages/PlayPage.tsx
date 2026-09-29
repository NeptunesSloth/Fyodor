import { activeProfile, usePrefs } from "../state/prefs";
import { useCallback, useEffect, useState } from "react";
import { ColorPips } from "../components/ColorPips";
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

const COLORS = ["#d4a852", "#5fa8d3", "#c9677a", "#6fbf8f", "#a68bd6", "#d98c4a"];

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
        // Show manual saves plus only the newest autosave of each game.
        const seen = new Set<string>();
        setSaves(s.filter((x) => !x.autosave || (!seen.has(x.game_id) && seen.add(x.game_id))));
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

  const open = (id: string) => navigate(`/game/${id}`);

  return (
    <div className="page play">
      <div className="play-grid">
        <div className="play-col">
          {host !== false && <NewGame decks={decks} preselect={route.query.get("deck")} />}
          {host === false && (
            <section className="panel">
              <h2>You're connected to a host</h2>
              <p className="hint">Games are created on the host computer. Join one with its room code.</p>
            </section>
          )}
        </div>
        <div className="play-col">
          <JoinGame />
          <section className="panel">
            <h2>Tables in progress</h2>
            {games.length === 0 && <p className="hint">No games running.</p>}
            {games.map((g) => (
              <div key={g.id} className="list-row">
                <div className="grow">
                  <b>{g.name}</b> <span className="hint">· {g.mode === "lan" ? `LAN · room ${g.code}` : "hot-seat"} · turn {g.turn}</span>
                  <div className="hint">{g.players.map((p) => `${p.name}${g.mode === "lan" ? (p.connected ? " ●" : p.claimed ? " ○" : " (open)") : ""}`).join(" · ")}</div>
                </div>
                {host && <button className="btn small primary" onClick={() => open(g.id)}>Open</button>}
                {host && (
                  <button className="btn small" onClick={async () => {
                    if (!window.confirm(`Close “${g.name}”? It is autosaved first and can be loaded later.`)) return;
                    await closeGame(g.id).catch(toastError);
                    refresh();
                  }}>Close</button>
                )}
              </div>
            ))}
          </section>
          {host && (
            <section className="panel">
              <div className="panel-head">
                <h2>Saved games</h2>
                <label className="btn small" title="Import a .fyodor.zip game package from another pod computer">
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
              {saves.length === 0 && <p className="hint">Nothing saved yet. Games autosave while you play.</p>}
              {saves.map((s) => (
                <div key={s.id} className="list-row">
                  <div className="grow">
                    <b>{s.name}</b> {s.autosave && <span className="chip">autosave</span>}
                    <div className="hint">
                      {s.created_at.replace("T", " ")} · turn {s.turn} · {s.players.map((p) => `${p.name} ${p.life}`).join(" · ")}
                    </div>
                  </div>
                  <button className="btn small primary" onClick={async () => {
                    try {
                      const res = await loadSave(s.id);
                      open(res.game.id);
                    } catch (e) {
                      toastError(e);
                    }
                  }}>Load</button>
                  <button className="btn small" title="Load as a LAN game" onClick={async () => {
                    try {
                      const res = await loadSave(s.id, "lan");
                      if (res.seat) rememberSeat(res.game.id, res.seat.token);
                      toast(`LAN room ${res.game.code} ready`);
                      open(res.game.id);
                    } catch (e) {
                      toastError(e);
                    }
                  }}>LAN</button>
                  <a className="btn small" href={packageUrl(s.id)} download title="Download a portable package (save + custom images + macros)">⇩</a>
                  <button className="btn small danger" onClick={async () => {
                    if (!window.confirm(`Delete save “${s.name}”?`)) return;
                    await deleteSave(s.id).catch(toastError);
                    refresh();
                  }}>✕</button>
                </div>
              ))}
            </section>
          )}
          {host && <LanPanel />}
        </div>
      </div>
    </div>
  );
}

function NewGame({ decks, preselect }: { decks: DeckSummary[]; preselect: string | null }) {
  const [name, setName] = useState("Commander night");
  const [format, setFormat] = useState<"commander" | "constructed" | "sandbox">("commander");
  const [mode, setMode] = useState<"local" | "lan">("local");
  const [password, setPassword] = useState("");
  const [first, setFirst] = useState<string>("random");
  const [life, setLife] = useState<string>("");
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

  useEffect(() => {
    if (preselect) setPlayers((ps) => ps.map((p, i) => (i === 0 ? { ...p, deck_id: preselect } : p)));
  }, [preselect]);
  useEffect(() => {
    // default the second player to another deck when decks load
    setPlayers((ps) => ps.map((p, i) => (p.deck_id || !decks.length ? p : { ...p, deck_id: decks[Math.min(i, decks.length - 1)]!.id })));
  }, [decks]);

  const update = (i: number, patch: Partial<CreatePlayer>) => setPlayers((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));

  const start = async () => {
    setBusy(true);
    try {
      const res = await createGame({
        name: name.trim() || "Game",
        format,
        mode,
        password: mode === "lan" ? password || null : null,
        players: useLobby ? [{ name: players[0]?.name.trim() || "Host", deck_id: null }] : players.map((p) => ({ ...p, name: p.name.trim() || "Player" })),
        shuffle: true,
        lobby: useLobby,
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

  return (
    <section className="panel new-game">
      <h2>New game</h2>
      <div className="row wrap">
        <label className="field grow">Table name<input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">
          Format
          <select value={format} onChange={(e) => setFormat(e.target.value as typeof format)}>
            <option value="commander">Commander (40 life)</option>
            <option value="constructed">Constructed (20 life)</option>
            <option value="sandbox">Sandbox</option>
          </select>
        </label>
        <label className="field">
          Starting life
          <input type="number" placeholder={format === "commander" ? "40" : "20"} value={life} min={1} onChange={(e) => setLife(e.target.value)} style={{ width: 90 }} />
        </label>
        <label className="field" title={AUTOMATION_HINT[automation]}>
          Automation
          <select data-testid="automation-level" value={automation} onChange={(e) => setAutomation(e.target.value as AutomationLevel)}>
            <option value="off">Off (sandbox)</option>
            <option value="assisted">Assisted</option>
            <option value="full">Full</option>
          </select>
        </label>
      </div>
      {useLobby ? (
        <div className="row wrap">
          <label className="field grow">Your name<input data-testid="host-name" value={players[0]?.name ?? ""} maxLength={40} onChange={(e) => update(0, { name: e.target.value })} /></label>
          <label className="field">Seats
            <select value={seats} onChange={(e) => setSeats(Number(e.target.value))}>
              {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="field">Deck privacy
            <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} data-testid="deck-privacy">
              <option value="private">Private</option>
              <option value="commander_only">Commander only</option>
              <option value="public">Public</option>
            </select>
          </label>
          <label className="field">Response helper
            <select value={helper} onChange={(e) => setHelper(e.target.value as typeof helper)}>
              <option value="simple">On</option>
              <option value="off">Off</option>
            </select>
          </label>
        </div>
      ) : (
      <div className="players-setup">
        {players.map((p, i) => {
          const deck = decks.find((d) => d.id === p.deck_id);
          return (
            <div key={i} className="player-setup" style={{ ["--player-color" as string]: p.color }}>
              <input type="color" value={p.color} onChange={(e) => update(i, { color: e.target.value })} title="Player color" />
              <input className="grow" value={p.name} maxLength={40} onChange={(e) => update(i, { name: e.target.value })} />
              <select value={p.deck_id ?? ""} onChange={(e) => update(i, { deck_id: e.target.value || null })}>
                <option value="">— no deck —</option>
                {decks.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}{d.commanders.length ? ` (${d.commanders.join(" & ")})` : ""}</option>
                ))}
              </select>
              {deck && <ColorPips colors={deck.color_identity} />}
              {players.length > 1 && <button className="icon-btn" onClick={() => setPlayers((ps) => ps.filter((_, j) => j !== i))} aria-label="Remove player">✕</button>}
            </div>
          );
        })}
        {players.length < 6 && (
          <button className="btn small" onClick={() => setPlayers((ps) => [...ps, { name: `Player ${ps.length + 1}`, deck_id: null, color: COLORS[ps.length % COLORS.length] }])}>
            + Add player
          </button>
        )}
      </div>
      )}
      <div className="row wrap">
        <label className="field">Opening hands
          <select value={mulligan} onChange={(e) => chooseRule(e.target.value)} data-testid="mulligan-rule">
            {MULLIGAN_RULES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        {!useLobby && (
        <label className="field">
          Who starts
          <select data-testid="first-player" value={first} onChange={(e) => setFirst(e.target.value)}>
            <option value="random">Random</option>
            {players.map((p, i) => <option key={i} value={i}>{p.name}</option>)}
          </select>
        </label>
        )}
        <label className="field">
          Table
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} data-testid="table-mode">
            <option value="local">Hot-seat on this computer</option>
            <option value="lan">LAN — others join with a room code</option>
          </select>
        </label>
        {mode === "lan" && (
          <label className="field row-check">
            <span><input type="checkbox" checked={lobby} onChange={(e) => setLobby(e.target.checked)} data-testid="use-lobby" /> Players choose their own decks</span>
          </label>
        )}
        {mode === "lan" && (
          <label className="field">Password (optional)<input type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} /></label>
        )}
      </div>
      {configurable && policy && <MulliganEditor value={policy} onChange={setPolicy} />}
      {decks.length === 0 && <p className="warn">No decks yet — <a href="#/decks">import some decks</a> first (or play with empty libraries).</p>}
      <button className="btn primary big" disabled={busy} onClick={() => void start()} data-testid="create-game">
        {busy ? "Setting up…" : useLobby ? "Open the table" : "Start game"}
      </button>
      <p className="hint">Libraries are shuffled and opening hands dealt automatically. With “None”, draw by hand (D or double-click your library).</p>
    </section>
  );
}

function JoinGame() {
  const [code, setCode] = useState("");
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
  return (
    <section className="panel">
      <h2>Join a LAN game</h2>
      <form className="row wrap" onSubmit={(e) => { e.preventDefault(); void join(false); }}>
        <label className="field">Room code<input data-testid="join-code" value={code} maxLength={12} onChange={(e) => setCode(e.target.value)} placeholder="ABC123" style={{ width: 110, textTransform: "uppercase" }} /></label>
        <label className="field grow">Your name<input data-testid="join-name" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">Password<input type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} style={{ width: 120 }} /></label>
        <button className="btn primary" type="submit" disabled={code.trim().length < 4} data-testid="join-submit">Join</button>
        <button className="btn" type="button" disabled={code.trim().length < 4} onClick={() => void join(true)}>Spectate</button>
      </form>
    </section>
  );
}

function LanPanel() {
  const [info, setInfo] = useState<{ addresses: string[]; port: number; reachable: boolean } | null>(null);
  useEffect(() => {
    lanInfo().then(setInfo, () => setInfo(null));
  }, []);
  if (!info) return null;
  return (
    <section className="panel">
      <h2>Playing over LAN</h2>
      {info.reachable ? (
        <p>
          Other devices can open{" "}
          {info.addresses.map((a) => <code key={a}>http://{a}:{info.port}</code>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " or ", el] : [el]), [])}
          {" "}and join with the room code.
        </p>
      ) : (
        <p className="hint">
          The server is only listening on this computer. Restart it with <code>FYODOR_HOST=0.0.0.0 scripts/serve.sh</code> to let
          other devices on your network join LAN games.
        </p>
      )}
    </section>
  );
}
