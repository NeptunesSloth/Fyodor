import { useEffect, useMemo, useRef, useState } from "react";
import { ColorPips } from "../components/ColorPips";
import { Modal } from "../components/Modal";
import { CONFIGURABLE_RULES, MULLIGAN_RULES, MulliganEditor, draftPolicy, rememberPolicy } from "../components/MulliganEditor";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import {
  arrangeLobbySeats,
  broughtDecks,
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
  type BroughtLibrary,
  type LobbyDeckBody,
  type MyDeck,
  lanInfo,
} from "../services/games";
import { useGame } from "../state/gameStore";
import { activeProfile } from "../state/prefs";
import { contrast } from "../theme/planes";
import type { DeckSummary } from "../types/decks";
import { SPECTATOR, type LobbySeat, type LobbySettings, type LobbyView } from "../types/game";
import { TablePermissionsSetting } from "./TablePermissionsSetting";
import { ownDecks, type OwnDeck, type OwnDecks } from "./lanBits";
import { CommanderArt } from "./CommanderArt";
import { PersonalDeckImports } from "./PersonalDeckImports";
import { SessionRecap } from "./SessionRecap";
import { TURN_ORDER_LABEL, canNudge, miniSeats, moveSeat, nudgeSeat, previewLine, previewParts, type TurnOrderMode } from "./seating";
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
/** The host's choice of first player, in a word or two (the full rule is the button's tooltip). */
const MODE_NAME: Record<TurnOrderMode, string> = { pod: "Pod rule", random: "Random", seats: "Seat order" };
const AUTOMATION_NAME = { off: "Off", assisted: "Assisted", full: "Full" } as const;

/**
 * Pregame table: take a seat, bring your own deck, get ready; the host starts the game. The room is drawn as the table it
 * is: each player's commander stands on the felt at their seat, open seats are empty chairs, the next game's order and
 * tonight's score sheet lie at the near edge, and Ready / Start sit on the table's front rail.
 */
export function LobbyScreen({ lobby }: { lobby: LobbyView }) {
  const gameId = lobby.game.id;
  const me = lobby.seats.find((s) => s.id === lobby.viewer) ?? null;
  const [choosing, setChoosing] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const invite = useInviteLink(lobby.is_host ? lobby.game.code : null);
  const setLobby = (l: LobbyView) => useGame.getState().applyLobby(l);
  // -- bring my decks -- the decks this seat brought: from the player's own Fyodor (sent with the join), or this browser's My decks
  const [brought, setBrought] = useState<BroughtLibrary | null>(null);
  const [savedVersion, setSavedVersion] = useState(0);
  const seated = !!me && me.id !== SPECTATOR;
  useEffect(() => {
    if (!seated) return;
    broughtDecks(gameId).then(setBrought, () => setBrought(null));
  }, [gameId, seated, me?.id]);
  const own = useMemo(() => (seated ? ownDecks(brought, myDecks()) : null), [seated, brought, savedVersion]);

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
  const arrangingFor = (seat: LobbySeat): Arranging | null => lobby.is_host ? {
    earlier: canNudge(seatIds, seat.id, -1) ? () => nudge(seat.id, -1) : null,
    later: canNudge(seatIds, seat.id, 1) ? () => nudge(seat.id, 1) : null,
    dropOn: (from) => void arrange(moveSeat(seatIds, from, seat.id)),
    over: dragOver === seat.id,
    setOver: (on) => setDragOver(on ? seat.id : null),
  } : null;

  const s = lobby.settings;
  const claimed = lobby.seats.filter((x) => x.claimed);
  const open = lobby.seats.filter((x) => !x.claimed);
  return (
    <div className="lobby" data-testid="lobby">
      <header className="lobby-top">
        <div className="lobby-title">
          <h1 title={s.name}>{s.name}</h1>
          <p className="lobby-sub">
            <span>Commander table</span>
            <span>{claimed.length} of {lobby.seats.length} seats taken</span>
            {lobby.spectators > 0 && <span>{lobby.spectators} watching</span>}
          </p>
        </div>
        {lobby.game.code && (
          <div className="lobby-door">
            <RoomCode code={lobby.game.code} />
            {lobby.is_host && invite && <InviteControl link={invite} code={lobby.game.code} />}
          </div>
        )}
      </header>

      <main className="lobby-table">
        <div className={`seat-row ${claimed.length ? "" : "all-open"}`} style={{
          ["--cols" as string]: claimed.length
            ? `repeat(${claimed.length}, minmax(0, var(--plinth-w)))${open.length ? " minmax(216px, 272px)" : ""}`
            : "minmax(0, 1fr)",
        }}>
          {claimed.map((seat) => (
            <SeatPlinth
              key={seat.id}
              seat={seat}
              mine={seat.id === lobby.viewer}
              lobby={lobby}
              busy={busy}
              onChoose={() => setChoosing(true)}
              onRun={run}
              arranging={arrangingFor(seat)}
              own={seat.id === lobby.viewer ? own : null}
              onPick={(d) => void run(() => bringDeck(gameId, d.body, { remember: !own?.brought }).finally(() => setSavedVersion((v) => v + 1)))}
            />
          ))}
          {open.length > 0 && (
            <div className="open-seats">
              {open.map((seat) => (
                <OpenSeat key={seat.id} seat={seat} lobby={lobby} busy={busy} onRun={run} invite={invite} arranging={arrangingFor(seat)} />
              ))}
            </div>
          )}
        </div>

        <div className="table-front">
          <NextGame lobby={lobby} busy={busy} onRun={run} onSettings={() => setSettingsOpen(true)} />
          {lobby.night && lobby.night.length > 0 && <SessionRecap games={lobby.night} seats={lobby.seats} />}
        </div>
      </main>

      <footer className="lobby-rail">
        <div className="rail-status" role="status">
          {claimed.length > 0 && (
            <ul className="rail-seats" aria-label="Who is ready">
              {claimed.map((x) => (
                <li key={x.id} className={x.ready ? "ready" : ""} title={`${x.name}: ${x.ready ? "ready" : x.deck ? "not ready" : "choosing a deck"}`}>
                  <SeatChip seat={x} text={x.name.slice(0, 1).toUpperCase()} />
                  {x.ready && <span className="rail-check"><Icon name="check" size={11} /></span>}
                </li>
              ))}
            </ul>
          )}
          <span className="rail-words">
            {lobby.start_blockers.length === 0 ? (
              <span className="ok">Everyone is ready.</span>
            ) : (
              lobby.start_blockers.map((b, i) => <span key={i}>{b}</span>)
            )}
          </span>
        </div>
        <div className="rail-actions">
          {me && !me.host && (
            <button className="tt-btn ghost" disabled={busy} onClick={() => void run(async () => {
              await leaveLobby(gameId);
              navigate("/play");
            })}>Leave table</button>
          )}
          {!lobby.is_host && <span className="rail-hint">The host starts the game when everyone is ready.</span>}
          {lobby.is_host && lobby.start_blockers.length > 0 && (
            <button className="tt-btn ghost" disabled={busy} onClick={() => void start(true)} title="Start now; players without a deck get empty libraries">
              Start anyway
            </button>
          )}
          {me && (
            <button
              className={`rail-btn ready-btn ${me.ready ? "is-ready" : ""}`}
              data-testid="ready"
              aria-pressed={me.ready}
              disabled={busy || !me.deck}
              title={!me.deck ? "Choose a deck first" : me.ready ? "You're ready. Press again if you need more time." : undefined}
              onClick={() => void run(() => setLobbyReady(gameId, !me.ready))}
            >
              {me.ready ? <><Icon name="check" size={17} />Ready</> : me.deck?.warning_count ? "Play anyway" : "Ready"}
            </button>
          )}
          {lobby.is_host && (
            <button className="rail-btn start-btn" data-testid="start-game" disabled={busy || lobby.start_blockers.length > 0} onClick={() => void start(false)}
              title={lobby.start_blockers.length ? `Waiting: ${lobby.start_blockers.join("; ")}` : undefined}>
              Start game
            </button>
          )}
        </div>
      </footer>

      {choosing && me && (
        <ChooseDeck gameId={gameId} brought={brought?.decks.length ? brought : null}
          onClose={() => { setChoosing(false); setSavedVersion((v) => v + 1); }}
          onDone={(l) => { setLobby(l); setChoosing(false); setSavedVersion((v) => v + 1); }} />
      )}
      {settingsOpen && <SettingsDialog lobby={lobby} onClose={() => setSettingsOpen(false)} onSaved={setLobby} />}
    </div>
  );
}

const INK_DARK = "#15120e";
const INK_LIGHT = "#f7f0e2";
/** Dark ink on a light seat colour, light ink on a dark one. */
function inkOn(color: string): string {
  try {
    return contrast(color, INK_DARK) >= contrast(color, INK_LIGHT) ? INK_DARK : INK_LIGHT;
  } catch {
    return INK_LIGHT;
  }
}

/** A seat's chip: its colour (the player's identity at the table) with its number or initial, never colour alone. */
function SeatChip({ seat, text, mine, onColor }: { seat: LobbySeat; text: string; mine?: boolean; onColor?: (color: string) => void }) {
  const ink = inkOn(seat.color);
  // a mid-tone colour reaches neither ink at 4.5:1: the number keeps a thin edge in the other one
  const style = {
    ["--seat" as string]: seat.color,
    ["--seat-ink" as string]: ink,
    ["--seat-ink-edge" as string]: ink === INK_DARK ? "0 0 2px rgba(255, 248, 235, 0.55)" : "0 1px 2px rgba(0, 0, 0, 0.75)",
  };
  if (mine && onColor) {
    return (
      <label className="seat-chip mine" style={style} title="Your colour: click to change it">
        <span aria-hidden>{text}</span>
        <input type="color" className="seat-color" value={seat.color} aria-label="Your colour" onChange={(e) => onColor(e.target.value)} />
      </label>
    );
  }
  return <span className="seat-chip" style={style} aria-hidden>{text}</span>;
}

/** Copies `text`, saying so on the button for a moment; falls back to a selection copy where the clipboard API is missing. */
function CopyButton({ text, label, done, className, testId }: { text: string; label: React.ReactNode; done: string; className?: string; testId?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(t);
  }, [copied]);
  const copy = async () => {
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(text);
      else {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand("copy");
        area.remove();
        if (!ok) throw new Error("copy");
      }
      setCopied(true);
    } catch {
      toast("Couldn't copy: select the text and copy it", "warn");
    }
  };
  return (
    <button type="button" className={`tt-btn ${className ?? ""}`} data-testid={testId} onClick={() => void copy()} aria-live="polite">
      {copied ? <><Icon name="check" size={14} />{done}</> : label}
    </button>
  );
}

/** The room code players type on the Play screen; click to copy it. */
function RoomCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);
  return (
    <button
      className="room-code"
      title="Copy room code"
      onClick={() => void navigator.clipboard?.writeText(code).then(() => setCopied(true), () => undefined)}
    >
      <small aria-live="polite">{copied ? "Copied" : "Room"}</small>
      <b data-testid="room-code">{code}</b>
    </button>
  );
}

/** The link the host sends the pod: it opens Join with the room code already filled in (null until it's known to work). */
function useInviteLink(code: string | null): string | null {
  const [addr, setAddr] = useState<string | null>(null);
  useEffect(() => {
    if (!code) return;
    lanInfo().then((i) => setAddr(i.reachable && i.addresses[0] ? `http://${i.addresses[0]}:${i.port}` : null), () => setAddr(null));
  }, [code]);
  return addr && code ? `${addr}/#/play?code=${code}` : null;
}

function InviteControl({ link, code }: { link: string; code: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="invite" ref={box} data-testid="invite-link">
      <button ref={toggle} className="tt-btn invite-btn" aria-expanded={open} aria-controls="invite-pop" onClick={() => setOpen((o) => !o)}>
        <LinkGlyph />Invite
      </button>
      {open && (
        <div className="invite-pop" id="invite-pop" role="dialog" aria-label="Invite players">
          <p>Friends on your network open this link:</p>
          <div className="invite-row">
            <input readOnly value={link} aria-label="Invite link" onFocus={(e) => e.currentTarget.select()} autoFocus />
            <CopyButton text={link} label="Copy link" done="Copied" className="brass" />
          </div>
          <p className="invite-or">Or they type the room code <b>{code}</b> on the Play screen.</p>
        </div>
      )}
    </div>
  );
}

function LinkGlyph() {
  return (
    <svg className="icon" width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.2 1.2M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.2-1.2" />
    </svg>
  );
}

/** An empty chair: a high-backed seat drawn on the icon grid. */
function ChairGlyph() {
  return (
    <svg className="icon" width={30} height={30} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M7.5 13V5.5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2V13M6 13h12v2.5H6zM7.5 15.5V21M16.5 15.5V21M7.5 18.5h9" />
    </svg>
  );
}

function WarnGlyph() {
  return (
    <svg className="icon warn-glyph" width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3.5l9.5 16.5h-19zM12 10v4.5M12 17.5h.01" />
    </svg>
  );
}

/**
 * -- seating -- the next game's order for everyone, the table's house rules, and for the host how the first player is decided
 * and the table settings (a host-only table control can sit beside Table settings in `.nx-host`).
 */
function NextGame({ lobby, busy, onRun, onSettings }: {
  lobby: LobbyView;
  busy: boolean;
  onRun: (fn: () => Promise<unknown>) => Promise<void>;
  onSettings: () => void;
}) {
  const parts = previewParts(lobby);
  const mode: TurnOrderMode = lobby.settings.turn_order ?? "pod";
  const s = lobby.settings;
  const seat = (id: string) => lobby.seats.find((x) => x.id === id);
  const seated = lobby.seats.filter((x) => x.claimed).map((x) => x.id);
  const level = s.automation ?? "off";
  return (
    <section className="next-game" aria-labelledby="next-game-title" data-testid="seating-bar">
      <MiniTable lobby={lobby} order={parts.order.length ? parts.order : seated} first={parts.first} d20={parts.source === "d20"} />
      <div className="nx-body">
        <h2 id="next-game-title">Next game</h2>
        <div className="nx-order" data-testid="turn-preview">
          {parts.note ? (
            <>
              <span className="sr-only">{previewLine(lobby)}</span>
              {parts.order.length > 0 && (
                <ol className="nx-seq" aria-hidden>
                  {parts.order.map((id) => {
                    const x = seat(id);
                    return x ? <li key={id}><SeatChip seat={x} text={x.name.slice(0, 1).toUpperCase()} />{x.name}</li> : null;
                  })}
                </ol>
              )}
              <p className="nx-note" aria-hidden>{parts.note}</p>
            </>
          ) : (
            <p className="nx-note">Waiting for players.</p>
          )}
        </div>
        {lobby.is_host && (
          <div className="nx-mode" role="group" aria-label="First player" data-testid="seating-mode">
            <span className="nx-label">First player</span>
            <span className="nx-segs">
              {(["pod", "random", "seats"] as const).map((m) => (
                <button key={m} className={mode === m ? "on" : ""} aria-pressed={mode === m} title={TURN_ORDER_LABEL[m]} disabled={busy}
                  onClick={() => mode !== m && void onRun(() => updateLobbySettings(lobby.game.id, { turn_order: m }))}>
                  {MODE_NAME[m]}
                </button>
              ))}
            </span>
          </div>
        )}
        {lobby.is_host && seated.length > 1 && <p className="nx-hint">Drag a seat by its grip, or use its arrows, to change places.</p>}
      </div>
      <div className="nx-foot">
      <dl className="house-rules">
        <div><dt>Life</dt><dd>{s.starting_life ?? 40}</dd></div>
        <div className={lobby.mulligan?.needs_definition ? "warn" : undefined}>
          <dt>Mulligan</dt>
          <dd>{lobby.mulligan?.display_name ?? MULLIGAN_LABEL[s.mulligan_rule] ?? s.mulligan_rule}{lobby.mulligan?.needs_definition ? " (not defined yet)" : ""}</dd>
        </div>
        <div title={DECK_PRIVACY_HINT[s.deck_privacy]}><dt>Decks</dt><dd>{DECK_PRIVACY_LABEL[s.deck_privacy]}</dd></div>
        <div><dt>Automation</dt><dd>{AUTOMATION_NAME[level]}</dd></div>
        {level === "off" && <div><dt>Response helper</dt><dd>{s.priority_helper === "simple" ? "On" : "Off"}</dd></div>}
      </dl>
      {lobby.is_host && (
        <div className="nx-host">
          <button className="tt-btn" onClick={onSettings}><Icon name="gear" size={15} />Table settings</button>
        </div>
      )}
      </div>
    </section>
  );
}

/**
 * The seat preview: the table in miniature, seated as the 3D table will seat it (the viewer nearest, turn order clockwise),
 * the first player ringed when it is known.
 */
function MiniTable({ lobby, order, first, d20 }: { lobby: LobbyView; order: string[]; first: string | null; d20: boolean }) {
  const W = 156;
  const H = 108;
  const top = 24;
  const bottom = H - 24;
  const placed = miniSeats(order, lobby.viewer);
  const seat = (id: string) => lobby.seats.find((x) => x.id === id);
  const names = order.map((id) => seat(id)?.name ?? id).join(", ");
  return (
    <svg className="mini-table" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={order.length ? `Seating, clockwise: ${names}` : "Nobody is seated yet"}>
      <rect className="mt-rim" x={8} y={top} width={W - 16} height={bottom - top} rx={18} />
      <rect className="mt-felt" x={13} y={top + 5} width={W - 26} height={bottom - top - 10} rx={14} />
      <g className="mt-turn" transform={`translate(${W / 2} ${H / 2})`}>
        <path d="M -9.6 -11.5 A 15 15 0 1 1 -14.6 3.4" />
        <path d="M -14.6 3.4 l -1.5 4.8 M -14.6 3.4 l 3.4 3.7" />
        {d20 && <path className="mt-die" d="M 0 -8 L 7 -4 L 7 4 L 0 8 L -7 4 L -7 -4 Z M 0 -8 L -4.5 3 L 4.5 3 Z M -7 4 L -4.5 3 M 7 4 L 4.5 3 M 0 8 L -4.5 3 M 0 8 L 4.5 3" />}
      </g>
      {placed.map((p) => {
        const x = seat(p.id);
        if (!x) return null;
        const cx = 0.5 * W + (p.x - 0.5) * W * 0.95;
        const cy = p.y ? bottom : top;
        return (
          <g key={p.id} className={`mt-seat ${p.id === lobby.viewer ? "me" : ""}`}>
            {p.id === first && <circle cx={cx} cy={cy} r={15} className="mt-first" />}
            <circle cx={cx} cy={cy} r={11.5} fill={x.color} className="mt-chip" />
            <text x={cx} y={cy + 4.2} fill={inkOn(x.color)}>{x.name.slice(0, 1).toUpperCase()}</text>
          </g>
        );
      })}
    </svg>
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

/** Drop handlers for a seat the host can drag another seat onto. */
function dropProps(arranging: Arranging | null) {
  if (!arranging) return {};
  return {
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(SEAT_DRAG)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (!arranging.over) arranging.setOver(true);
    },
    onDragLeave: (e: React.DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) arranging.setOver(false); },
    onDrop: (e: React.DragEvent) => {
      const from = e.dataTransfer.getData(SEAT_DRAG);
      arranging.setOver(false);
      if (!from) return;
      e.preventDefault();
      arranging.dropOn(from);
    },
  };
}

/** A taken seat: the player's name plate, their commander on the felt (lit once they're ready) and their deck. */
function SeatPlinth({ seat, mine, lobby, busy, onChoose, onRun, arranging, own, onPick }: {
  seat: LobbySeat;
  mine: boolean;
  lobby: LobbyView;
  busy: boolean;
  onChoose: () => void;
  onRun: (fn: () => Promise<unknown>) => Promise<void>;
  arranging: Arranging | null;
  /** the decks this player brought (their own seat only), one click each */
  own: OwnDecks | null;
  onPick: (deck: OwnDeck) => void;
}) {
  const gameId = lobby.game.id;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(seat.name);
  const deck = seat.deck;
  const state = seat.ready ? "ready" : deck ? "deck" : "choosing";
  const number = seat.id.slice(1);

  const cmdId = deck?.commander_ids?.[0] ?? null;
  const cov = deck?.coverage;
  const covTotal = cov ? cov.FULL + cov.PARTIAL + cov.REVIEW + cov.MANUAL : 0;
  const title = deck?.commanders?.length ? deck.commanders.join(" & ") : deck ? (deck.name ?? "Private deck") : null;
  return (
    <section className={`plinth ${state} ${mine ? "mine" : ""} ${arranging?.over ? "drop-target" : ""}`}
      style={{ ["--seat" as string]: seat.color }} data-testid={`seat-${seat.id}`} aria-label={`Seat ${number}: ${seat.name}`}
      {...dropProps(arranging)}>
      <header className="pl-plate">
        <SeatChip seat={seat} text={number} mine={mine} onColor={(color) => void onRun(() => setLobbyProfile(gameId, { color }))} />
        <div className="pl-who">
          <h2 className="pl-head">
          {mine && editing ? (
            <form className="seat-name-edit" onSubmit={(e) => {
              e.preventDefault();
              setEditing(false);
              if (name.trim() && name.trim() !== seat.name) void onRun(() => setLobbyProfile(gameId, { name: name.trim() }));
            }}>
              <input autoFocus value={name} maxLength={40} aria-label="Your name" onChange={(e) => setName(e.target.value)}
                onBlur={(e) => e.currentTarget.form?.requestSubmit()} />
            </form>
          ) : mine ? (
            <button className="pl-name" title="Rename" onClick={() => { setName(seat.name); setEditing(true); }}>{seat.name}</button>
          ) : (
            <span className="pl-name">{seat.name}</span>
          )}
          </h2>
          <span className="pl-tags">
            <span>Seat {number}</span>
            {seat.host && <span>Host</span>}
            {mine && <span className="you">You</span>}
            {!seat.connected && <span className="away">Not connected</span>}
          </span>
        </div>
        {seat.connected && <span className="presence on" role="img" aria-label="Connected" title="Connected" />}
        {(arranging || (lobby.is_host && !seat.host)) && (
          <span className="pl-tools">
            {arranging && (
              <span className="seat-move" role="group" aria-label={`Move ${seat.name}`}>
                <button className="tt-icon" disabled={busy || !arranging.earlier} onClick={() => arranging.earlier?.()}
                  title={`Move ${seat.name} one seat earlier`} aria-label={`Move ${seat.name} one seat earlier`} data-testid={`seat-earlier-${seat.id}`}>
                  <Icon name="left" size={15} />
                </button>
                <span className="seat-grip" draggable={!busy} title={`Drag ${seat.name} onto another seat`} aria-hidden
                  onDragStart={(e) => { e.dataTransfer.setData(SEAT_DRAG, seat.id); e.dataTransfer.effectAllowed = "move"; }}
                  onDragEnd={() => arranging.setOver(false)}>
                  <Icon name="grip" size={15} />
                </span>
                <button className="tt-icon" disabled={busy || !arranging.later} onClick={() => arranging.later?.()}
                  title={`Move ${seat.name} one seat later`} aria-label={`Move ${seat.name} one seat later`} data-testid={`seat-later-${seat.id}`}>
                  <Icon name="right" size={15} />
                </button>
              </span>
            )}
            {lobby.is_host && !seat.host && (
              <button className="tt-icon pl-kick" title={`Remove ${seat.name} from the table`} aria-label={`Remove ${seat.name} from the table`} onClick={() => {
                if (window.confirm(`Remove ${seat.name} from the table?`)) void onRun(() => kickFromLobby(gameId, seat.id));
              }}><Icon name="close" size={14} /></button>
            )}
          </span>
        )}
      </header>

      <div className={`pl-art ${deck ? "" : "empty"}`}>
        {cmdId ? <CommanderArt id={cmdId} /> : deck ? <CommanderArt back /> : (
          <span className="pl-slot">
            {mine ? (
              <button className="tt-btn brass pl-choose" disabled={busy} onClick={onChoose} data-testid="choose-deck">
                <Icon name="cards" size={16} />Choose deck
              </button>
            ) : <Icon name="cards" size={28} />}
          </span>
        )}
        <span className={`pl-status ${state}`} data-testid={`seat-status-${seat.id}`}>
          {state === "ready" ? <><Icon name="check" size={14} />Ready</> : state === "deck" ? "Not ready" : mine ? "No deck yet" : "Choosing a deck…"}
        </span>
      </div>

      <div className="pl-deck">
        {deck ? (
          <>
            <p className="pl-cmdr" title={title ?? undefined}>{title}</p>
            {(deck.commanders?.length || deck.color_identity) && (
              <p className="pl-sub">
                {deck.commanders?.length && deck.name ? <span className="pl-deckname">{deck.name}</span> : null}
                {deck.color_identity && <ColorPips colors={deck.color_identity} />}
              </p>
            )}
            <p className="pl-facts">
              <span><b>{deck.card_count}</b> cards</span>
              {cov && covTotal > 0 && (
                <span title={`FULL ${cov.FULL} · PARTIAL ${cov.PARTIAL} · REVIEW ${cov.REVIEW} · MANUAL ${cov.MANUAL}`} data-testid={`coverage-${seat.id}`}>
                  <b>{Math.round((cov.FULL / covTotal) * 100)}%</b> automated
                </span>
              )}
              {!mine && !!deck.warning_count && (
                <span className="pl-checks" title={deck.warnings?.map((w) => w.message).join("\n")}>
                  <WarnGlyph />{deck.warning_count} deck check{deck.warning_count === 1 ? "" : "s"}
                </span>
              )}
            </p>
            {mine && seat.queued && !seat.ready && (
              <p className="seat-queued" data-testid="queued-deck">
                Next deck queued: <b>{deck.commanders?.length ? deck.commanders.join(" & ") : deck.name}</b>. Ready to use it, or change it.
              </p>
            )}
            {mine && deck.report && deck.report.unresolved.length > 0 && (
              <p className="pl-warn" title={deck.report.unresolved.map((u) => u.name ?? u.line).join("\n")}>
                <WarnGlyph />Not in this table's card database, so they play as text proxies:{" "}
                {deck.report.unresolved.slice(0, 6).map((u) => u.name ?? u.line).join(", ")}{deck.report.unresolved.length > 6 ? ` and ${deck.report.unresolved.length - 6} more` : ""}
              </p>
            )}
            {mine && deck.warnings && deck.warnings.length > 0 && (
              <details className="deck-checks" data-testid="deck-checks">
                <summary>
                  <WarnGlyph />{deck.warning_count ? `${deck.warning_count} deck check${deck.warning_count === 1 ? "" : "s"}` : "Notes"} — you can play anyway
                </summary>
                <ul>{deck.warnings.map((w, i) => <li key={i} className={w.level}>{w.message}</li>)}</ul>
              </details>
            )}
          </>
        ) : (
          mine && own ? <OwnDeckPicks own={own} busy={busy} onPick={onPick} onMore={onChoose} /> : (
            <p className="pl-empty">{mine ? "Bring any Commander deck: pick one you saved, paste a list or import it." : `${seat.name} is choosing a deck.`}</p>
          )
        )}
      </div>

      {(mine && deck) || (!mine && deck?.list) ? (
        <div className="pl-actions">
          {mine && deck && (
            <>
              <button className="tt-btn" disabled={busy} onClick={onChoose} data-testid="choose-deck">Change deck</button>
              <button className="tt-btn ghost" disabled={busy} onClick={() => void onRun(() => clearLobbyDeck(gameId))}>Clear</button>
            </>
          )}
          {!mine && deck?.list && <DeckListPeek list={deck.list} />}
        </div>
      ) : null}
    </section>
  );
}

/** -- bring my decks -- the decks this player brought, right on their seat: commander art, one click to play one. */
function OwnDeckPicks({ own, busy, onPick, onMore }: { own: OwnDecks; busy: boolean; onPick: (d: OwnDeck) => void; onMore: () => void }) {
  const shown = own.decks.slice(0, 4);
  return (
    <div className="pl-own" data-testid="own-decks">
      <p className="pl-own-head">{own.label}</p>
      <ul className="pl-own-grid">
        {shown.map((d) => (
          <li key={d.key}>
            <button className="pl-own-deck" disabled={busy} onClick={() => onPick(d)} aria-label={`Use “${d.name}”`}
              title={d.commanders.length ? `${d.name}: ${d.commanders.join(" & ")}` : d.name}>
              <span className="pl-own-art">{d.cover ? <CommanderArt id={d.cover} /> : <CommanderArt back />}</span>
              <span className="pl-own-name">{d.commanders.length ? d.commanders.join(" & ") : d.name}</span>
              {d.commanders.length > 0 && <span className="pl-own-sub">{d.name}</span>}
            </button>
          </li>
        ))}
      </ul>
      {own.decks.length > shown.length && (
        <button className="tt-link pl-own-more" onClick={onMore}>All {own.decks.length} of your decks…</button>
      )}
    </div>
  );
}

/** An open seat: an empty chair at the table, with the way to fill it from where you are. */
function OpenSeat({ seat, lobby, busy, onRun, invite, arranging }: {
  seat: LobbySeat;
  lobby: LobbyView;
  busy: boolean;
  onRun: (fn: () => Promise<unknown>) => Promise<void>;
  invite: string | null;
  arranging: Arranging | null;
}) {
  const gameId = lobby.game.id;
  const iAmSeated = lobby.seats.some((s) => s.id === lobby.viewer);
  const watcher = lobby.viewer === SPECTATOR && !lobby.is_host && !!lobby.game.code;
  const number = seat.id.slice(1);
  return (
    <section className={`open-seat ${arranging?.over ? "drop-target" : ""}`} data-testid={`seat-${seat.id}`} aria-label={`Seat ${number}: open`}
      {...dropProps(arranging)}>
      <span className="os-chair"><ChairGlyph /><b aria-hidden>{number}</b></span>
      <span className="os-text">
        <b>Seat {number}</b>
        <span>{watcher ? "Open: take it to play" : lobby.is_host ? "Open seat" : "Waiting for a player"}</span>
      </span>
      {(lobby.is_host && invite) || iAmSeated || watcher ? (
        <span className="os-actions">
          {lobby.is_host && invite && <CopyButton text={invite} label={<><LinkGlyph />Invite</>} done="Link copied" className="os-invite" />}
          {iAmSeated && (
            <button className="tt-btn ghost" disabled={busy} onClick={() => void onRun(() => changeLobbySeat(gameId, seat.id))}>Sit here</button>
          )}
          {watcher && (
            <button className="tt-btn brass" disabled={busy} data-testid={`take-seat-${seat.id}`}
              title="Take this seat (a deck you queued while watching comes with you)"
              onClick={() => void onRun(() => takeSeat(lobby, seat.id))}>Take this seat</button>
          )}
        </span>
      ) : null}
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

function DeckListPeek({ list }: { list: { section: string; quantity: number; name: string }[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="tt-btn ghost" onClick={() => setOpen(true)}>View list</button>
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

type Source = "brought" | "table" | "mine" | "archidekt" | "paste" | "file";

/** Put a deck in this seat: the lobby's personal import (deck checks, privacy), remembered in My decks when asked. */
async function bringDeck(gameId: string, body: LobbyDeckBody, opts: { remember: boolean; companion?: string }): Promise<LobbyView> {
  const imported = await importPersonalDeck(gameId, body);
  if (opts.remember || body.deck_id) rememberMyDeck(imported.name, body, imported.commanders, imported);
  const res = await submitLobbyDeck(gameId, { name: imported.name, text: imported.text,
    collection: personalCollection(), ...(opts.companion ? { companion_id: opts.companion } : {}) });
  const mine = res.seats.find((s) => s.id === res.viewer)?.deck;
  toast(`Deck ready: ${mine?.name ?? "deck"} (${mine?.card_count ?? 0} cards)`);
  return res;
}

function ChooseDeck({ gameId, brought, onClose, onDone }: {
  gameId: string;
  /** -- bring my decks -- the library this player's own Fyodor sent with their join: offered first */
  brought: BroughtLibrary | null;
  onClose: () => void;
  onDone: (l: LobbyView) => void;
}) {
  const [companion, setCompanion] = useState("");
  const [hostDecks, setHostDecks] = useState<DeckSummary[] | null>(null);
  const [saved, setSaved] = useState<MyDeck[]>(() => myDecks());
  const [source, setSource] = useState<Source>(brought ? "brought" : saved.length ? "mine" : "paste");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<{ name: string; body: LobbyDeckBody } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [keepBrought, setKeepBrought] = useState(false);

  useEffect(() => {
    // The host's library is offered only on the host computer (the server enforces this too).
    listDecks().then(
      (d) => {
        setHostDecks(d);
        if (!saved.length && d.length) setSource((s) => (s === "brought" ? s : "table"));
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
      onDone(await bringDeck(gameId, body, { remember, companion }));
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
    ...(brought ? ([["brought", `Your decks, from ${brought.from ?? "your computer"}`]] as [Source, string][]) : []),
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
        {source === "brought" && brought && (
          <div className="deck-pick-list" data-testid="brought-decks">
            <p className="hint">Your decks from {brought.from ?? "your computer"}. Only you see this list; the table sees the deck you choose as its deck privacy allows.</p>
            {brought.unknown.length > 0 && (
              <p className="pl-warn" data-testid="brought-unknown">
                <WarnGlyph />This table's card database couldn't take {brought.unknown.length === 1 ? "a card" : `${brought.unknown.length} cards`} from {brought.from ?? "your computer"}:{" "}
                {brought.unknown.slice(0, 8).map((u) => `${u.name} (${u.why})`).join("; ")}. They play as text proxies.
              </p>
            )}
            {brought.decks.map((d, i) => (
              <button key={i} className="deck-pick brought-pick" disabled={busy} onClick={() => void submit({ name: d.name, text: d.text }, keepBrought)}>
                <span className="brought-art" aria-hidden>{d.cover_id ? <CommanderArt id={d.cover_id} /> : <CommanderArt back />}</span>
                <b>{d.name}</b>
                <span className="hint">{d.commanders.join(" & ") || "Deck list"}</span>
              </button>
            ))}
            <label className="row-check brought-keep">
              <input type="checkbox" checked={keepBrought} onChange={(e) => setKeepBrought(e.target.checked)} />
              <span>Also keep the one I choose in My decks on this browser</span>
            </label>
          </div>
        )}
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
            <p className="hint" data-testid="my-decks-address">
              My decks are kept in this browser for <b>{window.location.host}</b>: another address (another host, or this one after its
              address changes) has its own list. Export My decks to carry them there, and import the file at the new address.
            </p>
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
        <TablePermissionsSetting value={draft.card_permissions} onChange={(v) => set({ card_permissions: v })} />
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
