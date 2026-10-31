import { describe, expect, it } from "vitest";
import { HOTKEYS, bookmarkSlot, collisions, effectiveHotkeys, matchHotkey } from "./hotkeys";

describe("hotkeys", () => {
  it("never binds one key to two actions", () => {
    expect(collisions()).toEqual([]);
    expect(collisions([...HOTKEYS, { id: "pass", keys: ["t"], label: "" }])).toEqual(["t: tap / pass"]);
  });
  it("applies remapped keys and still detects collisions", () => {
    const ev = (key: string) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false });
    expect(matchHotkey(ev("x"), { pass: ["x"] })).toBe("pass");
    expect(matchHotkey(ev("p"), { pass: ["x"] })).toBeNull();
    expect(collisions(effectiveHotkeys({ pass: ["t"] }))).toEqual(["t: tap / pass"]);
  });
  it("ships presets without collisions; Arena's Space passes", async () => {
    const { KEY_PRESETS } = await import("./hotkeys");
    for (const p of KEY_PRESETS) expect(collisions(effectiveHotkeys(p.keymap))).toEqual([]);
    const arena = KEY_PRESETS.find((p) => p.id === "arena")!.keymap;
    expect(matchHotkey({ key: " ", ctrlKey: false, metaKey: false, shiftKey: false }, arena)).toBe("pass");
    expect(matchHotkey({ key: " ", ctrlKey: false, metaKey: false, shiftKey: false })).toBe("tap");
  });
  it("finds bookmark slots by physical key", () => {
    expect(bookmarkSlot({ code: "Digit3", ctrlKey: true, metaKey: false, shiftKey: false })).toEqual({ slot: 3, save: false });
    expect(bookmarkSlot({ code: "Digit3", ctrlKey: true, metaKey: false, shiftKey: true })).toEqual({ slot: 3, save: true });
    expect(bookmarkSlot({ code: "Digit3", ctrlKey: false, metaKey: false, shiftKey: false })).toBeNull();
  });
  it("matches modifiers exactly", () => {
    const ev = (key: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }> = {}) =>
      ({ key, ctrlKey: false, metaKey: false, shiftKey: false, ...mods });
    expect(matchHotkey(ev("p"))).toBe("pass");
    expect(matchHotkey(ev("P", { shiftKey: true }))).toBe("auto_pass");
    expect(matchHotkey(ev("z", { metaKey: true }))).toBe("undo");
    expect(matchHotkey(ev("Z", { ctrlKey: true, shiftKey: true }))).toBe("redo");
    expect(matchHotkey(ev("N", { shiftKey: true }))).toBe("next_turn");
    expect(matchHotkey(ev("r", { ctrlKey: true }))).toBeNull(); // browser reload stays the browser's
    expect(matchHotkey(ev("?", { shiftKey: true }))).toBe("help");
  });
});
