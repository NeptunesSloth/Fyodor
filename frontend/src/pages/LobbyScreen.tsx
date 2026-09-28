import { useEffect, useMemo, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { Modal } from "../components/Modal";
import { CONFIGURABLE_RULES, MULLIGAN_RULES, MulliganEditor, draftPolicy, rememberPolicy } from "../components/MulliganEditor";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import {
  changeLobbySeat,
  clearLobbyDeck,
  forgetMyDeck,
  kickFromLobby,
  leaveLobby,
  myDecks,
  rememberMyDeck,
  setLobbyProfile,
  setLobbyReady,
  startLobbyGame,
  submitLobbyDeck,
  updateLobbySettings,
  type LobbyDeckBody,
  type MyDeck,
} from "../services/games";
import { useGame } from "../state/gameStore";
import type { DeckSummary } from "../types/decks";
import type { LobbySeat, LobbySettings, LobbyView } from "../types/game";
import "./lobby.css";

export const DECK_PRIVACY_LABEL: Record<LobbySettings["deck_privacy"], string> = {
  private: "Private",
  commander_only: "Commander only",
  public: "Public",
};
const DECK_PRIVACY_HINT: Record<LobbySettings["deck_privacy"], string> = {
  private: "Others see only how many cards you brought.",
  commander_only: "Others see your commander(s), colors and deck name — not the list.",
  public: "Everyone can read every deck list before the game.",
};
export const MULLIGAN_LABEL: Record<string, string> = Object.fromEntries(MULLIGAN_RULES);
const MAX_FILE = 2 * 1024 * 1024;

/** Pregame table: take a seat, bring your own deck, get ready; the host starts the game. */
export function LobbyScreen({ lobby }: { lobby: LobbyView }) {
  const gameId = lobby.game.id;
  const me = lobby.seats.find((s) => s.id === lobby.viewer) ?? null;
  const [choosing, setChoosing] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const setLobby = (l: LobbyView) => useGame.setState({ lobby: l });

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      const res = await fn();
      if (res && typeof res === "object" && "seats" in res) setLobby(res as LobbyView);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const start = async (force: boolean) => {
    if (force && !window.confirm(`Start without waiting?\n\n${lobby.start_blockers.join("\n")}`)) return;
    await run(() => startLobbyGame(gameId, { force, first_player: "random" }));
  };

  const s = lobby.settings;
  return (
    <div className="lobby" data-testid="lobby">
      <header className="lobby-head">
        <div className="lobby-title">
          <h1>{s.name}</h1>
          <div className="lobby-meta">
            <span>{s.format === "commander" ? "Commander" : s.format === "constructed" ? "Constructed" : "Sandbox"}</span>
            <span>Life {s.starting_life ?? (s.format === "commander" ? 40 : 20)}</span>
            <span title={DECK_PRIVACY_HINT[s.deck_privacy]}>Decks: {DECK_PRIVACY_LABEL[s.deck_privacy]}</span>
            <span className={lobby.mulligan?.needs_definition ? "warn" : undefined}>
              Mulligan: {lobby.mulligan?.display_name ?? MULLIGAN_LABEL[s.mulligan_rule] ?? s.mulligan_rule}
              {lobby.mulligan?.needs_definition ? " (not defined yet)" : ""}
            </span>
            <span>Response helper: {s.priority_helper === "simple" ? "On" : "Off"}</span>
          </div>
        </div>
        {lobby.game.code && (
          <button
            className="room-code"
            title="Copy room code"
            onClick={() => void navigator.clipboard?.writeText(lobby.game.code ?? "").then(() => toast("Room code copied"), () => undefined)}
          >
            <small>Room</small>
            <b data-testid="room-code">{lobby.game.code}</b>
          </button>
        )}
      </header>

      <div className="seat-grid">
        {lobby.seats.map((seat) => (
          <SeatPlate
            key={seat.id}
            seat={seat}
            mine={seat.id === lobby.viewer}
            lobby={lobby}
            busy={busy}
            onChoose={() => setChoosing(true)}
            onRun={run}
          />
        ))}
      </div>

      <footer className="lobby-foot">
        <div className="lobby-status">
          {lobby.start_blockers.length === 0 ? (
            <span className="ok">Everyone is ready.</span>
          ) : (
            <span className="hint">{lobby.start_blockers.join(" · ")}</span>
          )}
          {lobby.spectators > 0 && <span className="hint"> · {lobby.spectators} watching</span>}
        </div>
        <span className="spacer" />
        {me && !me.host && (
          <button className="tt-btn" disabled={busy} onClick={() => void run(async () => {
            await leaveLobby(gameId);
            navigate("/play");
          })}>Leave table</button>
        )}
        {lobby.is_host && (
          <>
            <button className="tt-btn" onClick={() => setSettingsOpen(true)}>Table settings</button>
            {lobby.start_blockers.length > 0 && (
              <button className="tt-btn" disabled={busy} onClick={() => void start(true)} title="Start now; players without a deck get empty libraries">
                Start anyway
              </button>
            )}
            <button className="tt-btn brass" data-testid="start-game" disabled={busy || lobby.start_blockers.length > 0} onClick={() => void start(false)}>
              Start game
            </button>
          </>
        )}
        {!lobby.is_host && <span className="hint">The host starts the game when everyone is ready.</span>}
      </footer>

      {choosing && me && <ChooseDeck gameId={gameId} onClose={() => setChoosing(false)} onDone={(l) => { setLobby(l); setChoosing(false); }} />}
      {settingsOpen && <SettingsDialog lobby={lobby} onClose={() => setSettingsOpen(false)} onSaved={setLobby} />}
    </div>
  );
}

function SeatPlate({ seat, mine, lobby, busy, onChoose, onRun }: {
  seat: LobbySeat;
  mine: boolean;
  lobby: LobbyView;
  busy: boolean;
  onChoose: () => void;
  onRun: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const gameId = lobby.game.id;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(seat.name);
  const deck = seat.deck;
  const iAmSeated = lobby.seats.some((s) => s.id === lobby.viewer);
  const state = !seat.claimed ? "open" : seat.ready ? "ready" : deck ? "deck" : "choosing";

  return (
    <section className={`seat-plate ${state} ${mine ? "mine" : ""}`} style={{ ["--seat" as string]: seat.color }} data-testid={`seat-${seat.id}`}>
      <div className="seat-band" />
      <div className="seat-top">
        <span className="seat-no">{seat.id.slice(1)}</span>
        {mine && editing ? (
          <form className="seat-name-edit" onSubmit={(e) => {
            e.preventDefault();
            setEditing(false);
            if (name.trim() && name.trim() !== seat.name) void onRun(() => setLobbyProfile(gameId, { name: name.trim() }));
          }}>
            <input autoFocus value={name} maxLength={40} onChange={(e) => setName(e.target.value)} onBlur={(e) => e.currentTarget.form?.requestSubmit()} />
          </form>
        ) : (
          <b className="seat-name" title={mine ? "Click to rename" : undefined} onClick={() => mine && (setName(seat.name), setEditing(true))}>
            {seat.claimed ? seat.name : "Open seat"}
          </b>
        )}
        {seat.host && <span className="seat-tag">Host</span>}
        {mine && <span className="seat-tag you">You</span>}
        {seat.claimed && <span className={`presence ${seat.connected ? "on" : ""}`} title={seat.connected ? "Connected" : "Not connected"} />}
        {mine && (
          <input type="color" className="seat-color" value={seat.color} title="Your color"
            onChange={(e) => void onRun(() => setLobbyProfile(gameId, { color: e.target.value }))} />
        )}
        {lobby.is_host && seat.claimed && !seat.host && (
          <button className="tt-icon" title={`Remove ${seat.name} from the table`} onClick={() => {
            if (window.confirm(`Remove ${seat.name} from the table?`)) void onRun(() => kickFromLobby(gameId, seat.id));
          }}>✕</button>
        )}
      </div>

      <div className="seat-deck">
        {!seat.claimed ? (
          <span className="hint">Waiting for a player</span>
        ) : deck ? (
          <>
            <div className="deck-line">
              <b>{deck.name ?? "A deck"}</b>
              {deck.color_identity && <ColorPips colors={deck.color_identity} />}
            </div>
            {deck.commanders && deck.commanders.length > 0 && <div className="deck-cmd">{deck.commanders.join(" & ")}</div>}
            <div className="hint">{deck.card_count} cards</div>
            {mine && deck.report && deck.report.unresolved.length > 0 && (
              <div className="warn small">{deck.report.unresolved.length} line(s) not found — they'll be text proxies</div>
            )}
            {deck.list && !mine && <DeckListPeek list={deck.list} />}
          </>
        ) : (
          <span className="hint">{mine ? "Choose the deck you're bringing." : "Choosing a deck…"}</span>
        )}
      </div>

      <div className="seat-actions">
        {mine && (
          <>
            <button className="tt-btn" disabled={busy} onClick={onChoose} data-testid="choose-deck">{deck ? "Change deck" : "Choose deck"}</button>
            {deck && (
              <button className="tt-btn ghost" disabled={busy} onClick={() => void onRun(() => clearLobbyDeck(gameId))}>Clear</button>
            )}
            <span className="spacer" />
            <button
              className={`tt-btn ${seat.ready ? "on" : "brass"}`}
              data-testid="ready"
              disabled={busy || !deck}
              onClick={() => void onRun(() => setLobbyReady(gameId, !seat.ready))}
            >
              {seat.ready ? "Ready ✓" : "Ready"}
            </button>
          </>
        )}
        {!mine && !seat.claimed && iAmSeated && (
          <button className="tt-btn ghost" disabled={busy} onClick={() => void onRun(() => changeLobbySeat(gameId, seat.id))}>Sit here</button>
        )}
        {!mine && seat.claimed && <span className={`seat-state ${state}`}>{state === "ready" ? "Ready" : state === "deck" ? "Deck chosen" : "Choosing"}</span>}
      </div>
    </section>
  );
}

function DeckListPeek({ list }: { list: { section: string; quantity: number; name: string }[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="tt-link" onClick={() => setOpen(true)}>View list</button>
      {open && (
        <Modal title="Deck list" onClose={() => setOpen(false)}>
          <div className="peek-list">
            {list.map((e, i) => (
              <div key={i}><span className="hint">{e.section === "main" ? "" : `${e.section} · `}</span>{e.quantity} {e.name}</div>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}

type Source = "table" | "mine" | "archidekt" | "paste" | "file";

function ChooseDeck({ gameId, onClose, onDone }: { gameId: string; onClose: () => void; onDone: (l: LobbyView) => void }) {
  const [hostDecks, setHostDecks] = useState<DeckSummary[] | null>(null);
  const [saved, setSaved] = useState<MyDeck[]>(() => myDecks());
  const [source, setSource] = useState<Source>(saved.length ? "mine" : "paste");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<{ name: string; body: LobbyDeckBody } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // The host's library is offered only on the host computer (the server enforces this too).
    listDecks().then(
      (d) => {
        setHostDecks(d);
        if (!saved.length && d.length) setSource("table");
      },
      (e) => {
        if (!(e instanceof ApiError && e.status === 403)) toastError(e);
        setHostDecks(null);
      },
    );
  }, [saved.length]);

  const submit = async (body: LobbyDeckBody, remember: boolean) => {
    setBusy(true);
    try {
      const res = await submitLobbyDeck(gameId, body);
      const mine = res.seats.find((s) => s.id === res.viewer)?.deck;
      if (remember && mine) rememberMyDeck(mine.name ?? body.name ?? "Deck", body, mine.commanders ?? []);
      toast(`Deck ready: ${mine?.name ?? "deck"} (${mine?.card_count ?? 0} cards)`);
      onDone(res);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const readFile = async (f: File) => {
    if (f.size > MAX_FILE) {
      toast("That file is too large for a deck (2 MB max)", "error");
      return;
    }
    const content = await f.text();
    const isJson = f.name.toLowerCase().endsWith(".json") || content.trimStart().startsWith("{");
    const base = f.name.replace(/\.[^.]+$/, "");
    setFile({ name: f.name, body: isJson ? { json: content, name: base } : { text: content, name: base } });
  };

  const tabs: [Source, string][] = [
    ...(hostDecks ? ([["table", "Table decks"]] as [Source, string][]) : []),
    ["mine", "My decks"],
    ["archidekt", "Archidekt"],
    ["paste", "Paste list"],
    ["file", "File"],
  ];

  return (
    <Modal title="Bring a deck" onClose={onClose} wide>
      <div className="deck-src-tabs" role="tablist">
        {tabs.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={source === key} className={`tt-tab ${source === key ? "on" : ""}`} onClick={() => setSource(key)}>
            {label}
          </button>
        ))}
      </div>
      <div className="deck-src-body">
        {source === "table" && hostDecks && (
          <div className="deck-pick-list">
            {hostDecks.length === 0 && <p className="hint">No decks in this computer's library.</p>}
            {hostDecks.map((d) => (
              <button key={d.id} className="deck-pick" disabled={busy} onClick={() => void submit({ deck_id: d.id }, false)}>
                <b>{d.name}</b>
                <span className="hint">{d.commanders.join(" & ") || d.format}</span>
                <ColorPips colors={d.color_identity} />
              </button>
            ))}
          </div>
        )}
        {source === "mine" && (
          <div className="deck-pick-list">
            {saved.length === 0 && <p className="hint">Decks you bring to a table are remembered in this browser for next time.</p>}
            {saved.map((d) => (
              <div key={d.id} className="deck-pick-row">
                <button className="deck-pick" disabled={busy} onClick={() => void submit(d.body, true)}>
                  <b>{d.name}</b>
                  <span className="hint">{d.commanders.join(" & ") || (d.body.archidekt ? "Archidekt" : "Deck list")}</span>
                </button>
                <button className="tt-icon" title="Forget this deck" onClick={() => { forgetMyDeck(d.id); setSaved(myDecks()); }}>✕</button>
              </div>
            ))}
          </div>
        )}
        {source === "archidekt" && (
          <form className="deck-form" onSubmit={(e) => { e.preventDefault(); void submit({ archidekt: url.trim() }, true); }}>
            <label className="field">Archidekt deck URL
              <input autoFocus value={url} maxLength={300} placeholder="https://archidekt.com/decks/123456/…" onChange={(e) => setUrl(e.target.value)} />
            </label>
            <p className="hint">The host computer fetches the public deck once; the game itself never needs Archidekt.</p>
            <button className="tt-btn brass" type="submit" disabled={busy || !url.trim()}>{busy ? "Fetching…" : "Use this deck"}</button>
          </form>
        )}
        {source === "paste" && (
          <form className="deck-form" onSubmit={(e) => { e.preventDefault(); void submit({ text, name: name.trim() || undefined }, true); }}>
            <label className="field">Deck name<input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="Optional" /></label>
            <label className="field">Deck list
              <textarea autoFocus rows={12} value={text} onChange={(e) => setText(e.target.value)} data-testid="deck-text"
                placeholder={"Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Sol Ring\n…\n\nMoxfield, Archidekt, MTGGoldfish, Arena/MTGO and plain lists work."} />
            </label>
            <button className="tt-btn brass" type="submit" disabled={busy || !text.trim()} data-testid="use-deck">{busy ? "Checking…" : "Use this deck"}</button>
          </form>
        )}
        {source === "file" && (
          <div className="deck-form">
            <input ref={fileInput} type="file" accept=".txt,.dec,.dek,.json,.csv,text/plain,application/json" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void readFile(f); e.target.value = ""; }} />
            <button className="tt-btn" onClick={() => fileInput.current?.click()}>Choose a file…</button>
            <p className="hint">A deck list (.txt, .dec) or an Archidekt export (.json). The file is read here in your browser and only its text is sent.</p>
            {file && (
              <>
                <div>Selected: <b>{file.name}</b></div>
                <button className="tt-btn brass" disabled={busy} onClick={() => void submit(file.body, true)}>{busy ? "Checking…" : "Use this deck"}</button>
              </>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function SettingsDialog({ lobby, onClose, onSaved }: { lobby: LobbyView; onClose: () => void; onSaved: (l: LobbyView) => void }) {
  const [draft, setDraft] = useState<LobbySettings>(lobby.settings);
  const [busy, setBusy] = useState(false);
  const minSeats = useMemo(() => Math.max(1, ...lobby.seats.filter((s) => s.claimed).map((s) => Number(s.id.slice(1)))), [lobby.seats]);
  const set = (patch: Partial<LobbySettings>) => setDraft((d) => ({ ...d, ...patch }));
  const configurable = CONFIGURABLE_RULES.has(draft.mulligan_rule);
  const chooseRule = (rule: string) =>
    set({ mulligan_rule: rule, mulligan_policy: CONFIGURABLE_RULES.has(rule) ? (lobby.settings.mulligan_rule === rule && lobby.settings.mulligan_policy) || draftPolicy(rule) : null });
  const save = async () => {
    setBusy(true);
    try {
      if (configurable && draft.mulligan_policy) rememberPolicy(draft.mulligan_rule, draft.mulligan_policy);
      onSaved(await updateLobbySettings(lobby.game.id, draft));
      onClose();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Table settings" onClose={onClose} footer={
      <>
        <span className="hint">Changing the rules asks everyone to confirm Ready again.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={onClose}>Cancel</button>
        <button className="tt-btn brass" disabled={busy} onClick={() => void save()}>Save</button>
      </>
    }>
      <div className="settings-grid">
        <label className="field">Table name<input value={draft.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} /></label>
        <label className="field">Format
          <select value={draft.format} onChange={(e) => set({ format: e.target.value as LobbySettings["format"] })}>
            <option value="commander">Commander</option>
            <option value="constructed">Constructed</option>
            <option value="sandbox">Sandbox</option>
          </select>
        </label>
        <label className="field">Seats
          <select value={draft.seats} onChange={(e) => set({ seats: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6].filter((n) => n >= minSeats).map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="field">Starting life
          <input type="number" min={1} value={draft.starting_life ?? ""} placeholder={draft.format === "commander" ? "40" : "20"}
            onChange={(e) => set({ starting_life: e.target.value ? Number(e.target.value) : null })} />
        </label>
        <label className="field">Deck privacy
          <select value={draft.deck_privacy} onChange={(e) => set({ deck_privacy: e.target.value as LobbySettings["deck_privacy"] })}>
            {(["private", "commander_only", "public"] as const).map((p) => <option key={p} value={p}>{DECK_PRIVACY_LABEL[p]}</option>)}
          </select>
          <span className="hint">{DECK_PRIVACY_HINT[draft.deck_privacy]}</span>
        </label>
        <label className="field">Mulligan
          <select value={draft.mulligan_rule} onChange={(e) => chooseRule(e.target.value)} data-testid="mulligan-rule">
            {MULLIGAN_RULES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field">Response helper
          <select value={draft.priority_helper} onChange={(e) => set({ priority_helper: e.target.value as LobbySettings["priority_helper"] })}>
            <option value="simple">On — ask the table before resolving / moving on</option>
            <option value="off">Off</option>
          </select>
        </label>
      </div>
      {configurable && draft.mulligan_policy && (
        <>
          <h3 className="mull-editor-title">Define “{draft.mulligan_policy.display_name}”</h3>
          <p className="hint">Nothing about this rule is assumed — set each part the way your pod plays it.</p>
          <MulliganEditor value={draft.mulligan_policy} onChange={(p) => set({ mulligan_policy: p })} />
        </>
      )}
    </Modal>
  );
}
