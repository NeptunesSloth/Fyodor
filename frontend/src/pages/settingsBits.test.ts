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

  it("mark the last section whose top has passed the reading line", () => {
    const order = ["keys", "card-data", "backups"];
    // a long Keys section still fills the screen, but Card database has reached the line: Card database is marked
    expect(activeSection(order, [-900, 120, 800], 160, false)).toBe("card-data");
    expect(activeSection(order, [-900, 300, 900], 160, false)).toBe("keys");
    // above the first heading the first section is marked
    expect(activeSection(order, [400, 1200, 1800], 160, false)).toBe("keys");
    // at the bottom of the page the last section is marked even below the line; missing sections are skipped
    expect(activeSection(order, [-900, 120, 600], 160, true)).toBe("backups");
    expect(activeSection(order, [-900, 120, null], 160, true)).toBe("card-data");
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
