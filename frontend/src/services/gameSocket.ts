/** Live connection to a game room with automatic reconnection. */
import type { GameView } from "../types/game";

export type ConnStatus = "connecting" | "open" | "reconnecting" | "closed";

interface Handlers {
  onState: (view: GameView) => void;
  onStatus: (status: ConnStatus, detail?: string) => void;
  onClosedByServer: (reason: string) => void;
}

type ServerMessage =
  | { type: "state"; view: GameView }
  | { type: "ack"; id: number | null }
  | { type: "error"; id?: number | null; message: string }
  | { type: "pong"; id: number | null }
  | { type: "closed" };

const FATAL_CODES = new Set([4403, 4404]);

export class GameConnection {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: () => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
  private retry = 0;
  private stopped = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;

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
      this.retry += 1;
      this.handlers.onStatus("reconnecting");
      setTimeout(() => !this.stopped && this.connect(), Math.min(10000, 400 * 2 ** Math.min(this.retry, 5)));
    };
  }

  close(): void {
    this.stopped = true;
    this.failPending("Closed");
    this.ws?.close();
    this.ws = null;
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
      case "state":
        this.handlers.onState(msg.view);
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
