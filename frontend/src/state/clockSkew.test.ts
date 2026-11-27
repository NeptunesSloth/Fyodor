import { beforeEach, describe, expect, it } from "vitest";
import { applyInterim, clockSkewPatch, useGame } from "./gameStore";
import type { GameView } from "../types/game";

const view = (sentAt: number | null) =>
  ({ game: { id: "g1", clock: sentAt === null ? undefined : { settings: {}, sent_at: sentAt } }, cards: {}, players: [] }) as unknown as GameView;

describe("store clock skew", () => {
  beforeEach(() => useGame.setState({ view: null, clockSkew: null, clockSamples: [] }));
  it("a view carrying sent_at updates the skew; one without leaves it", () => {
    const a = clockSkewPatch({ clockSkew: null, clockSamples: [] }, view(1000), 1_000_500);
    expect(a.clockSkew).toBeCloseTo(0.5, 5);
    expect(clockSkewPatch(a, view(null), 9_999_999)).toEqual(a);
    const b = clockSkewPatch(a, view(1010), 1_010_900); // slower: the minimum stays
    expect(b.clockSkew).toBe(a.clockSkew);
  });
  it("an interim view updates the skew too", () => {
    useGame.setState({ view: view(1000) });
    applyInterim((fn) => useGame.setState(fn(useGame.getState())), () => useGame.getState(), view(1000), { count: 1 } as never);
    expect(useGame.getState().clockSkew).not.toBeNull();
  });
});
