import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, cardDbState } from "./api";

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

describe("cardDbState", () => {
  const db = { available: true, printings: 2, oracle_cards: 1, tokens: 0, images: 0, bulk_type: null, bulk_updated_at: null, imported_at: null };
  it("tells the host's browser about its card database", () => {
    expect(cardDbState(null)).toBe("unknown");
    expect(cardDbState({ status: "ok", version: "1", card_database: db })).toBe("ready");
    expect(cardDbState({ status: "ok", version: "1", card_database: { ...db, available: false } })).toBe("missing");
  });

  it("says nothing to a guest, whose health has no card_database (a host matter)", () => {
    expect(cardDbState({ status: "ok", version: "1" })).toBe("not-told");
    expect(cardDbState({ status: "ok", version: "1", tunnel: true })).toBe("not-told");
  });
});
