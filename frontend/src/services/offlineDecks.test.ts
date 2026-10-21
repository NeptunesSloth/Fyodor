import { afterEach, expect, it, vi } from "vitest";
import { saveDeckForOffline } from "./offlineDecks";

afterEach(() => vi.unstubAllGlobals());

function server(art: "ready" | "missing" | "failed" | "token-missing") {
  const requests: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    requests.push(url);
    const data = url === "/api/decks" ? { id: "saved", name: "My deck" }
      : url.endsWith("/cache-art") ? { id: "job" }
      : url === "/api/jobs/job" ? { state: art === "failed" ? "failed" : "done", failed: (art === "missing" || art === "token-missing") ? 1 : 0, message: "Download failed" }
      : { missing: art === "missing" ? 1 : 0, printings: 2 };
    return new Response(JSON.stringify(data), { status: 200 });
  });
  return requests;
}

it("confirms offline artwork only after the download job and cache check complete", async () => {
  const requests = server("ready");
  const result = await saveDeckForOffline({ text: "1 Sol Ring" }, true);
  expect(result.deck.id).toBe("saved");
  expect(result.artwork).toBe("ready");
  expect(requests).toEqual(["/api/decks", "/api/decks/saved/cache-art", "/api/jobs/job", "/api/decks/saved/art-status"]);
});

it.each(["missing", "failed", "token-missing"] as const)("keeps the saved deck when artwork is %s", async art => {
  const requests = server(art);
  const result = await saveDeckForOffline({ text: "1 Sol Ring" }, true);
  expect(result.deck.id).toBe("saved");
  expect(result.artwork).toBe("incomplete");
  expect(result.notice).toBeTruthy();
  expect(requests.filter(r => r === "/api/decks")).toHaveLength(1);
});

it("saves without requesting downloads when artwork caching is disabled", async () => {
  const requests = server("ready");
  const result = await saveDeckForOffline({ text: "1 Sol Ring" }, false);
  expect(result.artwork).toBe("not-requested");
  expect(requests).toEqual(["/api/decks"]);
});
