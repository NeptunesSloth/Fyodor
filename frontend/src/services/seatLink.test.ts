import { afterEach, describe, expect, it, vi } from "vitest";
import { adoptSeatLink, readSeatLink } from "./seatLink";

const remembered: [string, string][] = [];
vi.mock("./games", () => ({ rememberSeat: (id: string, token: string) => remembered.push([id, token]) }));

function page(pathname: string, search: string, hash: string) {
  const loc = { pathname, search, hash, get href() { return `http://table.local${this.pathname}${this.search}${this.hash}`; } };
  const history = {
    state: null,
    replaceState: vi.fn((_state: unknown, _title: string, url: string) => {
      const u = new URL(url, "http://table.local");
      loc.pathname = u.pathname;
      loc.search = u.search;
      loc.hash = u.hash;
    }),
  };
  vi.stubGlobal("window", { location: loc, history });
  return loc;
}

afterEach(() => {
  vi.unstubAllGlobals();
  remembered.length = 0;
});

describe("seat links", () => {
  it("reads the token from the fragment, keeps the seat and leaves no token in the address", () => {
    const loc = page("/", "", "#/game/g1?seat_token=tok123");
    adoptSeatLink("g1");
    expect(remembered).toEqual([["g1", "tok123"]]);
    expect(loc.href).toBe("http://table.local/#/game/g1");
    expect(loc.href).not.toContain("seat_token");
  });

  it("reads a real query-string token (a hand-built link) once and strips it from both positions", () => {
    const loc = page("/", "?seat_token=tok123&x=1", "#/game/g1?seat_token=tok123&y=2");
    adoptSeatLink();
    expect(remembered).toEqual([["g1", "tok123"]]);
    expect(loc.href).toBe("http://table.local/?x=1#/game/g1?y=2");
    expect(loc.href).not.toContain("seat_token");
    adoptSeatLink(); // nothing left to take
    expect(remembered).toHaveLength(1);
  });

  it("takes the game from the route when the page does not say", () => {
    page("/", "?seat_token=abc", "#/game/g%201");
    adoptSeatLink();
    expect(remembered).toEqual([["g 1", "abc"]]);
  });

  it("does nothing to an address without a seat token", () => {
    const loc = page("/", "", "#/play?code=ABC");
    adoptSeatLink("g1");
    expect(loc.href).toBe("http://table.local/#/play?code=ABC");
    expect(remembered).toEqual([]);
    expect(readSeatLink({ pathname: "/", search: "", hash: "#/play" })).toBeNull();
  });
});
