/** Live connection to a game room with automatic reconnection. */
import type { GameView, LobbyView } from "../types/game";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";

interface Handlers {
  /** `replace`: an authoritative resync — replace local state, never merge. */
  onState: (view: GameView, replace: boolean) => void;
  onLobby: (lobby: LobbyView) => void;
  onStatus: (status: ConnStatus, detail?: string) => void;
  onClosedByServer: (reason: string) => void;
  /** How many actions are waiting to reach the table (sent again after a reconnect). */
  onOutbox?: (count: number) => void;
  /** A transient social signal (a nudge to you, a spectator's reaction); never game state. */
  onSignal?: (signal: Signal) => void;
}

export interface Signal {
  kind: "nudge" | "react" | "ping";
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
  | { type: "state"; view: GameView; revision?: number; resync?: boolean }
  | { type: "lobby"; lobby: LobbyView }
  | { type: "kicked" }
  | { type: "ack"; id: number | null; status?: "ACCEPTED" | "ALREADY_APPLIED" }
  | { type: "error"; id?: number | null; message: string; status?: "REJECTED" }
  | { type: "pong"; id: number | null }
  | { type: "closed" }
  | ({ type: "signal" } & Signal);

const FATAL_CODES = new Set([4403, 4404]);
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

  constructor(
    private readonly gameId: string,
    private params: { token?: string | null; viewer?: string | null },
    private readonly handlers: Handlers,
  ) {}

  connect(): void {
    this.stopped = false;
    const q = new URLSearchParams();
    if (this.params.token) q.set("token", this.params.token);
    if (this.params.viewer) q.set("viewer", this.params.viewer);
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    this.revision = 0; // a fresh connection starts with a full snapshot
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/games/${encodeURIComponent(this.gameId)}?${q}`);
    this.ws = ws;
    this.handlers.onStatus(this.retry ? "reconnecting" : "connecting");
    ws.onopen = () => {
      this.retry = 0;
      this.handlers.onStatus("open");
      this.pingTimer = setInterval(() => this.raw({ type: "ping" }), 20000);
      this.flushOutbox(); // the server applies each queued action once (client_action_id)
    };
    ws.onmessage = (ev) => this.onMessage(ev.data as string);
    ws.onclose = (ev) => {
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.failPending("Connection lost");
      if (this.stopped) return;
      if (FATAL_CODES.has(ev.code)) {
        this.stopped = true;
        this.handlers.onStatus("closed", ev.reason || "Refused");
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

  /** Change the viewing seat (local hot-seat games only). */
  setViewer(viewer: string): void {
    this.params = { ...this.params, viewer };
    this.raw({ type: "view", viewer });
  }

  request(message: Record<string, unknown>): Promise<void> {
    const id = this.nextId++;
    return new Promise<void>((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
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
   * ALREADY_APPLIED, so it is never applied twice.
   */
  requestAction(message: Record<string, unknown>): Promise<void> {
    const cid = newClientActionId();
    return new Promise<void>((resolve, reject) => {
      this.outbox.set(cid, { message: { ...message, client_action_id: cid }, resolve, reject, deadline: Date.now() + OUTBOX_TTL, wireId: null });
      this.handlers.onOutbox?.(this.outbox.size);
      this.sendQueued(cid);
    });
  }

  private sendQueued(cid: string): void {
    const q = this.outbox.get(cid);
    if (!q || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
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

  private raw(message: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
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
        if (msg.resync || !this.revision) {
          this.revision = rev;
          this.handlers.onState(msg.view, !!msg.resync);
          break;
        }
        if (rev <= this.revision) break; // stale / out of order: the newer state is already here
        const gap = rev > this.revision + 1;
        this.revision = rev;
        this.handlers.onState(msg.view, false);
        if (gap) this.resync(); // missed an update: ask for the authoritative snapshot
        break;
      }
      case "lobby":
        this.handlers.onLobby(msg.lobby);
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
      case "signal":
        this.handlers.onSignal?.(msg);
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
