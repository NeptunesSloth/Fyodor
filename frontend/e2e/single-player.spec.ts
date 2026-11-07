import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, hostTable, seatToken } from "./helpers";

test("solo LAN night smoke: the host alone at a table, draw, tap, undo, redo", async ({ page }) => {
  // Two decks in the host library (the host computer may use the deck API).
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  // Solo testing is a LAN night with only the host seated (hot-seat tables are no longer offered).
  await hostTable(page, { players: 1, mulligan: "none" });
  await expect(page.locator(".seat-switch")).toHaveCount(0); // no "View" / "Act as": this browser is the host's seat
  const myHand = page.locator("main.table > .hand .hand-card");
  await expect(myHand).toHaveCount(0);

  await page.keyboard.press("d");
  await page.keyboard.press("d");
  await expect(myHand).toHaveCount(2);
  await page.keyboard.press("Control+z"); // nobody else at the table to ask: the undo happens at once
  await expect(myHand).toHaveCount(1);
  await page.keyboard.press("Control+Shift+z");
  await expect(myHand).toHaveCount(2);
  // No art cached and no Internet: cards render as readable text cards, never broken images.
  await expect(myHand.first().locator(".text-card .tc-name")).not.toBeEmpty();
  await expect(page.locator("main.table img:not([src])")).toHaveCount(0);

  // Play a land by double-clicking it, then tap it with T while hovered.
  const cardId = await myHand.first().getAttribute("data-card-id");
  await myHand.first().dblclick();
  await expect(myHand).toHaveCount(1);
  const permanent = page.locator(`.table-card[data-card-id="${cardId}"]`);
  await expect(permanent).toBeVisible();
  await permanent.hover();
  await page.keyboard.press("t");
  await expect(permanent).toHaveAttribute("data-tapped", "");
});

test("a saved game loads as a LAN night: the host back in their seat, a room code for the pod", async ({ page }) => {
  for (const text of [ALICE_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  const gameId = await hostTable(page, { players: 1, mulligan: "none" });
  await page.keyboard.press("d");
  await page.keyboard.press("d");
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(2);
  const token = await seatToken(page, gameId);
  const saved = await page.request.post(`/api/games/${gameId}/save`, { data: { name: "Solo shelf" }, headers: { "X-Seat-Token": token! } });
  expect(saved.ok(), await saved.text()).toBeTruthy();

  await page.goto("/#/play?tab=saves");
  const tile = page.locator(".pg-shelf .pg-tile", { hasText: "Solo shelf" });
  await expect(tile.getByRole("button", { name: "Load as LAN" })).toHaveCount(0); // Load is a LAN night already
  await tile.getByRole("button", { name: "Load", exact: true }).click();
  await expect(page.locator(".game-screen")).toBeVisible();
  await expect(page.locator(".game-top .room-code")).toContainText("Room");
  await expect(page.locator(".seat-switch")).toHaveCount(0); // not a hot-seat table: no View / Act as
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(2); // seated as the host, with the hand
});
