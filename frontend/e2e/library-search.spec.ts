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

/** The header buttons of the open zone browser that something else covers (by their text). */
function headButtonsOnTop(page: Page): Promise<string[]> {
  return page.evaluate(() => [...document.querySelectorAll<HTMLElement>(".zone-browser .zb-head button")]
    .filter((b) => {
      const r = b.getBoundingClientRect();
      return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) !== b && !b.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
    })
    .map((b) => b.textContent ?? ""));
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
      // and every button in its header (Done, Close: top right) is clear of the turn dial in the corner
      expect(await headButtonsOnTop(page)).toEqual([]);
      await browser.getByRole("button", { name: "Done & shuffle" }).click();
      await expect(browser).toHaveCount(0);
    }
  });
}

for (const width of [1920, 1440, 700]) {
  test(`a short zone browser's Close button is never under the turn dial, at ${width}px`, async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width, height: 900 });
    const id = await game(page, "2d");
    await page.goto(`/#/game/${id}`);
    await page.waitForTimeout(1500);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("turn-dial")).toBeVisible();
    // an empty zone: the shortest browser, its header low beside the dial (Bob's graveyard: at 700px the dial covers Alice's piles)
    await page.locator('main.table [data-drop="p2:graveyard"]').first().click();
    await expect(page.locator(".zone-browser")).toContainText("Nothing to show.");
    expect(await headButtonsOnTop(page)).toEqual([]);
  });
}

test("a library search shows its cards even while another zone's browser is open", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  const id = await game(page, "2d");
  await page.goto(`/#/game/${id}`);
  await page.waitForTimeout(1500);
  await page.keyboard.press("Escape");
  await page.locator('main.table [data-drop="p1:graveyard"]').first().click();
  const browser = page.locator(".zone-browser");
  await expect(browser).toContainText("Nothing to show.");
  await page.request.post(`/api/games/${id}/actions`, { data: { action: { type: "search_start", zone: { zone: "library", player: "p1" } } } });
  await expect(browser.getByText("Searching your library")).toBeVisible();
  await expect(browser.locator(".zb-card").first()).toBeVisible();
  await browser.getByRole("button", { name: "Done & shuffle" }).click();
  await expect(browser).toHaveCount(0);
});
