import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * The 3D table's camera (Tabletop Simulator style: right-drag orbits, middle-drag pans, the wheel zooms toward the
 * cursor, the arrow keys pan, Home and 1 come back to the seat) and its picture (nothing flickers, however far out).
 */
async function duel(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  const ids: string[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Duel", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none", players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: ids[i]! })) },
  });
  expect(res.ok()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => expect((await page.request.post(`/api/games/${gameId}/actions`, { data: { action } })).ok()).toBeTruthy();
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as { zones: Record<string, string[]> };
  for (const pid of ["p1", "p2"]) await act({ type: "draw", player: pid, count: 10 });
  for (const pid of ["p1", "p2"]) {
    const hand = (await view(pid)).zones[`${pid}:hand`]!;
    for (const [i, cid] of hand.slice(0, 3).entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 60 + i * 120, y: 60 });
  }
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 }); // software WebGL on a CI runner is slow to start
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(6);
  return { gameId, act, view };
}

test("3D table: nothing flickers at the farthest zoom (two frames, no input, the same pixel for pixel)", async ({ page }) => {
  test.slow();
  await page.setViewportSize({ width: 1280, height: 720 });
  await duel(page);
  const box = (await page.getByTestId("table-3d").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.4);
  for (let i = 0; i < 40; i++) await page.mouse.wheel(0, 500);
  await page.evaluate(() => window.__fyodor3d!.still!(true));
  await page.waitForTimeout(4000); // the camera eases out
  const diffs: number[] = [];
  for (let i = 0; i < 3; i++) diffs.push((await page.evaluate(() => window.__fyodor3d!.frameDiff!(200))).changed);
  console.log("frame diffs at the farthest zoom", JSON.stringify(diffs));
  expect(diffs).toEqual([0, 0, 0]);
});
