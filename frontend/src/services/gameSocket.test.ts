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
  drop() {
    this.readyState = 3;
    this.onclose?.({ code: 1006, reason: "" });
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
    const p = conn.requestAction({ type: "action", action: { type: "tap", card_ids: ["x"] } });
    const sent = FakeSocket.last!.sent.find((m) => m.type === "action")!;
    FakeSocket.last!.reply({ type: "error", id: sent.id, status: "REJECTED", message: "No such card" });
    await expect(p).rejects.toThrow("No such card");
  });
});
