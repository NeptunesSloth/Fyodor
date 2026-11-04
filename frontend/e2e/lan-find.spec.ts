import { expect, test, type Page } from "@playwright/test";
import { BOB_DECK, PORT, hostLobby, newPlayer } from "./helpers";


/** Name this browser's profile (the name a join sends). */
async function profileName(page: Page, name: string): Promise<void> {
  await page.addInitScript((n) => {
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: n, avatar: n[0], prefs: { ambience: false } }] }));
  }, name);
}

/** Open a LAN lobby with its own table name (tables of earlier tests stay open on the shared server). */
async function openLobby(page: Page, opts: { table: string; name: string; password?: string }): Promise<{ gameId: string; code: string }> {
  await page.goto("/#/play");
  await page.getByLabel("Table name").fill(opts.table);
  await page.getByTestId("host-name").fill(opts.name);
  if (opts.password) await page.locator(".pg-pass input").fill(opts.password);
  await page.getByTestId("create-game").click();
  await expect(page.getByTestId("lobby")).toBeVisible();
  const code = (await page.getByTestId("room-code").textContent())!.trim();
  return { gameId: page.url().split("/game/")[1]!.split(/[?#]/)[0]!, code };
}

/** A tile on the Play page's "Tables in progress". */
const tile = (page: Page, name: string) => page.locator(".pg-shelf .pg-tile", { hasText: name });

test("a device on the network joins a lobby right from its tile", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  await profileName(guest.page, "Bob");
  const { code } = await openLobby(host.page, { table: "Tile night", name: "Alice" });

  await guest.page.goto("/#/play");
  await expect(guest.page.getByRole("heading", { name: "You're connected to a host" })).toBeVisible();
  const lobby = tile(guest.page, "Tile night");
  await expect(lobby).toContainText(code);
  await expect(lobby).toContainText("In the lobby");
  await lobby.getByRole("button", { name: "Join “Tile night”" }).click();

  await expect(guest.page.getByTestId("lobby")).toBeVisible();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Bob");
  // back on the Play page, this browser's seat opens instead of taking another one
  await guest.page.goto("/#/play");
  await expect(tile(guest.page, "Tile night").getByRole("button", { name: "Open “Tile night”" })).toBeVisible();
  await expect(tile(guest.page, "Tile night").getByRole("button", { name: /^Join/ })).toHaveCount(0);

  await host.context.close();
  await guest.context.close();
});

test("a table with a password asks for it on the tile, and the server has the last word", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  await profileName(guest.page, "Bob");
  await openLobby(host.page, { table: "Locked night", name: "Alice", password: "s3cret" });

  await guest.page.goto("/#/play");
  const locked = tile(guest.page, "Locked night");
  await expect(locked.getByRole("img", { name: "Password" })).toBeVisible();
  await locked.getByRole("button", { name: "Join “Locked night”" }).click();
  await locked.getByTestId("tile-password").fill("wrong");
  await locked.getByRole("button", { name: "Join", exact: true }).click();
  await expect(guest.page.getByText("Unknown room code or wrong password")).toBeVisible();
  await locked.getByTestId("tile-password").fill("s3cret");
  await locked.getByRole("button", { name: "Join", exact: true }).click();
  await expect(guest.page.getByTestId("lobby")).toBeVisible();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Bob");

  await host.context.close();
  await guest.context.close();
});

test("a join link from another computer's Fyodor lands in the lobby, seated", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  const watcher = await newPlayer(browser, true);
  const { gameId, code } = await openLobby(host.page, { table: "Link night", name: "Alice" });

  await guest.page.goto(`/#/play?code=${code}&name=Carol&join=1`);
  await expect(guest.page.getByTestId("lobby")).toBeVisible();
  expect(guest.page.url()).toContain(`#/game/${gameId}`);
  await expect(host.page.getByTestId("seat-p2")).toContainText("Carol");

  await watcher.page.goto(`/#/play?code=${code}&watch=1`);
  await expect(watcher.page.getByTestId("lobby")).toBeVisible();
  const token = await watcher.page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
  const lobby = await watcher.page.request.get(`/api/games/${gameId}/lobby`, { headers: { "X-Seat-Token": token! } });
  expect((await lobby.json()).viewer).toBe("__spectator__");

  await host.context.close();
  await guest.context.close();
  await watcher.context.close();
});

test("Games on your network: Join brings my decks, and they wait on my seat", async ({ browser }) => {
  const host = await newPlayer(browser);
  const friend = await newPlayer(browser); // the friend's own Fyodor (here the same server stands in for both computers)
  await profileName(friend.page, "Dana");
  const { code } = await hostLobby(host.page, { name: "Alice" });
  const made = await friend.page.request.post("/api/decks", { data: { name: "Goblins", text: BOB_DECK } });
  expect(made.ok(), await made.text()).toBeTruthy();

  // what the network answers (a real scan needs two computers: lan-offline.spec.ts): this server, under another name
  await friend.page.route("**/api/lan/nearby", (route) => route.fulfill({ json: [{
    name: "DESKTOP-42", url: `http://127.0.0.1:${PORT}`, version: "0.1.0",
    tables: [{ id: "x", name: "Commander night", format: "commander", phase: "lobby", code, has_password: false,
               seats: 4, taken: 1, open: 3, players: ["Alice"], turn: 0 }],
  }] }));
  await friend.page.goto("/#/play");
  const near = friend.page.getByTestId("nearby-games");
  await expect(near.getByRole("heading", { name: "Games on your network" })).toBeVisible();
  const row = near.getByTestId("nearby-table");
  await expect(row).toContainText("DESKTOP-42");
  await expect(row).toContainText("In the lobby · 1 of 4 seats taken");
  await expect(near.getByTestId("bring-decks")).toContainText(/with you when you join/);
  await row.getByRole("button", { name: "Join “Commander night” on DESKTOP-42" }).click();

  // seated, with my decks right on my seat: one click plays one
  await expect(friend.page.getByTestId("lobby")).toBeVisible();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Dana");
  const own = friend.page.getByTestId("seat-p2").getByTestId("own-decks");
  await expect(own).toContainText(/Your decks, from /);
  await expect(own).toContainText("Krenko, Mob Boss");
  await own.getByRole("button", { name: "Use “Goblins”" }).click();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Krenko, Mob Boss");

  // Choose deck opens on them too; the host's own Choose deck has no such tab (the library went to Dana's seat alone)
  await friend.page.getByTestId("choose-deck").click();
  await expect(friend.page.getByRole("tab", { name: /^Your decks, from / })).toHaveAttribute("aria-selected", "true");
  await expect(friend.page.getByTestId("brought-decks")).toContainText("Goblins");
  await friend.page.keyboard.press("Escape");
  await host.page.getByTestId("choose-deck").click();
  await expect(host.page.getByRole("tab", { name: "Table decks" })).toBeVisible();
  await expect(host.page.getByRole("tab", { name: /^Your decks, from / })).toHaveCount(0);

  await host.context.close();
  await friend.context.close();
});

test("a player with only a browser brings the decks saved in it, and learns they belong to this address", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  await guest.page.addInitScript((deck) => {
    localStorage.setItem("fyodor.myDecks", JSON.stringify([{ id: "m1", name: "Mono red", body: { name: "Mono red", text: deck },
      commanders: ["Krenko, Mob Boss"], savedAt: 1 }]));
  }, BOB_DECK);
  const { code } = await openLobby(host.page, { table: "Browser night", name: "Alice" });
  await guest.page.goto(`/#/play?code=${code}&name=Erin&join=1`);
  const own = guest.page.getByTestId("seat-p2").getByTestId("own-decks");
  await expect(own).toContainText("Your decks in this browser");
  await own.getByRole("button", { name: "Use “Mono red”" }).click();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Krenko, Mob Boss");
  await guest.page.getByTestId("choose-deck").click();
  await expect(guest.page.getByRole("tab", { name: "My decks", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(guest.page.getByTestId("my-decks-address")).toContainText(`127.0.0.1:${PORT}`);
  await expect(guest.page.getByRole("button", { name: "Export My decks", exact: true })).toBeVisible();
  await host.context.close();
  await guest.context.close();
});
