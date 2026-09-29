import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("prefixes /api and parses JSON", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.get("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
  });

  it("raises ApiError with the server detail", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "nope" }), { status: 404 }));
    await expect(api.get("/x")).rejects.toMatchObject({ status: 404, message: "nope" });
    await expect(api.get("/x")).rejects.toBeInstanceOf(ApiError);
  });
});
