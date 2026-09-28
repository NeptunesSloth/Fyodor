import { describe, expect, it } from "vitest";
import { HOTKEYS, collisions, matchHotkey } from "./hotkeys";

describe("hotkeys", () => {
  it("never binds one key to two actions", () => {
    expect(collisions()).toEqual([]);
    expect(collisions([...HOTKEYS, { id: "pass", keys: ["t"], label: "" }])).toEqual(["t: tap / pass"]);
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
