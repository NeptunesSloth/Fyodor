import { describe, expect, it, vi } from "vitest";
import { imageErrorPlan, retryDelay, scheduleRetry } from "./imageRetry";

describe("the image retry", () => {
  it("retries once per src on the tunnel, then falls back", () => {
    expect(imageErrorPlan(true, null, "a")).toBe("retry");
    expect(imageErrorPlan(true, "a", "a")).toBe("fail");
    expect(imageErrorPlan(true, "a", "b")).toBe("retry");
  });
  it("never retries off the tunnel", () => {
    expect(imageErrorPlan(false, null, "a")).toBe("fail");
  });
  it("waits 800 to 2000 ms", () => {
    expect(retryDelay(() => 0)).toBe(800);
    expect(retryDelay(() => 0.5)).toBe(1400);
    expect(retryDelay(() => 0.999999)).toBeLessThan(2000);
  });
  it("fires once after the delay, and not at all once cancelled (unmount)", () => {
    const set = vi.fn((fn: () => void, _ms: number) => { fired.push(fn); return 7; });
    const clear = vi.fn((id: unknown) => { if (id === 7) fired.length = 0; });
    const fired: (() => void)[] = [];
    const again = vi.fn();
    const cancel = scheduleRetry(again, () => 0.5, { set, clear });
    expect(set).toHaveBeenCalledWith(again, 1400);
    cancel();
    fired.forEach((f) => f());
    expect(clear).toHaveBeenCalledWith(7);
    expect(again).not.toHaveBeenCalled();
  });
});
