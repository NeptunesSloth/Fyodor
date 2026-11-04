import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for the Bag of Extras (game/ExtrasBag.tsx), opened from its seat chit on the 3D table and its button on
 * the 2D table. Skipped unless SHOT_DIR is set; SHOT_PREFIX names the set.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "extras";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

async function game(page: Page, renderer: "3d" | "2d"): Promise<string> {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
  const ids: string[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) {
    const r = await page.request.post("/api/decks", { data: { text, name: text.split("\n")[1]!.replace(/^1x /, "").replace(/ \(.*/, "") } });
    expect(r.ok()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Extras", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "off",
      players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }] },
  });
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as { game: { id: string } }).game.id;
}

test("the Bag of Extras, 3D table, 1920x1080", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const id = await game(page, "3d");
  await page.goto(`/#/game/${id}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await page.waitForTimeout(3500);
  const at = await page.evaluate(() => window.__fyodor3d!.buttonAt("extras"));
  expect(at).not.toBeNull();
  await page.mouse.click(at!.x, at!.y);
  await expect(page.getByTestId("extras-panel")).toBeVisible();
  await page.mouse.move(2, 400);
  await page.waitForTimeout(1500); // token art and the panel's entrance settle
  await page.screenshot({ path: `${OUT}/${PREFIX}-3d-1920x1080.png` });
  await page.getByTestId("extras-panel").screenshot({ path: `${OUT}/${PREFIX}-3d-panel.png` });
});

test("the Bag of Extras, 2D table, 1440x900", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await game(page, "2d");
  await page.goto(`/#/game/${id}`);
  const intro = page.getByTestId("game-intro");
  await page.waitForTimeout(1500);
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Bag of Extras/ }).first().click();
  await expect(page.getByTestId("extras-panel")).toBeVisible();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${PREFIX}-2d-1440x900.png` });
});
