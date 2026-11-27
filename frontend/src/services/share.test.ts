import { afterEach, describe, expect, it, vi } from "vitest";
import { getShare, startShare, stopShare } from "./share";

const status = { shared: false, state: "stopped", reason: null, link: null, has_password: false, available: true };

function stub() {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(status), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
afterEach(() => vi.unstubAllGlobals());

describe("the share calls", () => {
  it("reads the status with a GET and no body", async () => {
    const f = stub();
    await expect(getShare("g1")).resolves.toEqual(status);
    expect(f).toHaveBeenCalledWith("/api/games/g1/share", expect.objectContaining({ method: "GET", body: undefined }));
  });
  it("starts with a POST that carries the password only when given", async () => {
    const f = stub();
    await startShare("g1");
    expect(f).toHaveBeenLastCalledWith("/api/games/g1/share", expect.objectContaining({ method: "POST", body: "{}" }));
    await startShare("g1", "correct horse");
    expect(f).toHaveBeenLastCalledWith("/api/games/g1/share", expect.objectContaining({ method: "POST", body: JSON.stringify({ password: "correct horse" }) }));
    await startShare("g1", "");
    expect(f).toHaveBeenLastCalledWith("/api/games/g1/share", expect.objectContaining({ body: "{}" }));
  });
  it("stops with a DELETE", async () => {
    const f = stub();
    await stopShare("g1");
    expect(f).toHaveBeenCalledWith("/api/games/g1/share", expect.objectContaining({ method: "DELETE", body: undefined }));
  });
});
