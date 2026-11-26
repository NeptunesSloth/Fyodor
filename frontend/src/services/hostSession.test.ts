import { afterEach, describe, expect, it, vi } from "vitest";
import { claimHostSession } from "./hostSession";

function page(hash: string) {
  const replaceState = vi.fn();
  vi.stubGlobal("location", { hash, pathname: "/", search: "" });
  vi.stubGlobal("history", { replaceState });
  return replaceState;
}

afterEach(() => vi.unstubAllGlobals());

describe("claimHostSession", () => {
  it("posts the secret from the address and clears it from the address bar", async () => {
    const replaceState = page("#host=abc");
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(claimHostSession()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/host/session", expect.objectContaining({ method: "POST", body: JSON.stringify({ secret: "abc" }) }));
    expect(replaceState).toHaveBeenCalledWith(null, "", "/");
  });

  it("posts nothing without a secret in the address", async () => {
    const replaceState = page("#/play");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(claimHostSession()).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(replaceState).not.toHaveBeenCalled();
  });

  it("leaves the user a guest on a refusal, and still clears the address", async () => {
    const replaceState = page("#host=wrong");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })));
    await expect(claimHostSession()).resolves.toBe(false);
    expect(replaceState).toHaveBeenCalled();
  });

  it("is a guest when the server cannot be reached", async () => {
    page("#host=abc");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(claimHostSession()).resolves.toBe(false);
  });
});
