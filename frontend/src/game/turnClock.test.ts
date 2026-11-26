import { describe, expect, it } from "vitest";
import { SKEW_WINDOW_MS, formatClock, noteSkew, noteSkewWindow, remainingNow } from "./turnClock";

const running = { bank: 100, buffer: 20, running: true, away: false };

describe("turn clock countdown", () => {
  it("noteSkew keeps the least-delayed message", () => {
    expect(noteSkew(null, 1000, 1_000_500)).toBe(1_000_500 / 1000 - 1000);
    expect(noteSkew(5, 1000, 1_002_000)).toBe(2);
    expect(noteSkew(1, 1000, 1_002_000)).toBe(1);
  });
  it("a client clock 600 s ahead shows the same remaining time as a correct one", () => {
    const sentAt = 1_000_000;
    const good = noteSkew(null, sentAt, sentAt * 1000 + 50);
    const fast = noteSkew(null, sentAt, (sentAt + 600) * 1000 + 50);
    const a = remainingNow(running, sentAt, good, sentAt * 1000 + 10_050);
    const b = remainingNow(running, sentAt, fast, (sentAt + 600) * 1000 + 10_050);
    expect(b).toEqual(a);
    expect(a.buffer).toBeCloseTo(10, 5);
  });
  it("a sentAt that looks like the future gives elapsed 0", () => {
    expect(remainingNow(running, 5000, 0, 1000 * 1000)).toEqual({ buffer: 20, bank: 100 });
  });
  it("spends the buffer before the bank and never goes below 0", () => {
    expect(remainingNow(running, 0, 0, 30_000)).toEqual({ buffer: 0, bank: 90 });
    expect(remainingNow(running, 0, 0, 9_999_000)).toEqual({ buffer: 0, bank: 0 });
  });
  it("frozen when not running or away", () => {
    expect(remainingNow({ ...running, running: false }, 0, 0, 50_000)).toEqual({ buffer: 20, bank: 100 });
    expect(remainingNow({ ...running, away: true }, 0, 0, 50_000)).toEqual({ buffer: 20, bank: 100 });
  });
  it("formatClock", () => {
    expect(formatClock(1500)).toBe("25:00");
    expect(formatClock(7)).toBe("0:07");
    expect(formatClock(3723)).toBe("1:02:03");
    expect(formatClock(-4)).toBe("0:00");
  });
  it("formatClock rounds remaining time up and survives bad input", () => {
    expect(formatClock(0.4)).toBe("0:01");
    expect(formatClock(59.9)).toBe("1:00");
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(1499.4)).toBe("25:00");
    expect(formatClock(Number.NaN)).toBe("0:00");
    expect(formatClock(Infinity)).toBe("0:00");
  });
  it("skew window: least-delayed wins inside it, a forward step of the client clock recovers after it", () => {
    const t0 = 1_000_000_000;
    let w = noteSkewWindow([], 1000, t0 + 1000 * 1000 + 50);
    const base = w.skew;
    w = noteSkewWindow(w.samples, 1010, t0 + 1010 * 1000 + 400); // a slower message: the minimum stays
    expect(w.skew).toBeCloseTo(base, 5);
    const at = t0 + 1020 * 1000 + 60_000; // the client clock steps 60 s forward: still read low inside the window...
    w = noteSkewWindow(w.samples, 1020, at + 50);
    expect(w.skew).toBeCloseTo(base, 5);
    const later = at + SKEW_WINDOW_MS + 1000; // ...and recovers once the old samples are out of it
    w = noteSkewWindow(w.samples, 1020 + SKEW_WINDOW_MS / 1000 + 1, later + 50);
    expect(w.skew).toBeCloseTo(base + 60, 0);
    expect(w.samples.length).toBe(1);
    // a big step (600 s, beyond the window) ages the old samples out at once; a step backwards drops the samples from the future
    expect(noteSkewWindow(w.samples, 1020 + SKEW_WINDOW_MS / 1000 + 1, later + 600_000 + 50).skew).toBeCloseTo(base + 660, 0);
    expect(noteSkewWindow([[later + 5000, -50]], 2000, later).samples).toHaveLength(1);
  });
});
