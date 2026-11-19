import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameConnection } from "./gameSocket";
import { applyPatch, PatchError, type Patch } from "./viewDelta";
import type { GameView } from "../types/game";

function deepFreeze<T>(x: T): T {
  if (x && typeof x === "object") {
    Object.freeze(x);
    for (const v of Object.values(x as Record<string, unknown>)) deepFreeze(v);
  }
  return x;
}

describe("applyPatch", () => {
  const base = () =>
    deepFreeze({
      game: { seq: 1, revision: 3, night: { n: 1 } },
      cards: { a: { zone: "hand", tapped: false }, b: { zone: "lib" }, c: { zone: "bf" } },
      log: [{ seq: 0 }, { seq: 1 }, { seq: 2 }, { seq: 3 }],
      zones: { "p1:hand": ["a"] },
      gone: 1,
    });

  it("rebuilds the new view exactly and shares every unchanged part", () => {
    const old = base();
    const patch: Patch = {
      set: { rules: null },
      del: ["gone"],
      sub: {
        game: { set: { seq: 2, revision: 4 } },
        cards: { set: { d: { zone: "bf" }, a: { zone: "bf", tapped: true } }, del: ["b"], keys: ["d", "a", "c"] },
        zones: { set: { "p1:hand": [] } },
      },
      tail: { log: { drop: 2, add: [{ seq: 4 }] } },
    };
    const next = applyPatch(old, patch) as Record<string, any>;
    expect(JSON.stringify(next)).toBe(JSON.stringify({
      game: { seq: 2, revision: 4, night: { n: 1 } },
      cards: { d: { zone: "bf" }, a: { zone: "bf", tapped: true }, c: { zone: "bf" } },
      log: [{ seq: 2 }, { seq: 3 }, { seq: 4 }],
      zones: { "p1:hand": [] },
      rules: null,
    }));
    expect(next.game.night).toBe(old.game.night); // (untouched: the very same objects)
    expect(next.cards.c).toBe(old.cards.c);
    expect(next.log[0]).toBe(old.log[2]);
    expect(applyPatch(old, {})).toEqual(old);
  });

  it("refuses a patch that does not fit, leaving the base alone", () => {
    const old = base();
    const bad: Patch[] = [
      { del: ["nope"] },
      { del: ["toString"] }, // (an inherited name is not a key of the view)
      { sub: { log: { set: { x: 1 } } } },
      { sub: { missing: {} } },
      { tail: { log: { drop: 9, add: [] } } },
      { tail: { cards: { drop: 0, add: [] } } },
      { keys: ["game"] },
      { keys: ["game", "game", "cards", "log", "zones"] },
    ];
    for (const patch of bad) expect(() => applyPatch(old, patch)).toThrow(PatchError);
    expect(old.cards.b).toEqual({ zone: "lib" });
  });

  it("keeps a key named __proto__ a plain key", () => {
    const next = applyPatch({ a: 1 }, JSON.parse('{"set": {"__proto__": {"polluted": true}}}') as Patch) as Record<string, unknown>;
    expect(Object.keys(next)).toEqual(["a", "__proto__"]);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});

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
}

const view = (seq: number, extra: Record<string, unknown> = {}) =>
  ({ game: { id: "g1", revision: seq, seq }, cards: { a: { zone: "hand" }, b: { zone: "bf" } }, log: [], ...extra }) as unknown as GameView;

describe("game connection: view deltas", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("window", { location: { protocol: "http:", host: "table.local" } });
  });
  afterEach(() => vi.unstubAllGlobals());

  function connect(keep?: (v: GameView) => GameView) {
    const states: { view: GameView; replace: boolean }[] = [];
    const conn = new GameConnection("g1", { token: "t" }, {
      onState: (v, replace) => {
        states.push({ view: v, replace });
        return keep?.(v);
      },
      onLobby: () => {}, onStatus: () => {}, onClosedByServer: () => {},
    });
    conn.connect();
    const ws = FakeSocket.last!;
    ws.open();
    return { conn, ws, states, resyncs: () => ws.sent.filter((m) => m.type === "resync").length };
  }

  it("asks for deltas, applies them in order on the last view, and keeps unchanged cards", () => {
    const { ws, states, resyncs } = connect();
    expect(ws.url).toContain("deltas=1");
    ws.reply({ type: "state", view: view(1), revision: 1, vseq: 1 });
    ws.reply({ type: "delta", revision: 2, base: 1, vseq: 2,
      patch: { sub: { game: { set: { revision: 2, seq: 2 } }, cards: { set: { a: { zone: "bf" } } } } } });
    expect(states).toHaveLength(2);
    const [first, second] = states.map((s) => s.view as unknown as { game: { seq: number }; cards: Record<string, unknown> }) as [
      { game: { seq: number }; cards: Record<string, unknown> }, { game: { seq: number }; cards: Record<string, unknown> }];
    expect(second.game.seq).toBe(2);
    expect(second.cards.a).toEqual({ zone: "bf" });
    expect(second.cards.b).toBe(first.cards.b);
    expect(states[1]!.replace).toBe(false);
    expect(resyncs()).toBe(0);
  });

  it("applies the next patch to the view the store kept", () => {
    const kept = view(1);
    const { ws, states } = connect((v) => (v.game.seq === 1 ? kept : v));
    ws.reply({ type: "state", view: view(1), revision: 1, vseq: 1 });
    ws.reply({ type: "delta", revision: 2, base: 1, vseq: 2, patch: { sub: { game: { set: { seq: 2 } } } } });
    expect((states[1]!.view as unknown as { cards: unknown }).cards).toBe((kept as unknown as { cards: unknown }).cards);
  });

  it("a patch from another view, or one that does not fit, asks for the whole view once and changes nothing", () => {
    const { ws, states, resyncs } = connect();
    ws.reply({ type: "state", view: view(1), revision: 1, vseq: 1 });
    ws.reply({ type: "delta", revision: 3, base: 2, vseq: 3, patch: {} }); // (vseq 2 never came)
    expect(states).toHaveLength(1);
    expect(resyncs()).toBe(1);
    ws.reply({ type: "delta", revision: 4, base: 3, vseq: 4, patch: {} });
    expect(resyncs()).toBe(1); // (asked already: no flood)
    ws.reply({ type: "state", view: view(4), revision: 4, vseq: 5, resync: true });
    expect(states).toHaveLength(2);
    expect(states[1]!.replace).toBe(true);
    ws.reply({ type: "delta", revision: 5, base: 5, vseq: 6, patch: { del: ["nope"] } }); // (doesn't fit)
    expect(states).toHaveLength(2);
    expect(resyncs()).toBe(2);
    ws.reply({ type: "state", view: view(5), revision: 5, vseq: 7, resync: true });
    ws.reply({ type: "delta", revision: 6, base: 7, vseq: 8, patch: { sub: { game: { set: { seq: 6 } } } } });
    expect((states.at(-1)!.view as unknown as { game: { seq: number } }).game.seq).toBe(6);
    expect(resyncs()).toBe(2);
  });

  it("a delta before any view, or an older whole view, is not applied", () => {
    const { ws, states, resyncs } = connect();
    ws.reply({ type: "delta", revision: 2, base: 1, vseq: 2, patch: {} });
    expect(states).toHaveLength(0);
    expect(resyncs()).toBe(1);
    ws.reply({ type: "state", view: view(3), revision: 3, vseq: 3, resync: true });
    ws.reply({ type: "state", view: view(2), revision: 2, vseq: 2 }); // (sent before the one above: superseded)
    expect(states).toHaveLength(1);
  });

  it("a reconnect starts from a whole view again", () => {
    const { conn, ws, states, resyncs } = connect();
    ws.reply({ type: "state", view: view(1), revision: 1, vseq: 1 });
    conn.connect(); // (a new socket: numbering starts over)
    const again = FakeSocket.last!;
    again.open();
    again.reply({ type: "delta", revision: 2, base: 1, vseq: 2, patch: {} });
    expect(states).toHaveLength(1);
    expect(resyncs() + again.sent.filter((m) => m.type === "resync").length).toBe(1);
    again.reply({ type: "state", view: view(2), revision: 2, vseq: 1 });
    expect(states).toHaveLength(2);
  });

  it("a server without deltas still gets whole views handled as before", () => {
    const { ws, states } = connect();
    ws.reply({ type: "state", view: view(1), revision: 1 });
    ws.reply({ type: "state", view: view(2), revision: 2 });
    ws.reply({ type: "state", view: view(1), revision: 1 }); // (stale)
    expect(states.map((s) => (s.view as unknown as { game: { seq: number } }).game.seq)).toEqual([1, 2]);
  });
});
