import { describe, expect, it, vi } from "vitest";
import { retryAfter429 } from "./imageRetry";

const reply = (status: number) => vi.fn(async () => new Response(null, { status }));

describe("retryAfter429", () => {
  it("waits a second and says retry when the server answered 429", async () => {
    const wait = vi.fn(async () => undefined);
    await expect(retryAfter429("/api/cards/x/image", reply(429), wait)).resolves.toBe(true);
    expect(wait).toHaveBeenCalledWith(1000);
  });
  it("does not retry any other answer, or an unreachable server", async () => {
    const wait = vi.fn(async () => undefined);
    await expect(retryAfter429("/x", reply(404), wait)).resolves.toBe(false);
    await expect(retryAfter429("/x", vi.fn(async () => { throw new Error("offline"); }), wait)).resolves.toBe(false);
    expect(wait).not.toHaveBeenCalled();
  });
});
