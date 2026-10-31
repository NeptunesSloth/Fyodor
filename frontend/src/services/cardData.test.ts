import { describe, expect, it } from "vitest";
import { progressFraction, progressText, type CardJob } from "./cardData";

const job = (phase: string, done: number, total: number): CardJob => ({ id: "j", kind: "card-update", state: "running", done, total, phase, message: "" });

describe("card update progress", () => {
  it("speaks in megabytes while downloading and printings while importing", () => {
    expect(progressText(job("Downloading", 120e6, 520e6))).toBe("Downloading 120 MB / 520 MB");
    expect(progressFraction(job("Downloading", 130e6, 520e6))).toBeCloseTo(0.25);
    expect(progressText(job("Importing", 51200, 112000))).toBe(`Importing ${(51200).toLocaleString()} of about ${(112000).toLocaleString()} printings`);
    expect(progressText(job("Importing", 120000, 112000))).toBe(`Importing ${(120000).toLocaleString()} printings`);
  });
  it("shows the step when it can't be measured", () => {
    expect(progressText(job("Asking Scryfall", 0, 0))).toBe("Asking Scryfall…");
    expect(progressFraction(job("Switching over", 5, 5))).toBeNull();
    expect(progressFraction(job("Downloading", 5, 0))).toBeNull();
  });
});
