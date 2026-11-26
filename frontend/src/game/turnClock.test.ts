import { describe, expect, it } from "vitest";
import { formatClock, noteSkew, remainingNow } from "./turnClock";

const running = { bank: 100, buffer: 20, running: true, away: false };

describe("turn clock countdown", () => {
  it("noteSkew keeps the least-delayed message", () => {
    expect(noteSkew(null, 1000, 1_000_500)).toBe(0.0 + (1_000_500 / 1000 - 1000));
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
});
