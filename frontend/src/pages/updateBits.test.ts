import { describe, expect, it } from "vitest";
import type { UpdateSummary } from "../services/update";
import { uploadError } from "../services/update";
import { installedText, percent, planLines, resultText, sizeText, versionText, waitForRestart } from "./updateBits";
import { settingsSections } from "./settingsBits";

const PLAN: UpdateSummary = {
  files: 262, total_bytes: 469_468_928, replaced: 250, added: 12, version: "2026-11-18a", commit: "fe22e8e1234567890", built_at: null,
  verified: true, removed: 3, removed_sample: ["_internal/old.dll"], warnings: [], closes_window: true, zip_name: "Fyodor-update-2026-11-18a.zip",
  groups: [
    { name: "browser", files: 30, bytes: 340_000_000, folder: true },
    { name: "_internal", files: 230, bytes: 111_000_000, folder: true },
    { name: "Fyodor.exe", files: 1, bytes: 18_002_105, folder: false },
  ],
};

describe("install update: words", () => {
  it("sizes", () => {
    expect(sizeText(10)).toBe("1 KB");
    expect(sizeText(48 * 1024)).toBe("48 KB");
    expect(sizeText(18_002_105)).toBe("17.2 MB");
    expect(sizeText(3 * 1024 ** 3)).toBe("3.00 GB");
  });

  it("names the version and commit when the update says them", () => {
    expect(versionText({ version: "2026-11-18a", commit: "fe22e8e1234567890" })).toBe("version 2026-11-18a (fe22e8e12345)");
    expect(versionText({ version: null, commit: "abc" })).toBe("commit abc");
    expect(versionText({ version: null, commit: null })).toBeNull();
    expect(installedText({ installed: null })).toMatch(/no update installed from here yet/);
    expect(installedText({ installed: { version: "2026-11-18a", commit: null, built_at: null } })).toBe("Installed: Fyodor version 2026-11-18a.");
  });

  it("summarises a plan: counts, folders, the check, the window, files no longer used", () => {
    const l = planLines(PLAN);
    expect(l.title).toBe("Fyodor version 2026-11-18a (fe22e8e12345)");
    expect(l.counts).toBe("262 files, 447.7 MB: 250 replaced, 12 new");
    expect(l.groups).toEqual(["browser: 30 files, 324.2 MB", "_internal: 230 files, 105.9 MB", "Fyodor.exe (17.2 MB)"]);
    expect(l.checkOk).toBe(true);
    expect(l.check).toMatch(/SHA-256/);
    expect(l.window).toMatch(/window closes/);
    expect(l.removed).toBe("The new version no longer uses 3 files; they stay in the folder and do no harm.");
    const bare = planLines({ ...PLAN, version: null, commit: null, verified: false, closes_window: false, removed: 0, replaced: 1, added: 0, files: 1 });
    expect(bare.title).toBe("Update Fyodor-update-2026-11-18a.zip");
    expect(bare.counts).toBe("1 file, 447.7 MB: 1 replaced");
    expect(bare.checkOk).toBe(false);
    expect(bare.check).toMatch(/No file list/);
    expect(bare.window).toBeNull();
    expect(bare.removed).toBeNull();
  });

  it("says how the last update went", () => {
    expect(resultText(null)).toBeNull();
    expect(resultText({ ok: true, message: "Installed 262 files", files: 262, version: "2026-11-18a", at: "2026-11-18T19:02:00" }))
      .toBe("Last update installed: version 2026-11-18a, 262 files (2026-11-18 19:02:00).");
    expect(resultText({ ok: false, message: "Could not replace Fyodor.exe: in use. The previous version was put back." }))
      .toBe("The last update didn't install: Could not replace Fyodor.exe: in use. The previous version was put back.");
  });

  it("upload progress and refusals", () => {
    expect(percent(0.456)).toBe(46);
    expect(percent(2)).toBe(100);
    expect(uploadError(422, { detail: "'Fyodor/../x': \"..\" isn't allowed" })).toMatch(/isn't allowed/);
    expect(uploadError(413, null)).toMatch(/too large/);
    expect(uploadError(403, {})).toMatch(/host computer/);
    expect(uploadError(500, "x")).toBe("The update was refused (500)");
  });

  it("is a host-only section", () => {
    expect(settingsSections(true).map((s) => s.id)).toContain("st-update");
    expect(settingsSections(false).map((s) => s.id)).not.toContain("st-update");
  });
});

describe("install update: waiting for the restart", () => {
  const run = (answers: boolean[], opts?: Parameters<typeof waitForRestart>[2]) => {
    let i = 0;
    const slept: number[] = [];
    const probe = async () => answers[Math.min(i++, answers.length - 1)]!;
    return waitForRestart(probe, async (ms) => { slept.push(ms); }, opts).then((r) => ({ r, slept: slept.length }));
  };

  it("waits for the old Fyodor to go and the new one to answer", async () => {
    expect(await run([true, true, false, false, false, true])).toEqual({ r: "back", slept: 4 });
  });

  it("a server that never goes away is stuck (the updater didn't take over)", async () => {
    expect((await run([true], { step: 500, downWithin: 2000 })).r).toBe("stuck");
  });

  it("a server that never comes back times out", async () => {
    expect((await run([true, false], { step: 500, upWithin: 1500 })).r).toBe("timeout");
  });
});
