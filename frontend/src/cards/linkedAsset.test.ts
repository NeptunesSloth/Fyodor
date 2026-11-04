import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { grainAt, PIP_COLOURS } from "./drawnBack";
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
  it("is our own drawing: the five colours in the printed order, a grain strongest on the frame", () => {
    expect(PIP_COLOURS).toEqual(["#efe2a2", "#3fa3b5", "#4e4540", "#c74a2c", "#7da834"]);
    expect(grainAt(30, 440)).toBeGreaterThan(grainAt(315, 440)); // the frame's grain is coarser than the oval's
    expect(grainAt(315, 440)).toBeGreaterThan(grainAt(5, 5)); // and the black border has almost none
  });
});
