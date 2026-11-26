import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ClockChipView, chipLabel } from "./TurnClockChip";

const settings = { on: true, bank_seconds: 1500, buffer_seconds: 30, at_zero: "act" as const, grace_seconds: 120 };
function show(clock: object | undefined) {
  const c = clock && ({ sent_at: 5000, ...clock } as never);
  return renderToStaticMarkup(createElement(ClockChipView, { clock: c, skew: 0, name: "Alice", player: "p1", now: 5_000_000 }));
}

describe("TurnClockChip label", () => {
  it("says the state in words", () => {
    expect(chipLabel("Alice", 751, 0, true, false)).toBe("Alice's clock: 12:31 left, running");
    expect(chipLabel("Alice", 751, 0, false, false)).toBe("Alice's clock: 12:31 left");
    expect(chipLabel("Alice", 751, 0, true, true)).toBe("Alice's clock: 12:31 left, paused, reconnecting");
  });
});

describe("TurnClockChip render", () => {
  it("running: the buffer before the bank", () => {
    const html = show({ settings, players: { p1: { bank: 751, buffer: 24, running: true, away: false } } });
    expect(html).toContain("0:24 · 12:31");
    expect(html).toContain("running");
  });
  it("idle: the bank alone", () => {
    const html = show({ settings, players: { p1: { bank: 751, buffer: 30, running: false, away: false } } });
    expect(html).toContain("12:31");
    expect(html).not.toContain("·");
  });
  it("away: says Paused — reconnecting", () => {
    expect(show({ settings, players: { p1: { bank: 751, buffer: 30, running: true, away: true } } })).toContain("Paused — reconnecting");
  });
  it("nothing when the clock is off, absent or the player has no entry", () => {
    expect(show({ settings: { ...settings, on: false } })).toBe("");
    expect(show(undefined)).toBe("");
    expect(show({ settings, players: {} })).toBe("");
  });
});
