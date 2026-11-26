import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/games", () => ({ rememberSeat: () => {} }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("the route module's remembered address", () => {
  it("does not keep a seat token or the host secret that main.tsx takes off the address after the module is imported", async () => {
    vi.resetModules();
    const loc = { pathname: "/", search: "", hash: "#/game/g1?seat_token=tok123" };
    vi.stubGlobal("window", {
      location: loc,
      history: { state: null, replaceState: (_s: unknown, _t: string, url: string) => { loc.hash = new URL(url, "http://t").hash; } },
    });
    const route = await import("./useHashRoute"); // imported first, as App imports it before main.tsx runs
    const { adoptSeatLink } = await import("../services/seatLink");
    adoptSeatLink();
    expect(route.acceptedHash()).toBe("#/game/g1");
    expect(route.acceptedHash()).not.toContain("seat_token");
  });
});
