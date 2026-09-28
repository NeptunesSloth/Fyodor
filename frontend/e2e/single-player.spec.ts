import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

test("hot-seat smoke: create a table, draw, tap, undo, redo", async ({ page }) => {
  // Two decks in the host library (the host computer may use the deck API).
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  await page.goto("/#/play");
  await page.getByTestId("mulligan-rule").selectOption("none");
  await page.getByTestId("create-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();
  const myHand = page.locator("main.table > .hand .hand-card");
  await expect(myHand).toHaveCount(0);

  await page.keyboard.press("d");
  await page.keyboard.press("d");
  await expect(myHand).toHaveCount(2);
  await page.keyboard.press("Control+z");
  await expect(myHand).toHaveCount(1);
  await page.keyboard.press("Control+Shift+z");
  await expect(myHand).toHaveCount(2);

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
