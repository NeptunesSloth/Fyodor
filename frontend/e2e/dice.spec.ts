import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

test("dice you can see: a roll lands on the roller's mat for everyone, with the server's numbers", async ({ page }) => {
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Dice", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  // rolls already in the log when the table opens aren't replayed; a new one is
  await expect(page.getByTestId("dice-throw")).toHaveCount(0);
  const roll = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "roll", sides: 6, count: 2 }, as: "p2" } });
  expect(roll.ok()).toBeTruthy();
  const throwEl = page.getByTestId("dice-throw");
  await expect(throwEl).toHaveCount(1);
  await expect(throwEl.locator(".die2d")).toHaveCount(2);
  const view = (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { log: { roll?: { results: number[] } }[] };
  const results = view.log.filter((e) => e.roll).at(-1)!.roll!.results;
  await expect(throwEl).toContainText(`Bob · 2d6: ${results[0]} + ${results[1]} = ${results[0]! + results[1]!}`);
  // it lands on Bob's mat
  const mat = (await page.locator('[data-drop="p2:battlefield"]').boundingBox())!;
  const box = (await throwEl.boundingBox())!;
  expect(box.x + box.width / 2).toBeGreaterThan(mat.x);
  expect(box.x + box.width / 2).toBeLessThan(mat.x + mat.width);
  expect(box.y + box.height / 2).toBeGreaterThan(mat.y);
  expect(box.y + box.height / 2).toBeLessThan(mat.y + mat.height);
  // and clears away by itself
  await expect(throwEl).toHaveCount(0, { timeout: 12000 });
});
