import { describe, expect, it } from "vitest";
import { DEFAULT_PREFS, PROFILE_VERSION, migrateProfiles } from "./prefs";

describe("profile migrations", () => {
  it("turns v1 single prefs into a default profile", () => {
    const s = migrateProfiles(null, { showTokenSources: true, hud: "minimal" });
    expect(s.version).toBe(PROFILE_VERSION);
    expect(s.profiles).toHaveLength(1);
    expect(s.profiles[0]!.prefs.showTokenSources).toBe(true);
    expect(s.profiles[0]!.prefs.hud).toBe("minimal");
    expect(s.profiles[0]!.prefs.sound).toEqual(DEFAULT_PREFS.sound);
    expect(s.active).toBe(s.profiles[0]!.id);
  });
  it("fills new fields into old profiles and repairs a bad active id", () => {
    const s = migrateProfiles({ version: 1, active: "gone", profiles: [{ id: "a", name: "Jonathan", prefs: { uiScale: 1.2, sound: { muted: true } } }] });
    expect(s.active).toBe("a");
    expect(s.profiles[0]!.prefs.uiScale).toBe(1.2);
    expect(s.profiles[0]!.prefs.sound.muted).toBe(true);
    expect(s.profiles[0]!.prefs.sound.master).toBe(DEFAULT_PREFS.sound.master);
    expect(s.profiles[0]!.prefs.tokenCollapse).toBe(5);
  });
  it("survives garbage", () => {
    expect(migrateProfiles("nonsense").profiles).toHaveLength(1);
    expect(migrateProfiles({ profiles: [null, 3, { id: "x" }] }).profiles.map((p) => p.id)).toEqual(["x"]);
  });
});
