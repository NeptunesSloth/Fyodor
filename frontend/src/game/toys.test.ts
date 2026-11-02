import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameConnection } from "../services/gameSocket";
import { useGame } from "../state/gameStore";
import type { GameView } from "../types/game";
import { Eliminated } from "./Eliminated";
import { play } from "./sound";
import { SideActivityDialog, SpectatorMenu } from "./SpectatorHub";
import {
  DIE_KINDS, HISTORY_MAX, MAX_DICE, MAX_OF_KIND, addDie, coinSummary, defaultToys, emptyPool, keepRoll, loadToys, poolLabel, poolOf,
  poolSize, remember, rollHeadline, rollLine, rollPool, rollTotal, sanitizeToys, saveToys, secureInt, sidesOf, spinPath, spinPlayers,
  type Pool, type Roll,
} from "./toys";

const pool = (over: Partial<Pool>): Pool => ({ ...emptyPool(), ...over });
/** A fixed sequence of "random" numbers, for exact totals. */
const scripted = (...xs: number[]) => (n: number) => {
  const x = xs.shift();
  if (x === undefined || x >= n) throw new Error(`scripted: ${x} for ${n}`);
  return x;
};

const view = (over: Record<string, unknown> = {}): GameView =>
  ({
    viewer: "p3",
    seat_order: ["p1", "p2", "p3", "p4"],
    players: [
      { id: "p1", name: "Zoe", color: "#c33", hand_count: 7, library_count: 80 },
      { id: "p2", name: "Bob", color: "#36c", hand_count: 3, library_count: 70 },
      { id: "p3", name: "Carol", color: "#3a5", hand_count: 0, library_count: 60 },
      { id: "p4", name: "Dan", color: "#999", left: true, hand_count: 0, library_count: 0 },
    ],
    cards: { c1: { id: "c1", name: "Secret Tutor Target", zone: "p1:hand" } },
    turn: { number: 5, active_player: "p2" },
    game: { id: "g1", mode: "lan", night: { number: 1, result: null }, settings: {} },
    ...over,
  }) as unknown as GameView;

describe("the dice", () => {
  it("draws its numbers from crypto.getRandomValues, never Math.random", () => {
    const crypto = vi.spyOn(globalThis.crypto, "getRandomValues");
    const math = vi.spyOn(Math, "random");
    rollPool(pool({ d4: 2, d6: 3, d8: 1, d10: 1, d12: 1, d20: 2, coin: 2 }));
    expect(crypto).toHaveBeenCalled();
    expect(math).not.toHaveBeenCalled();
    crypto.mockRestore();
    math.mockRestore();
  });

  it("keeps every die in range, roughly fair over many rolls", () => {
    for (const kind of DIE_KINDS) {
      const sides = sidesOf(kind);
      const per = 600;
      const counts = new Map<number, number>();
      const roll = rollPool(pool({ [kind]: 1 }))!;
      expect(roll.groups).toHaveLength(1);
      for (let i = 0; i < sides * per; i++) {
        const v = rollPool(pool({ [kind]: 1 }))!.groups[0]!.results[0]!;
        counts.set(v, (counts.get(v) ?? 0) + 1);
      }
      const faces = kind === "coin" ? [0, 1] : Array.from({ length: sides }, (_, k) => k + 1);
      expect([...counts.keys()].sort((a, b) => a - b), `${kind} faces`).toEqual(faces);
      for (const f of faces) {
        // expected 600 each (sd ≈ 24): a loose ±30% catches a broken or biased die, never a fair one
        expect(counts.get(f)!, `${kind} shows ${f}`).toBeGreaterThan(per * 0.7);
        expect(counts.get(f)!, `${kind} shows ${f}`).toBeLessThan(per * 1.3);
      }
    }
  });

  it("gives uniform whole numbers for any size", () => {
    for (const n of [1, 2, 3, 7, 100, 2 ** 31 + 1]) {
      for (let i = 0; i < 200; i++) {
        const v = secureInt(n);
        expect(Number.isInteger(v) && v >= 0 && v < n).toBe(true);
      }
    }
    expect(() => secureInt(0)).toThrow();
    expect(() => secureInt(1.5)).toThrow();
  });

  it("adds a pool up: each die, the total, and the coins apart", () => {
    const roll = rollPool(pool({ d6: 3, d20: 1, coin: 1 }), scripted(3, 1, 5, 16, 1), 1000)!;
    expect(roll.groups).toEqual([{ kind: "d6", results: [4, 2, 6] }, { kind: "d20", results: [17] }, { kind: "coin", results: [1] }]);
    expect(rollTotal(roll)).toBe(29);
    expect(coinSummary(roll)).toBe("heads");
    expect(rollHeadline(roll)).toBe("29");
    expect(rollLine(roll)).toBe("3d6 + d20: 4 + 2 + 6 + 17 = 29 · coin: heads");
    expect(poolLabel(pool({ d6: 3, d20: 1, coin: 2 }))).toBe("3d6 + d20 + 2 coins");

    const coins = rollPool(pool({ coin: 3 }), scripted(1, 0, 1))!;
    expect(rollTotal(coins)).toBeNull();
    expect(rollHeadline(coins)).toBe("2 heads, 1 tails");
    expect(rollLine(coins)).toBe("3 coins: 2 heads, 1 tails");

    expect(rollLine(rollPool(pool({ d20: 1 }), scripted(19))!)).toBe("d20: 20");
    expect(rollPool(emptyPool())).toBeNull();
  });

  it("keeps the pool within its limits", () => {
    let p = emptyPool();
    for (let i = 0; i < 20; i++) p = addDie(p, "d6", 1);
    expect(p.d6).toBe(MAX_OF_KIND);
    for (let i = 0; i < 20; i++) p = addDie(p, "d20", 1);
    expect(poolSize(p)).toBe(MAX_DICE);
    expect(addDie(p, "coin", 1)).toBe(p); // full: nothing changes
    expect(addDie(addDie(p, "d6", -3), "d6", -20).d6).toBe(0);
  });
});

describe("the history", () => {
  const roll = (id: string, over: Partial<Pool> = { d6: 1 }): Roll => ({ ...rollPool(pool(over))!, id });

  it("puts the newest first and keeps only a few", () => {
    let h: Roll[] = [];
    for (let i = 0; i < HISTORY_MAX + 4; i++) h = remember(h, roll(`r${i}`));
    expect(h).toHaveLength(HISTORY_MAX);
    expect(h[0]!.id).toBe(`r${HISTORY_MAX + 3}`);
    expect(h.at(-1)!.id).toBe("r4");
  });

  it("rerolls the same dice: the roll's pool becomes the pool and the new roll goes on top", () => {
    const first = rollPool(pool({ d8: 2, coin: 1 }))!;
    let s = keepRoll({ ...defaultToys(), pool: pool({ d4: 1 }) }, first);
    expect(s.pool).toEqual(pool({ d8: 2, coin: 1 }));
    const again = rollPool(poolOf(s.history[0]!))!;
    s = keepRoll(s, again);
    expect(s.history.map((r) => r.id)).toEqual([again.id, first.id]);
    expect(again.groups.map((g) => [g.kind, g.results.length])).toEqual([["d8", 2], ["coin", 1]]);
    expect({ ...s, history: [] }.history).toEqual([]); // Clear
  });

  it("is kept in this browser, and anything odd stored there is dropped", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
    try {
      const r = rollPool(pool({ d12: 2 }))!;
      saveToys({ ...defaultToys(), pool: pool({ d12: 2 }), history: [r], tally: { label: "Storm", count: 4 } });
      expect(loadToys()).toEqual({ pool: pool({ d12: 2 }), history: [r], tally: { label: "Storm", count: 4 } });
      store.set("fyodor.toys", "{not json");
      expect(loadToys()).toEqual(defaultToys());
    } finally {
      vi.unstubAllGlobals();
    }
    const bad = sanitizeToys({
      pool: { d6: 99, d7: 3, coin: -2 },
      history: [
        { id: "ok", at: 1, groups: [{ kind: "d6", results: [6] }] },
        { id: "out of range", at: 1, groups: [{ kind: "d6", results: [7] }] },
        { id: "no such die", at: 1, groups: [{ kind: "d7", results: [1] }] },
        null,
      ],
      tally: { label: 5, count: 1e9 },
    });
    expect(bad.pool).toEqual(pool({ d6: MAX_OF_KIND }));
    expect(bad.history.map((r) => r.id)).toEqual(["ok"]);
    expect(bad.tally).toEqual({ label: "Tally", count: 9999 });
  });
});

describe("the random player (just for fun)", () => {
  it("offers only the seated players' public names, alphabetically, leaving out those who left", () => {
    const names = spinPlayers(view());
    expect(names).toEqual([{ id: "p2", name: "Bob" }, { id: "p3", name: "Carol" }, { id: "p1", name: "Zoe" }]);
    expect(JSON.stringify(names)).not.toMatch(/Secret|hand|library|#/);
  });

  it("goes round a couple of times and ends on the pick", () => {
    for (const count of [2, 3, 6]) {
      for (let pick = 0; pick < count; pick++) {
        const path = spinPath(count, pick);
        expect(path.at(-1)).toBe(pick);
        expect(path.length).toBeGreaterThanOrEqual(12);
        expect(path.every((i) => i >= 0 && i < count)).toBe(true);
      }
    }
    expect(spinPath(0, 0)).toEqual([]);
  });
});

describe("nothing leaves this browser", () => {
  class FakeSocket {
    static OPEN = 1;
    static last: FakeSocket | null = null;
    readyState = 0;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onmessage: (() => void) | null = null;
    onclose: (() => void) | null = null;
    constructor(public url: string) {
      FakeSocket.last = this;
    }
    send(data: string) {
      this.sent.push(data);
    }
    close() {
      this.readyState = 3;
    }
  }
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("window", { location: { protocol: "http:", host: "table.local" } });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
  });
  afterEach(() => {
    useGame.setState({ conn: null });
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("rolls, rerolls, spins and counts without a request or a WebSocket message", () => {
    // a live game connection, open, as at the table
    const conn = new GameConnection("g1", { token: "t" }, { onState: () => {}, onLobby: () => {}, onStatus: () => {}, onClosedByServer: () => {}, onOutbox: () => {} });
    conn.connect();
    const ws = FakeSocket.last!;
    ws.readyState = 1;
    ws.onopen?.();
    useGame.setState({ conn });
    const sentBefore = ws.sent.length;
    const send = vi.spyOn(FakeSocket.prototype, "send");
    const request = vi.spyOn(conn, "request");

    let s = loadToys();
    for (let i = 0; i < 30; i++) {
      const roll = rollPool(addDie(addDie(s.pool, "d6", 2), "coin", 1))!;
      s = keepRoll(s, roll);
      saveToys(s);
      play(roll.groups.every((g) => g.kind === "coin") ? "coin" : "dice"); // the local sound
    }
    s = keepRoll(s, rollPool(poolOf(s.history[3]!))!); // reroll
    saveToys({ ...s, history: [] }); // clear
    const names = spinPlayers(view());
    spinPath(names.length, secureInt(names.length));
    saveToys({ ...s, tally: { label: "Tally", count: s.tally.count + 1 } });

    expect(fetch).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
    expect(ws.sent.length).toBe(sentBefore);
  });
});

describe("the hubs offer dice & toys", () => {
  it("in the eliminated player's hub, at a LAN table and a hot-seat one", () => {
    for (const mode of ["lan", "local"]) {
      const html = renderToStaticMarkup(createElement(Eliminated, { view: view({ game: { id: "g1", mode, night: { number: 1, result: null }, settings: {} } }), me: "p3", sceneOn: false }));
      expect(html).toContain('data-testid="eliminated-hub"');
      expect(html).toMatch(/data-testid="open-toys"[^>]*>\s*Dice &amp; toys/);
    }
  });

  it("in the spectators' Things to do", () => {
    const html = renderToStaticMarkup(createElement(SpectatorMenu, { onStart: () => {}, onClose: () => {} }));
    expect(html).toContain('data-testid="spectator-hub"');
    expect(html).toMatch(/data-testid="open-toys"[^>]*>\s*Dice &amp; toys/);
  });

  it("opens the tray: Roll, the dice to pick, nothing from anyone's hand", () => {
    const html = renderToStaticMarkup(createElement(SideActivityDialog, { activity: "toys", view: view(), onClose: () => {} }));
    expect(html).toContain("Dice &amp; toys");
    expect(html).toContain('data-testid="toys-roll"');
    for (const k of DIE_KINDS) expect(html).toContain(`data-testid="toys-add-${k}"`);
    expect(html).toContain("Only in this browser");
    expect(html).not.toContain("Secret Tutor Target");
  });
});
