import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameConnection } from "./gameSocket";

class FakeSocket {
  static OPEN = 1;
  static last: FakeSocket | null = null;
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number; reason: string }) => void) | null = null;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  reply(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop(code = 1006, reason = "") {
    this.readyState = 3;
    this.onclose?.({ code, reason });
  }
  /** The server's first message: the seat was accepted. */
  accept() {
    this.reply({ type: "pong", id: null });
  }
}

describe("game connection outbox", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("window", { location: { protocol: "http:", host: "table.local" } });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps an action through a dropped connection and sends it again with the same id", async () => {
    const outbox: number[] = [];
    const conn = new GameConnection("g1", { token: "t" }, { onState: () => {}, onLobby: () => {}, onStatus: () => {}, onClosedByServer: () => {}, onOutbox: (n) => outbox.push(n) });
    conn.connect();
    const first = FakeSocket.last!;
    first.open();
    first.accept();
    let done = false;
    const p = conn.requestAction({ type: "action", action: { type: "draw" } }).then(() => { done = true; });
    const sent = first.sent.find((m) => m.type === "action")!;
    expect(sent.client_action_id).toMatch(/^a[0-9a-f]{24}$/);
    first.drop(); // no answer: the connection died
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(1000); // reconnect
    const second = FakeSocket.last!;
    expect(second).not.toBe(first);
    second.open();
    second.accept();
    const resent = second.sent.find((m) => m.type === "action")!;
    expect(resent.client_action_id).toBe(sent.client_action_id);
    second.reply({ type: "ack", id: resent.id, status: "ALREADY_APPLIED" });
    await p;
    expect(done).toBe(true);
    expect(outbox.at(-1)).toBe(0);
  });

  it("reports a rejected action once", async () => {
    const conn = new GameConnection("g1", {}, { onState: () => {}, onLobby: () => {}, onStatus: () => {}, onClosedByServer: () => {} });
    conn.connect();
    FakeSocket.last!.open();
    FakeSocket.last!.accept();
    const p = conn.requestAction({ type: "action", action: { type: "tap", card_ids: ["x"] } });
    const sent = FakeSocket.last!.sent.find((m) => m.type === "action")!;
    FakeSocket.last!.reply({ type: "error", id: sent.id, status: "REJECTED", message: "No such card" });
    await expect(p).rejects.toThrow("No such card");
  });
});

describe("game connection authentication", () => {
  const handlers = (statuses: [string, string | undefined][] = []) => ({
    onState: () => {},
    onLobby: () => {},
    onStatus: (status: string, detail?: string) => statuses.push([status, detail]),
    onClosedByServer: () => {},
  });
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("window", { location: { protocol: "http:", host: "table.local" } });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("puts no token in the address and sends auth first on open", () => {
    const conn = new GameConnection("g1", { token: "secret-seat", viewer: "p2" }, handlers());
    conn.connect();
    const ws = FakeSocket.last!;
    expect(ws.url).toBe("ws://table.local/ws/games/g1");
    expect(ws.url).not.toContain("secret-seat");
    ws.open();
    expect(ws.sent).toEqual([{ type: "auth", token: "secret-seat", viewer: "p2", deltas: true }]);
  });

  it("sends nothing else until the server's first message, then sends what waited", async () => {
    const conn = new GameConnection("g1", { token: "t" }, handlers());
    conn.connect();
    const ws = FakeSocket.last!;
    ws.open();
    conn.resync();
    conn.sendCursor({ gone: true });
    void conn.requestAction({ type: "action", action: { type: "draw" } }).catch(() => {});
    await expect(conn.request({ type: "undo" })).rejects.toThrow("Not connected");
    vi.advanceTimersByTime(25000);
    expect(ws.sent.map((m) => m.type)).toEqual(["auth"]);
    ws.accept();
    expect(ws.sent.map((m) => m.type)).toEqual(["auth", "action"]);
  });

  it("sends auth first on every reconnect", async () => {
    const conn = new GameConnection("g1", { token: "t" }, handlers());
    conn.connect();
    FakeSocket.last!.open();
    FakeSocket.last!.accept();
    const first = FakeSocket.last!;
    first.drop();
    await vi.advanceTimersByTimeAsync(1000);
    const second = FakeSocket.last!;
    expect(second).not.toBe(first);
    second.open();
    expect(second.sent[0]).toEqual({ type: "auth", token: "t", viewer: null, deltas: true });
    expect(second.sent).toHaveLength(1);
  });

  it("stops on 4403 and says the seat is no longer valid, whatever reason came with it", async () => {
    const statuses: [string, string | undefined][] = [];
    const conn = new GameConnection("g1", { token: "t" }, handlers(statuses));
    conn.connect();
    const ws = FakeSocket.last!;
    ws.open();
    ws.drop(4403, "Not authorized");
    await vi.advanceTimersByTimeAsync(60000);
    expect(FakeSocket.last).toBe(ws); // no reconnect
    expect(statuses.at(-1)).toEqual(["closed", "Your seat is no longer valid here. Join again."]);
  });

  it("stops on 4400 as well", async () => {
    const statuses: [string, string | undefined][] = [];
    const conn = new GameConnection("g1", { token: "t" }, handlers(statuses));
    conn.connect();
    const ws = FakeSocket.last!;
    ws.open();
    ws.drop(4400, "Unknown host");
    await vi.advanceTimersByTimeAsync(60000);
    expect(FakeSocket.last).toBe(ws);
    expect(statuses.at(-1)).toEqual(["closed", "Unknown host"]);
  });
});
