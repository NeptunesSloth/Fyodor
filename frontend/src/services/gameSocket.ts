/** Live connection to a game room with automatic reconnection. */
import type { GameView, LobbyView } from "../types/game";
import { refreshImageless } from "../state/cardCache";
import { applyPatch, type Patch } from "./viewDelta";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";

interface Handlers {
  /**
   * `replace`: an authoritative resync — replace local state, never merge. -- view deltas -- may return the view it keeps (the same
   * content, merged into its own objects): the next patch is applied to that, so unchanged parts stay the very objects shown.
   */
  onState: (view: GameView, replace: boolean) => GameView | void;
  onLobby: (lobby: LobbyView) => void;
  onStatus: (status: ConnStatus, detail?: string) => void;
  onClosedByServer: (reason: string) => void;
  /** How many actions are waiting to reach the table (sent again after a reconnect). */
  onOutbox?: (count: number) => void;
  /** A transient social signal (a nudge to you, a spectator's reaction); never game state. */
  onSignal?: (signal: Signal) => void;
  /** -- live cursors -- another seated player's pointer over the 3D table (table3d/cursors.ts); never game state. */
  onCursor?: (cursor: CursorWire) => void;
  /**
   * -- resolving progress -- a long automatic chain inside one action, as it goes: the table part way through (built for this viewer
   * like every update; null when the server sends the count only) and how far it got. Display only: the action's own update follows.
   */
  onInterim?: (view: GameView | null, progress: ResolvingProgress) => void;
}

/** -- resolving progress -- objects the engine resolved so far in the action being worked out, the ones left, and whose action it is. */
export interface ResolvingProgress {
  resolved: number;
  left: number;
  by: string;
}

/** -- live cursors -- as the server relays it: the sender's seat, and a point on a seat's battlefield (virtual units). */
export type CursorWire = { from: string; gone: true } | { from: string; gone?: false; player: string; x: number; y: number; card?: string; cx?: number; cy?: number };

export interface Signal {
  /** "response": "wait, I have a response!" (``on``); "flip": (╯°□°)╯︵ ┻━┻, cosmetic (``concede``: with a concession) */
  kind: "nudge" | "react" | "ping" | "response" | "flip";
  on?: boolean;
  concede?: boolean;
  from: string | null;
  from_name: string;
  to?: string;
  emoji?: string;
  /** a ping: a card everyone can see, or a spot (virtual x/y) on a player's battlefield */
  card?: string;
  player?: string;
  x?: number;
  y?: number;
}

type ServerMessage =
  | { type: "state"; view: GameView; revision?: number; resync?: boolean; vseq?: number }
  | { type: "delta"; revision?: number; base: number; vseq: number; patch: Patch }
  | { type: "interim"; view?: GameView; revision: number; progress: ResolvingProgress }
  | { type: "lobby"; lobby: LobbyView }
  | { type: "kicked" }
  | { type: "art" }
  | { type: "ack"; id: number | null; status?: "ACCEPTED" | "ALREADY_APPLIED" }
  | { type: "error"; id?: number | null; message: string; status?: "REJECTED" }
  | { type: "pong"; id: number | null }
  | { type: "ping" } // the server's heartbeat: answered with a pong
  | { type: "closed" }
  | ({ type: "signal" } & Signal)
  | ({ type: "cursor" } & CursorWire);

// The codes the page can see are the ones the server closes with after accepting the socket: 4403, no seat here (every auth failure);
// 4429 for a fifth socket of one seat; 4408, silent too long. A refusal before accept (4400 a Host the server does not answer to, 4403
// a cross-site Origin, 4429 too many sockets from one address) is an HTTP 403 to the browser, which reports 1006 like a dropped
// connection: those reconnect through the backoff below (a page whose Host is refused cannot load in the first place). 4400 and 4404
// (no such game, from older servers) stay fatal for a server that sends them after accept. Only a server message resets the backoff.
const FATAL_CODES = new Set([4400, 4403, 4404]);
/** What a refused seat says, whatever reason the server gave (it gives the same one for every refusal). */
export const SEAT_REFUSED = "Your seat is no longer valid here. Join again.";
const OUTBOX_TTL = 45000; // an action waits this long for the table to come back

interface Queued {
  message: Record<string, unknown>;
  resolve: () => void;
  reject: (e: Error) => void;
  deadline: number;
  wireId: number | null;
}

export function newClientActionId(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return "a" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
const RETRY_NOW = 4000; // the host asked this client to reconnect

export class GameConnection {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: () => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private retry = 0;
  private stopped = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  /** Actions with a client_action_id, kept until the server answers (survive reconnects). */
  private outbox = new Map<string, Queued>();
  /** Last authoritative revision applied (0 = none yet). */
  revision = 0;
  /** A hot-seat view switch is on its way: its answer replaces the table shown. */
  private seatSwitch = false;
  /**
   * -- view deltas (services/viewDelta.ts) -- the last view this connection was sent (as kept by the store) and its number on this
   * connection: each update after the first full view is a patch from it. A patch from any other view, or one that doesn't fit, asks
   * for the whole view once (`resyncAsked` until it comes).
   */
  private base: GameView | null = null;
  private vseq = 0;
  private resyncAsked = false;
  /** The server has answered this socket (its first message follows a good `auth`): until then nothing else is sent on it. */
  private authed = false;

  constructor(
    private readonly gameId: string,
    private params: { token?: string | null; viewer?: string | null },
    private readonly handlers: Handlers,
  ) {}

  connect(): void {
    this.stopped = false;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    this.revision = 0; // a fresh connection starts with a full snapshot
    this.base = null;
    this.vseq = 0;
    this.resyncAsked = false;
    this.authed = false;
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/games/${encodeURIComponent(this.gameId)}`); // (no token in the address)
    this.ws = ws;
    this.handlers.onStatus(this.retry ? "reconnecting" : "connecting");
    ws.onopen = () => {
      // the seat token travels in the first message of every connection, reconnects included, never in the address
      // (-- view deltas -- `deltas`: a server without them sends whole views, as before)
      ws.send(JSON.stringify({ type: "auth", token: this.params.token ?? null, viewer: this.params.viewer ?? null, deltas: true }));
    };
    ws.onmessage = (ev) => {
      if (!this.authed) {
        this.authed = true; // the server's first word: the seat is good
        this.retry = 0;
        this.handlers.onStatus("open");
        this.pingTimer = setInterval(() => this.raw({ type: "ping" }), 20000);
        this.flushOutbox(); // the server applies each queued action once (client_action_id)
      }
      this.onMessage(ev.data as string);
    };
    ws.onclose = (ev) => {
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.failPending("Connection lost");
      if (this.stopped) return;
      if (FATAL_CODES.has(ev.code)) {
        this.stopped = true;
        this.handlers.onStatus("closed", ev.code === 4403 ? SEAT_REFUSED : ev.reason || "Refused");
        return;
      }
      this.retry = ev.code === RETRY_NOW ? 0 : this.retry + 1;
      this.handlers.onStatus("reconnecting");
      setTimeout(() => !this.stopped && this.connect(), ev.code === RETRY_NOW ? 150 : Math.min(10000, 400 * 2 ** Math.min(this.retry, 5)));
    };
  }

  close(): void {
    this.stopped = true;
    this.failPending("Closed");
    for (const q of this.outbox.values()) q.reject(new Error("Closed"));
    this.outbox.clear();
    this.handlers.onOutbox?.(0);
    this.ws?.close();
    this.ws = null;
  }

  /** Ask the server for a fresh authoritative view (it replaces local state). */
  resync(): void {
    this.raw({ type: "resync" });
  }

  /** -- view deltas -- a patch didn't fit: the whole view once (patches after it are dropped until it comes). */
  private resyncForDelta(): void {
    if (this.resyncAsked) return;
    this.resyncAsked = true;
    this.resync();
  }

  /** -- view deltas -- hand a whole view on; it (as the store keeps it) is what the next patch applies to. */
  private deliver(view: GameView, replace: boolean, vseq: number | undefined): void {
    const kept = this.handlers.onState(view, replace);
    if (vseq != null) {
      this.base = kept ?? view;
      this.vseq = vseq;
    }
  }

  /** Change the viewing seat (local hot-seat games only). */
  setViewer(viewer: string): void {
    this.params = { ...this.params, viewer };
    // the server answers with the table as the new seat sees it, at the revision already here: taken as a fresh snapshot (with the
    // revision kept, it read as stale and the switch showed only with the next update)
    this.revision = 0;
    this.seatSwitch = true; // (and it replaces the table shown: another seat's view, not an update of this one)
    this.raw({ type: "view", viewer });
  }

  request(message: Record<string, unknown>): Promise<void> {
    const id = this.nextId++;
    return new Promise<void>((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.authed) {
        reject(new Error("Not connected — reconnecting…"));
        return;
      }
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("The server did not answer in time"));
      }, 10000);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify({ ...message, id }));
    });
  }

  /**
   * Send a game action safely: it carries a client_action_id, waits in an outbox while the
   * connection is down and is sent again after a reconnect. The server answers a repeat with
   * ALREADY_APPLIED, so it is never applied twice. It also carries the revision of the view it was
   * requested on (kept through a resend): the server refuses it when the turn clock already acted for
   * this player in a newer view.
   */
  requestAction(message: Record<string, unknown>): Promise<void> {
    const cid = newClientActionId();
    return new Promise<void>((resolve, reject) => {
      const queued = { ...message, client_action_id: cid, seen_revision: this.revision };
      this.outbox.set(cid, { message: queued, resolve, reject, deadline: Date.now() + OUTBOX_TTL, wireId: null });
      this.handlers.onOutbox?.(this.outbox.size);
      this.sendQueued(cid);
    });
  }

  private sendQueued(cid: string): void {
    const q = this.outbox.get(cid);
    if (!q || !this.ws || this.ws.readyState !== WebSocket.OPEN || !this.authed) return;
    const id = this.nextId++;
    q.wireId = id;
    this.ws.send(JSON.stringify({ ...q.message, id }));
  }

  private flushOutbox(): void {
    const now = Date.now();
    for (const [cid, q] of this.outbox) {
      if (q.deadline < now) {
        this.outbox.delete(cid);
        q.reject(new Error("Could not reach the table — the action was not sent"));
      } else this.sendQueued(cid);
    }
    this.handlers.onOutbox?.(this.outbox.size);
  }

  /** Answer for a queued action (by its wire id): true when it was one of ours. */
  private settleQueued(id: number | null, error: string | null): boolean {
    if (id == null) return false;
    for (const [cid, q] of this.outbox) {
      if (q.wireId !== id) continue;
      this.outbox.delete(cid);
      this.handlers.onOutbox?.(this.outbox.size);
      if (error) q.reject(new Error(error));
      else q.resolve();
      return true;
    }
    return false;
  }

  /** -- live cursors -- my pointer over the 3D table, or that it left (fire and forget: never queued, never retried). */
  sendCursor(spot: { player: string; x: number; y: number; card?: string; cx?: number; cy?: number } | { gone: true }): void {
    this.raw({ type: "cursor", ...spot });
  }

  private raw(message: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN && this.authed) this.ws.send(JSON.stringify(message));
  }

  private onMessage(data: string): void {
    let msg: ServerMessage;
    try {
      msg = JSON.parse(data) as ServerMessage;
    } catch {
      console.error("Bad message from server");
      return;
    }
    switch (msg.type) {
      case "state": {
        const rev = msg.revision ?? msg.view.game.revision ?? 0;
        if (msg.vseq != null) {
          // -- view deltas -- numbered in the order this connection was sent them: an older one is already superseded
          if (msg.vseq <= this.vseq) break;
          this.resyncAsked = false;
          this.revision = rev;
          const replace = !!msg.resync || this.seatSwitch;
          this.seatSwitch = false;
          this.deliver(msg.view, replace, msg.vseq);
          break;
        }
        if (msg.resync || !this.revision) {
          this.revision = rev;
          const replace = !!msg.resync || this.seatSwitch;
          this.seatSwitch = false;
          this.handlers.onState(msg.view, replace);
          break;
        }
        if (rev <= this.revision) break; // stale / out of order: the newer state is already here
        const gap = rev > this.revision + 1;
        this.revision = rev;
        this.handlers.onState(msg.view, false);
        if (gap) this.resync(); // missed an update: ask for the authoritative snapshot
        break;
      }
      case "delta": {
        // -- view deltas -- a patch from the view numbered `base`: anything else (a message missed, a patch that doesn't fit) → whole view
        if (!this.base || msg.base !== this.vseq) {
          this.resyncForDelta();
          break;
        }
        let view: GameView;
        try {
          view = applyPatch(this.base, msg.patch);
        } catch (e) {
          console.warn("View update did not fit, asking for the whole table:", e);
          this.resyncForDelta();
          break;
        }
        this.revision = msg.revision ?? view.game.revision ?? this.revision;
        // (during a seat switch: whichever seat this is, the switch's own whole view follows and replaces it)
        this.deliver(view, this.seatSwitch, msg.vseq);
        break;
      }
      case "interim":
        // -- resolving progress -- views on top of the last update only: none yet (a fresh connection's first message is its
        // snapshot), or a newer update already here (the action's own), and the frame is stale
        if (this.revision && msg.revision === this.revision) this.handlers.onInterim?.(msg.view ?? null, msg.progress);
        break;
      case "lobby":
        this.handlers.onLobby(msg.lobby);
        break;
      case "art": // new card images reached the host (a player's own Fyodor sent them): proxies may now have art
        refreshImageless();
        break;
      case "kicked":
        this.stopped = true;
        this.ws?.close();
        this.handlers.onClosedByServer("The host removed you from this table.");
        break;
      case "ack":
        if (!this.settleQueued(msg.id, null)) this.settle(msg.id, null);
        break;
      case "error":
        if (this.settleQueued(msg.id ?? null, msg.message)) break;
        if (msg.id != null && this.pending.has(msg.id)) this.settle(msg.id, msg.message);
        else console.warn("Server error:", msg.message);
        break;
      case "closed":
        this.stopped = true;
        this.handlers.onClosedByServer("The host closed this game.");
        break;
      case "pong":
        break;
      case "ping":
        this.raw({ type: "pong" }); // (only after auth, like every send: raw)
        break;
      case "signal":
        this.handlers.onSignal?.(msg);
        break;
      case "cursor":
        this.handlers.onCursor?.(msg);
        break;
    }
  }

  private settle(id: number | null, error: string | null): void {
    if (id == null) return;
    const p = this.pending.get(id);
    if (!p) return;
    clearTimeout(p.timer);
    this.pending.delete(id);
    if (error) p.reject(new Error(error));
    else p.resolve();
  }

  private failPending(reason: string): void {
    for (const [id, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(new Error(reason));
      this.pending.delete(id);
    }
  }
}
