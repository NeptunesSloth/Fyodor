import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Searching your library opens the docked zone browser where it can be seen and used, every time, on both tables. (A broad table rule once
 * put the browser into the page flow, off screen on the 3D table: the search was logged but its window never showed.)
 */
async function game(page: Page, renderer: "2d" | "3d"): Promise<string> {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  }, renderer);
  const ids: string[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) {
    const r = await page.request.post("/api/decks", { data: { text, name: `d${ids.length}` } });
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Search", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "off",
      players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }] },
  });
  return ((await res.json()) as { game: { id: string } }).game.id;
}

for (const renderer of ["3d", "2d"] as const) {
  test(`search the library three times in a row, ${renderer} table`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 1600, height: 900 });
    const id = await game(page, renderer);
    await page.goto(`/#/game/${id}`);
    if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
    await page.waitForTimeout(1500);
    await page.keyboard.press("Escape");
    for (let i = 0; i < 3; i++) {
      await page.request.post(`/api/games/${id}/actions`, { data: { action: { type: "search_start", zone: { zone: "library", player: "p1" } } } });
      const browser = page.locator(".zone-browser");
      await expect(browser).toBeVisible();
      await expect(browser.getByText("Searching your library")).toBeVisible();
      // on screen and on top: what's under the middle of its header is the browser itself
      await expect.poll(() => page.evaluate(() => {
        const r = document.querySelector(".zone-browser")!.getBoundingClientRect();
        const inView = r.top >= 0 && r.bottom <= window.innerHeight && r.left >= 0;
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 16);
        return inView && !!hit?.closest(".zone-browser");
      })).toBe(true);
      await browser.getByRole("button", { name: "Done & shuffle" }).click();
      await expect(browser).toHaveCount(0);
    }
  });
}
