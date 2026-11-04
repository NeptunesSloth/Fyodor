import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, hostTable } from "./helpers";

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
