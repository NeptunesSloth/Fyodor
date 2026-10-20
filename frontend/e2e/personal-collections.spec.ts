import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, bringDeck, hostLobby, joinLobby, newPlayer, recordTraffic, seatToken } from "./helpers";

test("personal bulk imports survive reload, work offline, and remain the guest's collection", async ({ browser }) => {
  const host = await newPlayer(browser);
  const guest = await newPlayer(browser, true);
  try {
    for (const p of [host.page, guest.page]) await p.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
    const hostTraffic = recordTraffic(host.page);
    const { gameId, code } = await hostLobby(host.page, { name: "Alice" });
    await joinLobby(guest.page, code, "Bob");
    await guest.page.getByTestId("choose-deck").click();
    await guest.page.getByRole("tab", { name: "My decks", exact: true }).click();
    await guest.page.locator('input[type="file"][multiple]').setInputFiles([
      { name: "Offline Goblins.txt", mimeType: "text/plain", buffer: Buffer.from(BOB_DECK) },
      { name: "Private Reserve.txt", mimeType: "text/plain", buffer: Buffer.from("2 Grizzly Bears") },
      { name: "Invalid.txt", mimeType: "text/plain", buffer: Buffer.from("") },
    ]);
    await expect(guest.page.getByText(/saved for offline play/)).toHaveCount(2);
    await expect(guest.page.getByText(/Invalid.txt: not saved/)).toBeVisible();
    const downloadReady = guest.page.waitForEvent("download");
    await guest.page.getByRole("button", { name: "Export My decks", exact: true }).click();
    const backup = await downloadReady;
    const backupPath = await backup.path();
    expect(backupPath).toBeTruthy();
    await guest.page.evaluate(() => localStorage.removeItem("fyodor.myDecks"));
    await guest.page.reload();
    await expect(guest.page.getByTestId("lobby")).toBeVisible();
    await guest.page.getByTestId("choose-deck").click();
    await guest.page.getByRole("tab", { name: "My decks", exact: true }).click();
    await guest.page.locator('input[type="file"][multiple]').setInputFiles(backupPath!);
    await expect(guest.page.getByText(/saved for offline play/)).toHaveCount(2);
    await guest.page.reload();
    await expect(guest.page.getByTestId("lobby")).toBeVisible();
    const remoteFetches: string[] = [];
    await guest.page.route("**/api/games/*/lobby/import", async route => {
      const body = route.request().postDataJSON() as { archidekt?: string };
      if (body.archidekt) { remoteFetches.push(body.archidekt); await route.abort(); }
      else await route.continue();
    });
    await guest.page.getByTestId("choose-deck").click();
    await guest.page.getByRole("tab", { name: "My decks", exact: true }).click();
    await expect(guest.page.getByRole("button", { name: /^Private Reserve/ })).toBeVisible();
    await guest.page.getByRole("button", { name: /^Offline Goblins/ }).click();
    await expect(guest.page.getByRole("dialog")).toHaveCount(0);
    await bringDeck(host.page, ALICE_DECK, "Host deck");
    await host.page.getByTestId("ready").click();
    await guest.page.getByTestId("ready").click();
    await host.page.getByTestId("start-game").click();
    await expect(guest.page.locator(".game-screen")).toBeVisible();
    const token = await seatToken(guest.page, gameId);
    const own = await guest.page.request.get(`/api/games/${gameId}/collection`, { headers: { "X-Seat-Token": token! } });
    expect(await own.json()).toEqual([expect.objectContaining({ name: "Grizzly Bears", quantity: 2 })]);
    const hostToken = await seatToken(host.page, gameId);
    const other = await host.page.request.get(`/api/games/${gameId}/collection?viewer=p2`, { headers: { "X-Seat-Token": hostToken! } });
    expect(JSON.stringify(await other.json())).not.toContain("Grizzly Bears");
    expect(hostTraffic.text()).not.toContain("Grizzly Bears");
    expect(remoteFetches).toEqual([]);
  } finally {
    await guest.context.close();
    await host.context.close();
  }
});
