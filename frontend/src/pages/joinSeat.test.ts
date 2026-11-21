import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../services/api";
import { joinWithPreferredSeat } from "./joinSeat";

const BODY = { code: "ABCDEF", spectate: false };
const OK = { game_id: "g", token: "t" };

describe("joining with a preferred seat", () => {
  it("a wrong code or password (403) is one request, not two", async () => {
    const join = vi.fn().mockRejectedValue(new ApiError(403, "Unknown room code or wrong password"));
    await expect(joinWithPreferredSeat(join, BODY, "p2")).rejects.toThrow("Unknown room code");
    expect(join).toHaveBeenCalledTimes(1);
  });
  it("too many attempts (429) is one request and its message reaches the caller", async () => {
    const join = vi.fn().mockRejectedValue(new ApiError(429, "Too many attempts. Try again in a few minutes."));
    await expect(joinWithPreferredSeat(join, BODY, "p2")).rejects.toThrow("Too many attempts");
    expect(join).toHaveBeenCalledTimes(1);
  });
  it("a seat that is taken (409) or missing (404) retries without the seat", async () => {
    for (const status of [409, 404]) {
      const join = vi.fn().mockRejectedValueOnce(new ApiError(status, "no")).mockResolvedValueOnce(OK);
      await expect(joinWithPreferredSeat(join, BODY, "p2")).resolves.toBe(OK);
      expect(join.mock.calls).toEqual([[{ ...BODY, seat: "p2" }], [BODY]]);
    }
  });
  it("without a preferred seat, or when spectating, it asks once without one", async () => {
    const join = vi.fn().mockResolvedValue(OK);
    await joinWithPreferredSeat(join, BODY, null);
    await joinWithPreferredSeat(join, { ...BODY, spectate: true }, "p2");
    expect(join.mock.calls).toEqual([[BODY], [{ ...BODY, spectate: true }]]);
  });
});
