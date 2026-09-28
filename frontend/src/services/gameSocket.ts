/** Live connection to a game room with automatic reconnection. */
import type { GameView, LobbyView } from "../types/game";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";

interface Handlers {
  /** `replace`: an authoritative resync — replace local state, never merge. */
  onState: (view: GameView, replace: boolean) => void;
  onLobby: (lobby: LobbyView) => void;
  onStatus: (status: ConnStatus, detail?: string) => void;
  onClosedByServer: (reason: string) => void;
}

type ServerMessage =
  | { type: "state"; view: GameView; revision?: number; resync?: boolean }
  | { type: "lobby"; lobby: LobbyView }
  | { type: "kicked" }
  | { type: "ack"; id: number | null }
  | { type: "error"; id?: number | null; message: string }
  | { type: "pong"; id: number | null }
  | { type: "closed" };

const FATAL_CODES = new Set([4403, 4404]);
const RETRY_NOW = 4000; // the host asked this client to reconnect

export class GameConnection {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: () => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private retry = 0;
  private stopped = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
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
        this.settle(msg.id, null);
        break;
      case "error":
        if (msg.id != null && this.pending.has(msg.id)) this.settle(msg.id, msg.message);
        else console.warn("Server error:", msg.message);
        break;
      case "closed":
        this.stopped = true;
        this.handlers.onClosedByServer("The host closed this game.");
        break;
      case "pong":
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
