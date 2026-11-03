import { describe, expect, it } from "vitest";
import { activeSection, keyCaps, keyWords, SETTINGS_SECTIONS, sectionById, settingsSections } from "./settingsBits";

describe("settings sections", () => {
  it("have unique ids and a one-line explanation each", () => {
    const ids = SETTINGS_SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const s of SETTINGS_SECTIONS) expect(s.blurb.length).toBeGreaterThan(10);
    // the card database and backups keep the ids other screens already link to
    expect(ids).toContain("card-data");
    expect(ids).toContain("backups");
  });

  it("show Diagnostics on the host computer only", () => {
    expect(settingsSections(true).map((s) => s.id)).toContain("st-diag");
    expect(settingsSections(false).map((s) => s.id)).not.toContain("st-diag");
    expect(sectionById("st-sound").title).toBe("Sound");
    expect(() => sectionById("nope")).toThrow();
  });

  it("mark the first section in the reading band, or keep the last one marked", () => {
    const order = ["a", "b", "c"];
    expect(activeSection(order, new Set(["c", "b"]), "a")).toBe("b");
    expect(activeSection(order, new Set(), "c")).toBe("c");
  });
});

describe("keyCaps", () => {
  it("names each key of a combo as it is printed on the keyboard", () => {
    expect(keyCaps("ctrl+shift+z")).toEqual(["Ctrl", "Shift", "Z"]);
    expect(keyCaps(" ")).toEqual(["Space"]);
    expect(keyCaps("escape")).toEqual(["Esc"]);
    expect(keyCaps("shift+?")).toEqual(["Shift", "?"]);
    expect(keyCaps("home")).toEqual(["Home"]);
    expect(keyCaps("2")).toEqual(["2"]);
    expect(keyCaps("ctrl++")).toEqual(["Ctrl", "+"]);
    expect(keyWords("ctrl+y")).toBe("Ctrl+Y");
  });
});
