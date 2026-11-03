import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

/** Experience and energy show on the seat plaque once a player has any (Atraxa's experience deck), and click like the other trackers. */
test("counters show on the plaque while a player has any; the plaque's + adds one", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Counters", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
    players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }] } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const resources = async () => ((await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { players: { id: string; resources: Record<string, number> }[] })
    .players.find((p) => p.id === "p1")!.resources;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("heart-p1")).toBeVisible();
  // a zero says nothing: no poison or commander damage on the plaque until there is some; its + adds one
  await expect(page.getByTestId("poison-p1")).toHaveCount(0);
  await page.getByTestId("seat-add-p1").click();
  await page.locator(".ctx-menu .ctx-item", { hasText: "Poison" }).click();
  await expect(page.getByTestId("poison-p1")).toContainText("1");
  await expect.poll(async () => (await resources()).poison).toBe(1);
  await expect(page.getByTestId("experience-p1")).toHaveCount(0); // none yet: not on the plaque
  const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "resource", player: "p1", key: "experience", delta: 3 }, as: "p1" } });
  expect(r.ok(), await r.text()).toBeTruthy();
  await expect(page.getByTestId("experience-p1")).toContainText("3");
  await expect(page.getByTestId("energy-p1")).toHaveCount(0);
  await page.getByTestId("experience-p1").click();
  await expect.poll(async () => (await resources()).experience).toBe(4);
});
