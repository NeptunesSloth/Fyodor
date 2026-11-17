/**
 * -- resolving progress -- interim views of a long chain (the server's "interim" messages): collapsed to the latest, shown without
 * sounds or table motion, the progress kept for the indicator, and all of it replaced by the action's own update.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameView } from "../types/game";
import type { ResolvingProgress } from "../services/gameSocket";

type Handlers = {
  onState: (view: GameView, replace: boolean) => void;
  onInterim: (view: GameView | null, progress: ResolvingProgress) => void;
  onStatus: (status: string) => void;
};
const socket = vi.hoisted(() => ({ handlers: null as unknown as Handlers }));

vi.mock("../services/gameSocket", () => ({
  GameConnection: class {
    constructor(_id: string, _params: unknown, handlers: Handlers) {
      socket.handlers = handlers;
    }
    connect(): void {}
    close(): void {}
  },
}));
vi.mock("../game/motion/tableEvents", () => ({ publishTableEvents: vi.fn() }));
vi.mock("../game/sound", () => ({ play: vi.fn(), soundForLog: () => "draw" }));
vi.mock("./cardCache", () => ({ requestCards: vi.fn() }));

import { publishTableEvents } from "../game/motion/tableEvents";
import { play } from "../game/sound";
import { INTERIM_GAP_MS, settledChange, useGame } from "./gameStore";
import { resolvingText } from "../game/rules/ResolvingIndicator";

/** A table with ``tokens`` copies on Alice's battlefield; ``seq``: the last log line's. */
function table(tokens: number, seq = 10, revision = 5): GameView {
  const cards: Record<string, unknown> = {};
  for (let i = 0; i < tokens; i++) cards[`t${i}`] = { id: `t${i}`, name: "Pestermite", zone: "p1:battlefield", card_id: "pest" };
  return {
    viewer: "p1",
    seat_order: ["p1", "p2"],
    players: [{ id: "p1", name: "Alice", commanders: [] }, { id: "p2", name: "Bob", commanders: [] }],
    game: { id: "g1", revision, seats: { p1: {}, p2: {} } },
    turn: { active_player: "p1", number: 3 },
    zones: { "p1:battlefield": Object.keys(cards) },
    cards,
    stack: [],
    log: [{ seq, ts: 1, parts: [{ t: "Alice drew a card" }], kind: "action" }],
  } as unknown as GameView;
}

const progress = (resolved: number, left: number): ResolvingProgress => ({ resolved, left, by: "p1" });

describe("interim views", () => {
  let renders = 0;
  let unsub: () => void;
  beforeEach(() => {
    vi.useFakeTimers();
    useGame.getState().connect("g1", {});
    socket.handlers.onState(table(200), true);
    vi.mocked(publishTableEvents).mockClear();
    vi.mocked(play).mockClear();
    renders = 0;
    unsub = useGame.subscribe((s, prev) => { if (s.view !== prev.view) renders++; });
  });
  afterEach(() => {
    unsub();
    vi.useRealTimers();
  });

  it("collapses a burst to the latest and shows it without sounds or table motion", () => {
    const base = useGame.getState().view;
    for (let n = 1; n <= 5; n++) socket.handlers.onInterim(table(200 - n * 10, 10), progress(n * 10, 200 - n * 10));
    expect(renders).toBe(0); // (nothing yet: they are collapsed)
    vi.advanceTimersByTime(INTERIM_GAP_MS);
    const s = useGame.getState();
    expect(renders).toBe(1);
    expect(Object.keys(s.view!.cards)).toHaveLength(150); // the latest one only
    expect(s.interim).toBe(true);
    expect(s.committed).toBe(base); // the last authoritative view is kept
    expect(s.resolving).toEqual(progress(50, 150));
    expect(publishTableEvents).not.toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
    expect(settledChange(s, s)).toBeNull(); // (subscribers that react to changes skip it)
    expect(resolvingText(50, 150)).toBe("50 resolved · 150 left");
  });

  it("the action's own update replaces it, drops a waiting one, and is compared with the last update before the chain", () => {
    socket.handlers.onInterim(table(120), progress(80, 120));
    vi.advanceTimersByTime(INTERIM_GAP_MS);
    const before = useGame.getState().committed;
    const shown = useGame.getState().view;
    socket.handlers.onInterim(table(100), progress(100, 100)); // still waiting when the final arrives
    let change: ReturnType<typeof settledChange> = null;
    const watch = useGame.subscribe((s, prev) => { change = settledChange(s, prev); });
    socket.handlers.onState(table(0, 11, 6), false);
    watch();
    vi.advanceTimersByTime(INTERIM_GAP_MS * 3);
    const s = useGame.getState();
    expect(Object.keys(s.view!.cards)).toHaveLength(0); // (the stale interim view never shows after it)
    expect(s.interim).toBe(false);
    expect(s.resolving).toBeNull();
    expect(s.committed).toBe(s.view);
    expect(change).not.toBeNull();
    expect(change!.before).toBe(before); // what changed is judged against the table before the chain...
    expect(publishTableEvents).toHaveBeenCalledTimes(1);
    expect(vi.mocked(publishTableEvents).mock.calls[0]![0]).toBe(shown); // ...while motion starts from what was on screen
    expect(play).toHaveBeenCalledTimes(1); // the new log line sounds once, with the action's own update
  });

  it("a count-only message (no view) only moves the indicator; a dropped connection clears it", () => {
    const shown = useGame.getState().view;
    socket.handlers.onInterim(null, progress(3, 9));
    vi.advanceTimersByTime(INTERIM_GAP_MS);
    expect(useGame.getState().view).toBe(shown);
    expect(useGame.getState().resolving).toEqual(progress(3, 9));
    socket.handlers.onStatus("reconnecting");
    expect(useGame.getState().resolving).toBeNull();
  });
});
