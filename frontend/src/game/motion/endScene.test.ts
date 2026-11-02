import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameView } from "../../types/game";
import { showEliminated } from "../nightEnding";
import { play } from "../sound";
import { usePrefs } from "../../state/prefs";
import {
  END_LOOKS, MAX_HOLD, SKIP_RELEASE, endAt, endFrame, endKindFor, freezeEndScene, holdMs, moteAt, moteFrame, moteTiming, onEndScene,
  playEndScene, resultWord, type EndCue, type EndKind,
} from "./endScene";

vi.mock("../sound", () => ({ play: vi.fn() }));

const KINDS: EndKind[] = ["victory", "defeat", "draw", "watch", "eliminated"];
const win = (winners: string[]) => ({ result_type: winners.length > 1 ? "multiple" : "single", winners });

describe("which scene each viewer gets (from the server's result)", () => {
  it("the winner sees Victory, every other seat Defeat, a spectator the winner's name", () => {
    expect(resultWord(win(["p1"]), "p1", true)).toBe("victory");
    expect(resultWord(win(["p1"]), "p2", true)).toBe("defeat");
    expect(resultWord(win(["p1"]), "p2", false)).toBe("winner");
    expect(endKindFor("victory")).toBe("victory");
    expect(endKindFor("defeat")).toBe("defeat");
    expect(endKindFor("winner")).toBe("watch");
  });
  it("shared wins: every winner sees Victory", () => {
    expect(resultWord(win(["p1", "p3"]), "p3", true)).toBe("victory");
    expect(resultWord(win(["p1", "p3"]), "p2", true)).toBe("defeat");
  });
  it("a draw is a draw for everyone; no result has no table scene", () => {
    for (const [me, seated] of [["p1", true], ["p2", true], ["x", false]] as const) {
      expect(resultWord({ result_type: "draw", winners: [] }, me, seated)).toBe("draw");
    }
    expect(resultWord({ result_type: "no_result", winners: [] }, "p1", true)).toBe("none");
    expect(endKindFor("none")).toBeNull();
  });
  it("eliminated: only the player who is out, and not once the game has a result", () => {
    const view = (result: unknown) => ({
      viewer: "p2", seat_order: ["p1", "p2", "p3"], players: [], rules: { conceded: [], lost: { p2: "0 or less life" }, winner: null, draw_reason: null },
      game: { id: "g", mode: "lan", seats: {}, night: { number: 1, proposal: null, result } },
    }) as unknown as GameView;
    expect(showEliminated(view(null), "p2")).toBe(true);
    expect(showEliminated({ ...view(null), viewer: "p1" }, "p1")).toBe(false); // the others' game goes on untouched
    expect(showEliminated(view(win(["p1"])), "p2")).toBe(false);
    expect(resultWord(win(["p1"]), "p2", true)).toBe("defeat"); // …and the game's end is then their Defeat
  });
});

describe("sequence timing per kind", () => {
  it("holds 1–3 s at 1×; eliminated is the shortest, draw shorter than victory", () => {
    expect(holdMs("victory", 1)).toBe(2600);
    expect(holdMs("defeat", 1)).toBe(2400);
    expect(holdMs("draw", 1)).toBe(2200);
    expect(holdMs("eliminated", 1)).toBe(1600);
    for (const k of KINDS) {
      expect(holdMs(k, 1)).toBeGreaterThanOrEqual(1000);
      expect(holdMs(k, 1)).toBeLessThanOrEqual(MAX_HOLD);
      expect(holdMs("eliminated", 1)).toBeLessThanOrEqual(holdMs(k, 1));
    }
    expect(holdMs("draw", 1)).toBeLessThan(holdMs("victory", 1));
  });
  it("follows the animation speed, but never holds input past 3 s", () => {
    expect(holdMs("victory", 2)).toBe(1300);
    for (const k of [...KINDS, null]) expect(holdMs(k, 0.5)).toBeLessThanOrEqual(MAX_HOLD);
    expect(holdMs(null, 1)).toBe(2600); // no result: the spotlight alone
  });
  it("every beat finishes inside its hold, and the table settles back within a second after", () => {
    for (const k of KINDS) {
      const l = END_LOOKS[k];
      expect(l.dimIn).toBeLessThan(l.hold);
      expect(l.camIn).toBeLessThan(l.hold);
      if (l.pulse) expect(l.pulse.at + l.pulse.dur).toBeLessThan(l.hold);
      if (l.motes) expect(l.motes.at + (l.motes.count - 1) * l.motes.stagger + l.motes.life * 1.2).toBeLessThanOrEqual(l.hold);
      expect(l.release).toBeLessThanOrEqual(600);
    }
  });
  it("dims in, pulses once, and settles back exactly to normal", () => {
    const l = END_LOOKS.victory;
    const f = endFrame();
    expect(endAt(l, 0, null, false, f).dim).toBe(0);
    expect(endAt(l, l.dimIn, null, false, f).dim).toBeCloseTo(1);
    expect(endAt(l, l.pulse!.at - 1, null, false, f).pulse).toBe(0);
    expect(endAt(l, l.pulse!.at + l.pulse!.dur * 0.3, null, false, f).pulse).toBeCloseTo(l.pulse!.strength);
    expect(endAt(l, l.pulse!.at + l.pulse!.dur + 1, null, false, f).pulse).toBe(0);
    const held = endAt(l, 2000, null, false, f);
    expect(held.done).toBe(false);
    expect(held.dim).toBeCloseTo(1);
    const rel = { at: 2600, dur: l.release };
    const mid = endAt(l, 2600 + l.release / 2, rel, false, f);
    expect(mid.dim).toBeGreaterThan(0);
    expect(mid.dim).toBeLessThan(1);
    const after = endAt(l, 2600 + l.release, rel, false, f);
    expect(after.done).toBe(true);
    expect([after.dim, after.push, after.lift, after.pulse]).toEqual([0, 0, 0, 0]);
  });
  it("the camera: a small push for victory, a small pull back for defeat and eliminated, almost still for a draw", () => {
    const f = endFrame();
    const push = (k: EndKind) => endAt(END_LOOKS[k], END_LOOKS[k].camIn, null, false, f).push;
    expect(push("victory")).toBeGreaterThanOrEqual(0.02);
    expect(push("victory")).toBeLessThanOrEqual(0.04);
    expect(push("defeat")).toBeLessThanOrEqual(-0.02);
    expect(push("defeat")).toBeGreaterThanOrEqual(-0.04);
    expect(push("eliminated")).toBeLessThan(0);
    expect(Math.abs(push("eliminated"))).toBeLessThan(Math.abs(push("defeat")));
    expect(Math.abs(push("draw"))).toBeLessThanOrEqual(0.01);
    expect(push("watch")).toBe(0);
  });
  it("a few motes, fewer for defeat and a draw, none for eliminated; all gone before the hold ends", () => {
    expect(END_LOOKS.victory.motes!.count).toBeLessThanOrEqual(16);
    expect(END_LOOKS.defeat.motes!.count).toBeLessThan(END_LOOKS.victory.motes!.count);
    expect(END_LOOKS.draw.motes!.count).toBeLessThan(END_LOOKS.victory.motes!.count);
    expect(END_LOOKS.eliminated.motes).toBeNull();
    const m = moteFrame();
    for (const k of KINDS) {
      const l = END_LOOKS[k];
      for (let i = 0; i < (l.motes?.count ?? 0); i++) {
        const { start, life } = moteTiming(l, i);
        expect(moteAt(l, i, start + life * 0.3, 1, false, m).alpha).toBeGreaterThan(0);
        const r = Math.hypot(m.x, m.z);
        expect(r).toBeGreaterThan(0.25); // never on the very middle, where the word is
        expect(r).toBeLessThanOrEqual(1);
        expect(moteAt(l, i, l.hold, 1, false, m).alpha).toBe(0);
      }
    }
  });
});

describe("reduced motion", () => {
  it("drops the camera, the pulse and the motes, keeps the dim", () => {
    const f = endFrame();
    const m = moteFrame();
    for (const k of KINDS) {
      const l = END_LOOKS[k];
      for (const t of [0, 200, 500, 1000, 1500]) {
        endAt(l, t, null, true, f);
        expect(f.push).toBe(0);
        expect(f.lift).toBe(0);
        expect(f.pulse).toBe(0);
        for (let i = 0; i < (l.motes?.count ?? 0); i++) expect(moteAt(l, i, t, 1, true, m).alpha).toBe(0);
      }
      expect(endAt(l, l.dimIn, null, true, f).dim).toBeCloseTo(1);
    }
  });
});

describe("playing a scene", () => {
  let cues: (EndCue | null)[] = [];
  let off: () => void = () => undefined;
  beforeEach(() => {
    vi.useFakeTimers();
    usePrefs.setState({ animationSpeed: 1 });
    cues = [];
    off = onEndScene((c) => cues.push(c));
  });
  afterEach(() => {
    off();
    freezeEndScene(null);
    vi.runAllTimers();
    vi.useRealTimers();
  });

  it("starts the cue, lets go after the hold, then clears; onEnd runs once", () => {
    const onEnd = vi.fn();
    playEndScene("defeat", onEnd);
    expect(cues.at(-1)?.kind).toBe("defeat");
    expect(cues.at(-1)?.release).toBeNull();
    vi.advanceTimersByTime(2399);
    expect(onEnd).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(cues.at(-1)?.release?.dur).toBe(END_LOOKS.defeat.release);
    vi.advanceTimersByTime(END_LOOKS.defeat.release + 60);
    expect(cues.at(-1)).toBeNull();
    vi.advanceTimersByTime(5000);
    expect(onEnd).toHaveBeenCalledTimes(1);
  });
  it("stop() lets the table settle back quickly and doesn't call onEnd", () => {
    const onEnd = vi.fn();
    const play = playEndScene("victory", onEnd);
    vi.advanceTimersByTime(500);
    play.stop();
    expect(cues.at(-1)?.release?.dur).toBe(SKIP_RELEASE);
    vi.advanceTimersByTime(SKIP_RELEASE + 60);
    expect(cues.at(-1)).toBeNull();
    vi.advanceTimersByTime(5000);
    expect(onEnd).not.toHaveBeenCalled();
  });
  it("a frozen scene (a screenshot) holds until it is unfrozen", () => {
    const onEnd = vi.fn();
    freezeEndScene(700);
    playEndScene("draw", onEnd);
    vi.advanceTimersByTime(10_000);
    expect(onEnd).not.toHaveBeenCalled();
    expect(cues.at(-1)?.kind).toBe("draw");
    freezeEndScene(null);
    vi.advanceTimersByTime(250);
    expect(onEnd).toHaveBeenCalledTimes(1);
  });
  it("the sting (sound is optional) lands with the pulse, and never after a skip", () => {
    vi.mocked(play).mockClear();
    playEndScene("victory", () => undefined);
    vi.advanceTimersByTime(END_LOOKS.victory.pulse!.at - 1);
    expect(play).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(play).toHaveBeenCalledWith("victory");
    vi.mocked(play).mockClear();
    playEndScene("defeat", () => undefined).stop();
    vi.advanceTimersByTime(1000);
    expect(play).not.toHaveBeenCalled();
  });
  it("no result: no table reaction, only the hold", () => {
    const onEnd = vi.fn();
    const before = cues.length;
    playEndScene(null, onEnd);
    expect(cues.length).toBe(before);
    vi.advanceTimersByTime(2600);
    expect(onEnd).toHaveBeenCalledTimes(1);
  });
  it("a new scene replaces the old one; the old one's release leaves it alone", () => {
    const a = playEndScene("eliminated", () => undefined);
    vi.advanceTimersByTime(300);
    playEndScene("defeat", () => undefined);
    a.stop();
    expect(cues.at(-1)?.kind).toBe("defeat");
    expect(cues.at(-1)?.release).toBeNull();
  });
});
