import { useEffect, useMemo, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { CardFace } from "../cards/CardFace";
import { useCard } from "../state/cardCache";
import { Modal } from "../components/Modal";
import { CONFIGURABLE_RULES, MULLIGAN_RULES, MulliganEditor, draftPolicy, rememberPolicy } from "../components/MulliganEditor";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import {
  arrangeLobbySeats,
  changeLobbySeat,
  clearLobbyDeck,
  forgetMyDeck,
  kickFromLobby,
  leaveLobby,
  myDecks,
  importPersonalDeck,
  joinGame,
  personalCollection,
  rememberSeat,
  seatToken,
  syncPersonalCollection,
  rememberMyDeck,
  setLobbyProfile,
  setLobbyReady,
  startLobbyGame,
  submitLobbyDeck,
  updateLobbySettings,
  type LobbyDeckBody,
  type MyDeck,
  lanInfo,
} from "../services/games";
import { useGame } from "../state/gameStore";
import { activeProfile } from "../state/prefs";
import type { DeckSummary } from "../types/decks";
import { SPECTATOR, type LobbySeat, type LobbySettings, type LobbyView } from "../types/game";
import { EliminationOrder, FinalBoard } from "./GameRecap";
import { PersonalDeckImports } from "./PersonalDeckImports";
import { TURN_ORDER_LABEL, TURN_ORDER_SHORT, canNudge, moveSeat, nudgeSeat, previewLine, rollsText, type TurnOrderMode } from "./seating";
import "./lobby.css";
import { Icon } from "../components/Icon";

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
  const [dragOver, setDragOver] = useState<string | null>(null);
  const setLobby = (l: LobbyView) => useGame.getState().applyLobby(l);

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
  // -- seating -- the host arranges the seats: arrows on each seat, or drag its grip onto another seat
  const seatIds = lobby.seats.map((x) => x.id);
  const arrange = async (order: string[]) => {
    if (order.join() !== seatIds.join()) await run(() => arrangeLobbySeats(gameId, order));
  };
  // an arrow keeps the keyboard on the player it moved (their seat number just changed)
  const nudge = (id: string, delta: -1 | 1) => {
    const order = nudgeSeat(seatIds, id, delta);
    const to = `p${order.indexOf(id) + 1}`;
    void arrange(order).then(() => requestAnimationFrame(() => {
      const button = (dir: string) => document.querySelector<HTMLButtonElement>(`[data-testid="seat-${dir}-${to}"]:not(:disabled)`);
      (button(delta < 0 ? "earlier" : "later") ?? button(delta < 0 ? "later" : "earlier"))?.focus();
    }));
  };

  const s = lobby.settings;
  return (
    <div className="lobby" data-testid="lobby">
      <header className="lobby-head">
        <div className="lobby-title">
          <h1>{s.name}</h1>
          <div className="lobby-meta">
            <span>Commander</span>
            <span>Life {s.starting_life ?? 40}</span>
            <span title={DECK_PRIVACY_HINT[s.deck_privacy]}>Decks: {DECK_PRIVACY_LABEL[s.deck_privacy]}</span>
            <span className={lobby.mulligan?.needs_definition ? "warn" : undefined}>
              Mulligan: {lobby.mulligan?.display_name ?? MULLIGAN_LABEL[s.mulligan_rule] ?? s.mulligan_rule}
              {lobby.mulligan?.needs_definition ? " (not defined yet)" : ""}
            </span>
            <span>Turn order: {TURN_ORDER_SHORT[s.turn_order ?? "pod"]}</span>
            <span>Automation: {(s.automation ?? "off").toUpperCase()}</span>
            {(s.automation ?? "off") === "off" && <span>Response helper: {s.priority_helper === "simple" ? "On" : "Off"}</span>}
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

      {lobby.is_host && lobby.game.code && <InviteLink code={lobby.game.code} />}

      <SeatingBar lobby={lobby} busy={busy} onRun={run} />

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
            arranging={lobby.is_host ? {
              earlier: canNudge(seatIds, seat.id, -1) ? () => nudge(seat.id, -1) : null,
              later: canNudge(seatIds, seat.id, 1) ? () => nudge(seat.id, 1) : null,
              dropOn: (from) => void arrange(moveSeat(seatIds, from, seat.id)),
              over: dragOver === seat.id,
              setOver: (on) => setDragOver(on ? seat.id : null),
            } : null}
          />
        ))}
      </div>

      {lobby.night && lobby.night.length > 0 && <SessionRecap games={lobby.night} />}

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

/** -- seating -- the next game's order for everyone, and for the host how the first player is decided. */
function SeatingBar({ lobby, busy, onRun }: { lobby: LobbyView; busy: boolean; onRun: (fn: () => Promise<unknown>) => Promise<void> }) {
  const line = previewLine(lobby);
  const mode: TurnOrderMode = lobby.settings.turn_order ?? "pod";
  if (!lobby.is_host && !line) return null;
  return (
    <section className="seating-bar" aria-label="Seating and turn order" data-testid="seating-bar">
      <span className="seating-label">Next game</span>
      <span className="seating-preview" data-testid="turn-preview">{line || "Waiting for players."}</span>
      {lobby.is_host && (
        <>
          <span className="spacer" />
          <span className="hint seating-hint">Arrange seats with the arrows, or drag a seat's grip onto another seat.</span>
          <label className="seating-mode">
            <span>First player</span>
            <select data-testid="seating-mode" value={mode} disabled={busy}
              onChange={(e) => void onRun(() => updateLobbySettings(lobby.game.id, { turn_order: e.target.value as TurnOrderMode }))}>
              {(["pod", "random", "seats"] as const).map((m) => <option key={m} value={m}>{TURN_ORDER_LABEL[m]}</option>)}
            </select>
          </label>
        </>
      )}
    </section>
  );
}

/** The link the host sends the pod: it opens Join with the room code already filled in. */
function InviteLink({ code }: { code: string }) {
  const [addr, setAddr] = useState<string | null>(null);
  useEffect(() => {
    lanInfo().then((i) => setAddr(i.reachable && i.addresses[0] ? `http://${i.addresses[0]}:${i.port}` : null), () => setAddr(null));
  }, []);
  if (!addr) return null;
  const link = `${addr}/#/play?code=${code}`;
  return (
    <p className="invite-link" data-testid="invite-link">
      Friends on your network open <code>{link}</code>
      <button className="tt-btn ghost" onClick={() => void navigator.clipboard?.writeText(link).then(() => toast("Invite link copied"), () => undefined)}>Copy link</button>
    </p>
  );
}

/** Tonight so far (TABLETOP_QOL_MILESTONE #17): a casual recap, never a ranking. */
function SessionRecap({ games }: { games: NonNullable<LobbyView["night"]> }) {
  const wins = new Map<string, number>();
  for (const g of games) if (g.result_type === "single" || g.result_type === "multiple") for (const w of g.winner_names) wins.set(w, (wins.get(w) ?? 0) + 1);
  const minutes = games.reduce((n, g) => n + (g.minutes ?? 0), 0);
  const describe = (g: (typeof games)[number]) =>
    g.result_type === "draw" ? "Draw" : g.result_type === "no_result" ? "No result" : `${g.winner_names.join(" & ")} won`;
  return (
    <section className="session-recap" data-testid="session-recap" aria-label="Tonight so far">
      <h2>Tonight so far</h2>
      <p className="hint">
        {games.length} game{games.length === 1 ? "" : "s"}{minutes ? ` · about ${minutes} min` : ""}
        {wins.size > 0 && ` · ${[...wins].sort((a, b) => b[1] - a[1]).map(([n, w]) => `${n} ${w}`).join(", ")}`}
      </p>
      <ol>
        {games.map((g) => {
          const winner = g.winner_names.length === 1 ? g.winner_names[0]! : null;
          const cmdr = winner ? g.commanders?.[winner]?.join(" & ") : null;
          return (
            <li key={g.number}>
              <span className="recap-n">Game {g.number}</span>
              <span>
                {describe(g)}{cmdr ? ` with ${cmdr}` : ""}{g.agreed ? " (agreed)" : ""}
                {g.rolls && g.rolls.length > 0 && <span className="recap-rolls" data-testid="recap-rolls"> · d20 {rollsText(g.rolls)}</span>}
              </span>
              <span className="hint">{g.turns} turn{g.turns === 1 ? "" : "s"}{g.minutes ? ` · ${g.minutes} min` : ""}</span>
              {(!!g.eliminations?.length || !!g.result_id) && (
                <div className="recap-more">
                  <EliminationOrder list={g.eliminations} />
                  {g.result_id && <FinalBoard resultId={g.result_id} eliminations={g.eliminations} />}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <a className="tt-btn ghost" href="#/stats">Pod stats</a>
    </section>
  );
}

/** -- seating -- the host's controls for one seat (null for everyone else). */
interface Arranging {
  earlier: (() => void) | null;
  later: (() => void) | null;
  dropOn: (from: string) => void;
  over: boolean;
  setOver: (on: boolean) => void;
}

const SEAT_DRAG = "application/x-fyodor-seat";

function SeatPlate({ seat, mine, lobby, busy, onChoose, onRun, arranging }: {
  seat: LobbySeat;
  mine: boolean;
  lobby: LobbyView;
  busy: boolean;
  onChoose: () => void;
  onRun: (fn: () => Promise<unknown>) => Promise<void>;
  arranging: Arranging | null;
}) {
  const gameId = lobby.game.id;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(seat.name);
  const deck = seat.deck;
  const iAmSeated = lobby.seats.some((s) => s.id === lobby.viewer);
  const state = !seat.claimed ? "open" : seat.ready ? "ready" : deck ? "deck" : "choosing";

  const cmdId = deck?.commander_ids?.[0] ?? null;
  const cov = deck?.coverage;
  const covTotal = cov ? cov.FULL + cov.PARTIAL + cov.REVIEW + cov.MANUAL : 0;
  const level = lobby.settings.automation ?? "off";
  return (
    <section className={`seat-plate seat-card frame ${state} ${mine ? "mine" : ""} ${arranging?.over ? "drop-target" : ""}`}
      style={{ ["--seat" as string]: seat.color }} data-testid={`seat-${seat.id}`}
      onDragOver={arranging ? (e) => {
        if (!e.dataTransfer.types.includes(SEAT_DRAG)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        if (!arranging.over) arranging.setOver(true);
      } : undefined}
      onDragLeave={arranging ? (e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) arranging.setOver(false); } : undefined}
      onDrop={arranging ? (e) => {
        const from = e.dataTransfer.getData(SEAT_DRAG);
        arranging.setOver(false);
        if (!from) return;
        e.preventDefault();
        arranging.dropOn(from);
      } : undefined}>
      <div className="seat-top">
        <span className="portrait" style={{ ["--size" as string]: "38px", borderColor: seat.claimed ? seat.color : undefined }}>
          {seat.claimed ? seat.name.slice(0, 1).toUpperCase() : seat.id.slice(1)}
        </span>
        <span className="seat-who">
          <span className="seat-no">Player {seat.id.slice(1)}{seat.host ? " · Host" : ""}{mine ? " · You" : ""}</span>
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
        </span>
        <span className="spacer" />
        {seat.claimed && <span className={`presence ${seat.connected ? "on" : ""}`} title={seat.connected ? "Connected" : "Not connected"} />}
        {mine && (
          <input type="color" className="seat-color" value={seat.color} title="Your color"
            onChange={(e) => void onRun(() => setLobbyProfile(gameId, { color: e.target.value }))} />
        )}
        {arranging && seat.claimed && (
          <span className="seat-move" role="group" aria-label={`Move ${seat.name}`}>
            <button className="tt-icon" disabled={busy || !arranging.earlier} onClick={() => arranging.earlier?.()}
              title={`Move ${seat.name} one seat earlier`} aria-label={`Move ${seat.name} one seat earlier`} data-testid={`seat-earlier-${seat.id}`}>
              <Icon name="left" size={14} />
            </button>
            <span className="seat-grip" draggable={!busy} title={`Drag ${seat.name} onto another seat`} aria-hidden
              onDragStart={(e) => { e.dataTransfer.setData(SEAT_DRAG, seat.id); e.dataTransfer.effectAllowed = "move"; }}
              onDragEnd={() => arranging.setOver(false)}>
              <Icon name="grip" size={14} />
            </span>
            <button className="tt-icon" disabled={busy || !arranging.later} onClick={() => arranging.later?.()}
              title={`Move ${seat.name} one seat later`} aria-label={`Move ${seat.name} one seat later`} data-testid={`seat-later-${seat.id}`}>
              <Icon name="right" size={14} />
            </button>
          </span>
        )}
        {lobby.is_host && seat.claimed && !seat.host && (
          <button className="tt-icon" title={`Remove ${seat.name} from the table`} onClick={() => {
            if (window.confirm(`Remove ${seat.name} from the table?`)) void onRun(() => kickFromLobby(gameId, seat.id));
          }}>✕</button>
        )}
      </div>

      <div className={`seat-art ${cmdId ? "" : "empty"}`}>
        {cmdId ? <CommanderArt id={cmdId} /> : <span className="seat-art-glyph" aria-hidden><Icon name={seat.claimed ? "cards" : "plus"} size={34} /></span>}
        <div className="seat-art-caption">
          <b>{deck?.commanders?.length ? deck.commanders.join(" & ") : deck ? (deck.name ?? "A deck") : seat.claimed ? "No deck yet" : "Waiting for a player"}</b>
          {deck?.commanders?.length ? <span>{deck.name}</span> : null}
          {deck?.color_identity && <ColorPips colors={deck.color_identity} />}
        </div>
      </div>

      <div className={`seat-status ${state}`} data-testid={`seat-status-${seat.id}`}>
        {state === "ready" ? "✓ Ready" : state === "deck" ? "Not ready" : state === "choosing" ? (mine ? "Choose your deck" : "Choosing a deck…") : "Open seat"}
      </div>

      <div className="seat-facts">
        <div className="seat-fact"><span>Automation</span><b>{level === "off" ? "Off" : level === "assisted" ? "Assisted" : "Full"}</b></div>
        {cov && covTotal > 0 && (
          <div className="seat-fact" title={`FULL ${cov.FULL} · PARTIAL ${cov.PARTIAL} · REVIEW ${cov.REVIEW} · MANUAL ${cov.MANUAL}`} data-testid={`coverage-${seat.id}`}>
            <span>Fully automated</span>
            <b className="cov">{Math.round((cov.FULL / covTotal) * 100)}%</b>
            <span className="cov-count">({cov.FULL}/{covTotal})</span>
          </div>
        )}
        {deck && <div className="seat-fact"><span>Deck</span><b>{deck.card_count} cards</b></div>}
      </div>

      <div className="seat-deck">
        {deck && (
          <>
            {mine && seat.queued && !seat.ready && (
              <div className="seat-queued" data-testid="queued-deck">
                Next deck queued — <b>{deck.commanders?.length ? deck.commanders.join(" & ") : deck.name}</b>. Ready to use it, or change it.
              </div>
            )}
            {mine && deck.report && deck.report.unresolved.length > 0 && (
              <div className="warn small">{deck.report.unresolved.length} line(s) not found — they'll be text proxies</div>
            )}
            {mine && deck.warnings && deck.warnings.length > 0 && (
              <details className="deck-checks" data-testid="deck-checks">
                <summary className="warn small">
                  {deck.warning_count ? `⚠ ${deck.warning_count} deck check${deck.warning_count === 1 ? "" : "s"}` : "ⓘ Notes"} — you can play anyway
                </summary>
                <ul>{deck.warnings.map((w, i) => <li key={i} className={w.level}>{w.message}</li>)}</ul>
              </details>
            )}
            {!mine && !!deck.warning_count && (
              <div className="hint" title={deck.warnings?.map((w) => w.message).join("\n")}>⚠ {deck.warning_count} deck check{deck.warning_count === 1 ? "" : "s"}</div>
            )}
            {deck.list && !mine && <DeckListPeek list={deck.list} />}
          </>
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
              {seat.ready ? "Ready ✓" : deck?.warning_count ? "Play anyway" : "Ready"}
            </button>
          </>
        )}
        {!mine && !seat.claimed && iAmSeated && (
          <button className="tt-btn ghost" disabled={busy} onClick={() => void onRun(() => changeLobbySeat(gameId, seat.id))}>Sit here</button>
        )}
        {!seat.claimed && lobby.viewer === SPECTATOR && !lobby.is_host && lobby.game.code && (
          <button className="tt-btn ghost" disabled={busy} data-testid={`take-seat-${seat.id}`}
            title="Take this seat (a deck you queued while watching comes with you)"
            onClick={() => void onRun(() => takeSeat(lobby, seat.id))}>Take this seat</button>
        )}
        {!mine && seat.claimed && <span className={`seat-state ${state}`}>{state === "ready" ? "Ready" : state === "deck" ? "Deck chosen" : "Choosing"}</span>}
      </div>
    </section>
  );
}

/**
 * (spectator activities) A spectator in the lobby takes an open seat; the deck they queued while watching comes with them
 * (the server moves it from their spectator token to the new seat).
 */
async function takeSeat(lobby: LobbyView, seat: string): Promise<void> {
  const gameId = lobby.game.id;
  const password = lobby.game.has_password ? window.prompt("Room password") ?? undefined : undefined;
  if (lobby.game.has_password && password === undefined) return;
  const name = activeProfile().name === "Player" ? undefined : activeProfile().name;
  const res = await joinGame({ code: lobby.game.code ?? "", seat, name, password }, seatToken(gameId));
  rememberSeat(gameId, res.token);
  useGame.getState().connect(gameId, { token: res.token });
}

/** The commander's art (or its text card offline), cropped for the seat card. */
function CommanderArt({ id }: { id: string }) {
  const card = useCard(id);
  return <div className="seat-art-card"><CardFace card={card} /></div>;
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
  const [companion, setCompanion] = useState("");
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

  const savedChanged = async () => {
    setSaved(myDecks());
    try { useGame.getState().applyLobby(await syncPersonalCollection(gameId)); }
    catch (e) { toastError(e); }
  };

  const submit = async (body: LobbyDeckBody, remember: boolean) => {
    setBusy(true);
    try {
      const imported = await importPersonalDeck(gameId, body);
      if (remember || body.deck_id) rememberMyDeck(imported.name, body, imported.commanders, imported);
      const res = await submitLobbyDeck(gameId, { name: imported.name, text: imported.text,
        collection: personalCollection(), ...(companion ? { companion_id: companion } : {}) });
      const mine = res.seats.find((s) => s.id === res.viewer)?.deck;

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
      <label className="field">Companion from My decks (optional)
        <select value={companion} disabled={busy} onChange={e => setCompanion(e.target.value)}>
          <option value="">Use the deck's companion, if any</option>
          {Array.from(new Map(saved.flatMap(d => d.companions ?? []).map(c => [c.name, c])).values()).map(c =>
            <option key={c.name} value={c.printing_id}>{c.name}</option>)}
        </select>
      </label>
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
            <PersonalDeckImports gameId={gameId} onSaved={savedChanged} disabled={busy} onBusyChange={setBusy} />
            {saved.length === 0 && <p className="hint">No personal decks saved yet.</p>}
            {saved.map((d) => (
              <div key={d.id} className="deck-pick-row">
                <button className="deck-pick" disabled={busy} onClick={() => void submit(d.body, true)}>
                  <b>{d.name}</b>
                  <span className="hint">{d.commanders.join(" & ") || (d.body.archidekt ? "Archidekt" : "Deck list")}</span>
                </button>
                <button className="tt-icon" title="Forget this deck" onClick={() => { forgetMyDeck(d.id); void savedChanged(); }}>✕</button>
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
        <label className="field">Automation
          <select data-testid="lobby-automation" value={draft.automation ?? "off"} onChange={(e) => set({ automation: e.target.value as LobbySettings["automation"] })}>
            <option value="off">Off — sandbox, nothing enforced</option>
            <option value="assisted">Assisted — validates and asks before important steps</option>
            <option value="full">Full — supported rules happen by themselves</option>
          </select>
        </label>
        <label className="field">Turn order
          <select data-testid="lobby-turn-order" value={draft.turn_order ?? "pod"} onChange={(e) => set({ turn_order: e.target.value as LobbySettings["turn_order"] })}>
            {(["pod", "random", "seats"] as const).map((m) => <option key={m} value={m}>{TURN_ORDER_LABEL[m]}</option>)}
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
