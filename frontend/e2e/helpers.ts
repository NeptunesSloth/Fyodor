import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";

export const PORT = Number(process.env.E2E_PORT ?? 8765);

/**
 * How a second browser reaches the table "from another device". By default it connects over
 * loopback with an X-Forwarded-For address on the LAN: the server trusts that header only from
 * loopback (as it does for the dev proxy), so it treats this browser exactly like a remote
 * device — no host library, no hot-seat powers. Set E2E_LAN_ORIGIN=http://<lan-ip>:<port> to use
 * a real network address instead.
 */
export function remoteDevice(): { baseURL?: string; extraHTTPHeaders?: Record<string, string> } {
  const origin = process.env.E2E_LAN_ORIGIN;
  if (origin) return { baseURL: origin };
  return { extraHTTPHeaders: { "X-Forwarded-For": "192.168.50.20" } };
}

export const ALICE_DECK = `Commander
1x Atraxa, Praetors' Voice (2x2) 190
Deck
1x Counterspell (cmm) 81
1x Swords to Plowshares (sta) 10
1x Opt (eld) 59
1x Sol Ring (cmm) 410
1x Arcane Signet (cmm) 370
1x Command Tower (cmm) 1000
12x Island (cmm) 1001
`;

export const BOB_DECK = `Commander
1x Krenko, Mob Boss (ddn) 13
Deck
1x Lightning Bolt (clb) 187
1x Pyroblast (ice) 213
1x Sol Ring (c21) 263
14x Mountain (cmm) 1003
`;

/** Names that must never reach another player's browser while those cards are hidden. */
export const ALICE_SECRETS = ["Counterspell", "Swords to Plowshares", "Opt", "Arcane Signet"];

export async function newPlayer(browser: Browser, remote = false): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext(remote ? remoteDevice() : {});
  const page = await context.newPage();
  return { context, page };
}

/** Records every WebSocket frame and HTTP JSON body the page receives. */
export function recordTraffic(page: Page): { text: () => string } {
  const chunks: string[] = [];
  page.on("websocket", (ws) => ws.on("framereceived", (f) => chunks.push(String(f.payload))));
  page.on("response", async (res) => {
    if (!res.url().includes("/api/")) return;
    if (!(res.headers()["content-type"] ?? "").includes("json")) return;
    try {
      chunks.push(await res.text());
    } catch {
      /* body gone (navigation) */
    }
  });
  return { text: () => chunks.join("\n") };
}

export async function hostLobby(page: Page, opts: { name: string; privacy?: string }): Promise<{ gameId: string; code: string }> {
  await page.goto("/#/play");
  await page.getByTestId("table-mode").selectOption("lan");
  await expect(page.getByTestId("use-lobby")).toBeChecked();
  await page.getByTestId("host-name").fill(opts.name);
  if (opts.privacy) await page.getByTestId("deck-privacy").selectOption(opts.privacy);
  await page.getByTestId("create-game").click();
  await expect(page.getByTestId("lobby")).toBeVisible();
  const code = (await page.getByTestId("room-code").textContent())!.trim();
  const gameId = page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
  return { gameId, code };
}

export async function joinLobby(page: Page, code: string, name: string): Promise<void> {
  await page.goto("/#/play");
  await page.getByTestId("join-code").fill(code);
  await page.getByTestId("join-name").fill(name);
  await page.getByTestId("join-submit").click();
  await expect(page.getByTestId("lobby")).toBeVisible();
}

export async function bringDeck(page: Page, text: string, name?: string): Promise<void> {
  await page.getByTestId("choose-deck").click();
  await page.getByRole("tab", { name: "Paste list" }).click();
  if (name) await page.getByLabel("Deck name").fill(name);
  await page.getByTestId("deck-text").fill(text);
  await page.getByTestId("use-deck").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

export function seatToken(page: Page, gameId: string): Promise<string | null> {
  return page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
}

/** The exact view the server sends this browser's seat. */
export async function serverView(page: Page, gameId: string): Promise<Record<string, unknown>> {
  const token = await seatToken(page, gameId);
  const res = await page.request.get(`/api/games/${gameId}/view`, { headers: token ? { "X-Seat-Token": token } : {} });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as Record<string, unknown>;
}

export const BOB_SECRETS = ["Lightning Bolt", "Pyroblast"];

/** Host + remote guest, decks chosen, everyone ready, game started. */
export async function startLanGame(browser: Browser, opts: { privacy?: string } = {}) {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  const hostTraffic = recordTraffic(host.page);
  const guestTraffic = recordTraffic(guest.page);
  const { gameId, code } = await hostLobby(host.page, { name: "Alice", privacy: opts.privacy });
  await joinLobby(guest.page, code, "Bob");
  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  await bringDeck(guest.page, BOB_DECK, "Goblins");
  await host.page.getByTestId("ready").click();
  await guest.page.getByTestId("ready").click();
  await expect(host.page.getByTestId("start-game")).toBeEnabled();
  await host.page.getByTestId("start-game").click();
  await expect(host.page.locator(".game-screen")).toBeVisible();
  await expect(guest.page.locator(".game-screen")).toBeVisible();
  return { host, guest, gameId, hostTraffic, guestTraffic };
}
