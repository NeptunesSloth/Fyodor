import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { drawnBackSvg, drawnBackUrl } from "./drawnBack";
import { linkedCheck } from "./linkedAsset";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("linkedCheck: something the host fetches from Scryfall and serves", () => {
  it("asks once, then again later while the host hasn't it, and tells its subscribers when it arrives", async () => {
    let there = false;
    const probe = vi.fn(async () => there);
    const check = linkedCheck("has-thing", probe);
    const seen = vi.fn();
    check.subscribe(seen);
    expect(await check()).toBe(false);
    expect(await check()).toBe(false); // the same answer, not a second request
    expect(probe).toHaveBeenCalledTimes(1);
    there = true; // the host fetched it in the background
    await vi.advanceTimersByTimeAsync(15_000);
    expect(probe).toHaveBeenCalledTimes(2);
    expect(check.ready()).toBe(true);
    expect(seen).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3_600_000);
    expect(probe).toHaveBeenCalledTimes(2); // there: nothing more to ask
  });

  it("asks less and less often while it stays missing, and a failed request counts as missing", async () => {
    const probe = vi.fn(async (): Promise<boolean> => { throw new Error("offline"); });
    const check = linkedCheck("has-thing", probe);
    expect(await check()).toBe(false);
    await vi.advanceTimersByTimeAsync(15_000);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(probe).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(299_000);
    expect(probe).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(probe).toHaveBeenCalledTimes(4);
  });
});

describe("the drawn card back", () => {
  it("is one SVG with the frame, the oval and the five colours, usable as a CSS background", () => {
    const svg = drawnBackSvg();
    expect(svg).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 630 880"/);
    expect(svg).not.toContain("<text"); // no wordmark: our own drawing
    for (const pip of ["#efe2a2", "#3fa3b5", "#4e4540", "#c74a2c", "#7da834"]) expect(svg).toContain(pip);
    expect(drawnBackUrl()).toMatch(/^data:image\/svg\+xml,%3Csvg/);
    expect(drawnBackUrl()).not.toMatch(/["#]/);
  });
});
