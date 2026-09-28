import { expect, test } from "@playwright/test";
import { ALICE_DECK, ALICE_SECRETS, BOB_DECK, bringDeck, hostLobby, joinLobby, newPlayer, recordTraffic, serverView } from "./helpers";

test("LAN lobby: each player brings their own deck, readies up, host starts", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  const guestTraffic = recordTraffic(guest.page);

  const { gameId, code } = await hostLobby(host.page, { name: "Alice" });
  await joinLobby(guest.page, code, "Bob");

  // Both see both seats live.
  await expect(host.page.getByTestId("seat-p2")).toContainText("Bob");
  await expect(guest.page.getByTestId("seat-p1")).toContainText("Alice");

  // The guest on another device cannot browse the host's deck library.
  await guest.page.getByTestId("choose-deck").click();
  await expect(guest.page.getByRole("tab", { name: "My decks" })).toBeVisible();
  await expect(guest.page.getByRole("tab", { name: "Table decks" })).toHaveCount(0);
  await guest.page.keyboard.press("Escape");
  expect((await guest.page.request.get("/api/decks")).status()).toBe(403);
  await host.page.getByTestId("choose-deck").click();
  await expect(host.page.getByRole("tab", { name: "Table decks" })).toBeVisible();
  await host.page.keyboard.press("Escape");

  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  await bringDeck(guest.page, BOB_DECK, "Goblins");

  // Commander-only privacy (the default): commander and deck name, never the list.
  await expect(guest.page.getByTestId("seat-p1")).toContainText("Atraxa, Praetors' Voice");
  await expect(guest.page.getByTestId("seat-p1")).toContainText("Superfriends");
  await expect(guest.page.getByTestId("seat-p1").getByRole("button", { name: "View list" })).toHaveCount(0);
  await expect(host.page.getByTestId("seat-p2")).toContainText("Krenko, Mob Boss");

  // Start is blocked until everyone is ready.
  await expect(host.page.getByTestId("start-game")).toBeDisabled();
  await host.page.getByTestId("ready").click();
  await expect(host.page.getByTestId("start-game")).toBeDisabled();
  await guest.page.getByTestId("ready").click();
  await expect(host.page.getByTestId("seat-p2")).toContainText("Ready");
  await expect(host.page.getByTestId("start-game")).toBeEnabled();
  await host.page.getByTestId("start-game").click();

  // Both browsers switch to the table, same URL, each in their own seat.
  await expect(host.page.locator(".game-screen")).toBeVisible();
  await expect(guest.page.locator(".game-screen")).toBeVisible();
  const aliceView = await serverView(host.page, gameId);
  const bobView = await serverView(guest.page, gameId);
  expect(aliceView.viewer).toBe("p1");
  expect(bobView.viewer).toBe("p2");
  const players = bobView.players as { name: string; library_count: number; deck_name?: string }[];
  expect(players.map((p) => p.name)).toEqual(["Alice", "Bob"]);
  // opening hands (7) are dealt under the default Commander London rule
  expect(players[0]!.library_count).toBe(11);
  expect(players[1]!.library_count).toBe(10);

  // Nothing from Alice's library ever reached Bob's browser.
  const seen = guestTraffic.text();
  for (const name of ALICE_SECRETS) expect(seen).not.toContain(name);

  await host.context.close();
  await guest.context.close();
});

test("LAN lobby: private decks reveal nothing but a card count", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  const guestTraffic = recordTraffic(guest.page);
  const { code } = await hostLobby(host.page, { name: "Alice", privacy: "private" });
  await joinLobby(guest.page, code, "Bob");
  await bringDeck(host.page, ALICE_DECK, "Superfriends");
  await expect(guest.page.getByTestId("seat-p1")).toContainText("19 cards");
  await expect(guest.page.getByTestId("seat-p1")).not.toContainText("Atraxa");
  expect(guestTraffic.text()).not.toContain("Superfriends");
  expect(guestTraffic.text()).not.toContain("Atraxa");
  await host.context.close();
  await guest.context.close();
});
