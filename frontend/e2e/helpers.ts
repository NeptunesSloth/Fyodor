import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import * as zlib from "node:zlib";

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

/**
 * Host a LAN lobby. Seats keep their join order unless `turnOrder: "pod"` (the d20 pod rule reseats
 * players by their rolls), so most tests can name seats p1, p2… in join order.
 */
export async function hostLobby(page: Page, opts: { name: string; privacy?: string; turnOrder?: "pod" | "random" }): Promise<{ gameId: string; code: string }> {
  await page.goto("/#/play");
  await expect(page.getByTestId("use-lobby")).toBeChecked(); // every new game is a LAN night, and the pod brings decks by default
  await page.getByTestId("host-name").fill(opts.name);
  if (opts.privacy) await page.getByTestId("deck-privacy").selectOption(opts.privacy);
  await page.getByTestId("create-game").click();
  await expect(page.getByTestId("lobby")).toBeVisible();
  const code = (await page.getByTestId("room-code").textContent())!.trim();
  const gameId = page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
  if ((opts.turnOrder ?? "random") === "random") {
    const token = await page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
    const res = await page.request.post(`/api/games/${gameId}/lobby/settings`, { data: { turn_order: "random" }, headers: token ? { "X-Seat-Token": token } : {} });
    expect(res.ok(), await res.text()).toBeTruthy();
  }
  return { gameId, code };
}

/**
 * A LAN night set up on the Play page without a lobby: the host's own decks go to the seats (the first player is the host's
 * seat; the others stay open for the pod). `players: 1` is solo testing: the host alone at the table.
 */
export async function hostTable(page: Page, opts: { players?: number; deck?: string; mulligan?: string; automation?: string; format?: "commander" | "sandbox"; first?: string } = {}): Promise<string> {
  await page.goto(opts.deck ? `/#/play?deck=${opts.deck}` : "/#/play"); // `deck`: the first seat's (the host's) deck
  await expect(page.getByTestId("create-game")).toBeVisible();
  if (opts.format) await page.getByTestId(`format-${opts.format}`).check();
  await page.locator(".pg-toggle").click(); // "Players bring their own decks": off
  await expect(page.getByTestId("use-lobby")).not.toBeChecked();
  const want = opts.players ?? 2;
  for (let n = await page.locator(".pg-seat").count(); n > want; n--) await page.getByRole("button", { name: "Remove player" }).last().click();
  await expect(page.locator(".pg-seat")).toHaveCount(want);
  if (opts.mulligan) await page.getByTestId("mulligan-rule").selectOption(opts.mulligan);
  if (opts.automation) await page.getByTestId("automation-level").selectOption(opts.automation);
  if (opts.first) await page.getByTestId("first-player").selectOption(opts.first);
  await page.getByTestId("create-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();
  return page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
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

/** Perform an action as this browser's seat (through the same REST API the UI uses). */
export async function act(page: Page, gameId: string, action: Record<string, unknown>): Promise<Record<string, unknown>> {
  const token = await seatToken(page, gameId);
  const res = await page.request.post(`/api/games/${gameId}/actions`, {
    data: { action },
    headers: token ? { "X-Seat-Token": token } : {},
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return (await res.json()) as Record<string, unknown>;
}

/** Everyone keeps their opening hand. */
export async function keepAll(...pages: Page[]): Promise<void> {
  for (const p of pages) await p.getByTestId("mull-keep").click();
  for (const p of pages) await expect(p.getByTestId("mulligan")).toHaveCount(0);
}

/** Click through a context-menu path, e.g. menuPath(page, "Effects", "Flying"). */
export async function menuPath(page: Page, ...labels: string[]): Promise<void> {
  for (const label of labels) {
    await page.locator(".ctx-menu .ctx-item", { hasText: label }).last().click();
  }
}

/** Play a card from this browser's hand onto the battlefield; returns its id. */
export async function playFromHand(page: Page, index = 0): Promise<string> {
  const hand = page.locator("main.table > .hand .hand-card");
  const id = (await hand.nth(index).getAttribute("data-card-id"))!;
  await hand.nth(index).dblclick();
  await expect(page.locator(`.table-card[data-card-id="${id}"]`)).toBeVisible();
  return id;
}

/** A tiny real PNG (for asset uploads in tests). */
export function pngBuffer(width = 8, height = 8, rgb: [number, number, number] = [150, 30, 30]): Buffer {
  const chunk = (tag: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(tag, "ascii"), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(body) >>> 0);
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const rows = Buffer.concat(Array.from({ length: height }, () => Buffer.concat([Buffer.from([0]), Buffer.from(Array(width).fill(rgb).flat())])));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

/**
 * Saves Alice's and Bob's decks and returns them in that order, by the ids the server gave them. (The deck list is newest first, to the
 * second: when the two saves fall in different seconds Bob's deck comes first, and other tests on this server save decks too.)
 */
export async function saveDecks(page: Page, texts: string[] = [ALICE_DECK, BOB_DECK]): Promise<{ id: string; name: string }[]> {
  const decks: { id: string; name: string }[] = [];
  for (const text of texts) {
    const made = await page.request.post("/api/decks", { data: { text } });
    expect(made.ok(), await made.text()).toBeTruthy();
    decks.push((await made.json()) as { id: string; name: string });
  }
  return decks;
}
