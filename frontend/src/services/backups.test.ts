import { describe, expect, it } from "vitest";
import { whenMade } from "./backups";

describe("whenMade", () => {
  const now = new Date(2026, 9, 31, 22, 0, 0).getTime() / 1000;
  it("says how long ago, then the day", () => {
    expect(whenMade(now - 20, now)).toBe("just now");
    expect(whenMade(now - 12 * 60, now)).toBe("12 min ago");
    expect(whenMade(now - 3 * 3600, now)).toMatch(/^today /);
    expect(whenMade(now - 24 * 3600, now)).toMatch(/^yesterday /);
    expect(whenMade(now - 5 * 24 * 3600, now)).toMatch(/26/);
  });
});
