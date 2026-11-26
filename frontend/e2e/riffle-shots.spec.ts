import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * The Blender-authored library shuffle (packaging/blender/riffle.py → table3d/assets/riffle.glb) on the 3D table: frames
 * of a riffle on the opponent's library, up close. Skipped unless SHOT_DIR is set.
 */
const OUT = process.env.SHOT_DIR ?? "";

test("3D shuffle: the Blender riffle plays on a library", async ({ page }) => {
  test.skip(!OUT, "set SHOT_DIR to capture the frames");
  test.setTimeout(480_000);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, animationSpeed: 0.5 } }] }));
  });
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", {
    data: { name: "Riffle", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.evaluate(() => window.__fyodor3d?.camera({ focus: "p2" }));
  await page.waitForTimeout(4000); // (the clip loads with the table)
  // zoom toward Bob's library (the wheel zooms to the pointer) and frame it
  await page.mouse.move(885, 266);
  for (let i = 0; i < 6; i++) {
    await page.mouse.wheel(0, -240);
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(2500);
  const library = { x: 585, y: 66, width: 600, height: 400 };
  await page.screenshot({ path: `${OUT}/riffle-0.png`, clip: library });
  const frames = () => page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))));
  // each frame: freeze the table's motion clock at a moment of the clip, shuffle, and take it (the clip runs ~1.7 s at half speed)
  for (const [i, ms] of [[1, 250], [2, 500], [3, 800], [4, 1150], [5, 1450]] as const) {
    await page.evaluate((t) => window.__fyodor3d?.motionFreeze?.(t), ms);
    await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "shuffle", player: "p2", zone: "library" }, as: "p2" } });
    await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().riffles ?? 0), { timeout: 60_000 }).toBe(1);
    expect(await page.evaluate(() => window.__fyodor3d?.motion?.().clips)).toBe(1); // the Blender clip, not the drawn riffle
    await frames();
    await page.screenshot({ path: `${OUT}/riffle-${i}.png`, clip: library });
    await page.evaluate(() => window.__fyodor3d?.motionFreeze?.(null));
    await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().riffles ?? 1), { timeout: 60_000 }).toBe(0);
  }
  await page.screenshot({ path: `${OUT}/riffle-view.png` });
});
