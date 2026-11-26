import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DEFAULT_CLOCK, TurnClockSetting, clockPatch } from "./TurnClockSetting";
import { chipLabel } from "../game/TurnClockChip";

const html = (c: object) => renderToStaticMarkup(createElement(TurnClockSetting, { value: c as never, onChange: vi.fn() }));

describe("TurnClockSetting", () => {
  it("always sends the full clock object, never a partial one", () => {
    const patch = clockPatch({ ...DEFAULT_CLOCK, on: true, bank_seconds: 900 }, { at_zero: "show" });
    expect(patch.clock).toEqual({ on: true, bank_seconds: 900, buffer_seconds: 30, at_zero: "show", grace_seconds: 120 });
    expect(Object.keys(clockPatch(undefined, { on: true }).clock).sort()).toEqual(["at_zero", "bank_seconds", "buffer_seconds", "grace_seconds", "on"]);
  });
  it("shows the hints", () => {
    expect(html({ ...DEFAULT_CLOCK, on: false })).toContain("Off: no clock.");
    expect(html({ ...DEFAULT_CLOCK, on: true })).toContain("it never concedes for anyone");
    expect(html({ ...DEFAULT_CLOCK, on: true, at_zero: "show" })).toContain("the clock just reads 0:00; nothing happens.");
  });
  it("the chip says its state in words", () => {
    expect(chipLabel("Alice", 751, 0, true, false)).toBe("Alice's clock: 12:31 left, running");
    expect(chipLabel("Alice", 751, 0, false, false)).toBe("Alice's clock: 12:31 left");
    expect(chipLabel("Alice", 751, 0, true, true)).toBe("Alice's clock: 12:31 left, paused, reconnecting");
  });
});
