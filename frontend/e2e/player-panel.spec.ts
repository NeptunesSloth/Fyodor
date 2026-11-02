import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

/** The 2D table: a seat plaque's player panel opens in full view (not clipped by the rail or strip it sits in), for my
 * own seat and an opponent's, with the commander-damage matrix inside it. */
test("2D: player panels open in full view, with the commander damage matrix", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.renderer", "2d");
  });
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Panels", mode: "local", shuffle: false, mulligan_rule: "none",
    players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i % 2]!.id })) } });
  const gid = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gid}`);
  for (const seat of ["p1", "p2"]) {
    await page.getByTestId(`seat-${seat}`).click();
    const toggle = page.getByTestId("cmd-matrix-toggle");
    await expect(toggle).toBeInViewport();
    await toggle.click(); // a clipped or covered panel can't be clicked
    await expect(page.getByTestId("cmd-matrix")).toBeInViewport();
    await page.getByTestId(`seat-${seat}`).click(); // close it again
    await expect(toggle).toHaveCount(0);
  }
});
