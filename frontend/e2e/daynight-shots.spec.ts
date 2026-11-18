import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for day and night (CR 726; game/DayNightLayer.tsx, table3d/dayNight.ts): day beginning, day → night and
 * night → day, each mid-change and settled, on the 2D and the 3D table. Skipped unless SHOT_DIR is set. The animation speed is
 * slowed (0.5× in 2D; 0.03× in 3D, where software WebGL draws about a frame a second and a 1920×1080 screenshot takes
 * ~13 s) so the frames land mid-change.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

async function setup(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free", animationSpeed: r === "3d" ? 0.03 : 0.5 } }] }));
  }, renderer);
  const decks: { id: string }[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) decks.push((await (await page.request.post("/api/decks", { data: { text } })).json()) as { id: string });
  const res = await page.request.post("/api/games", {
    data: { name: "Day and night", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (v: string) => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as { zones: Record<string, string[]> };
  for (const pid of ["p1", "p2"]) {
    await act(pid, { type: "draw", player: pid, count: 8 });
    const ids = (await view(pid)).zones[`${pid}:hand`]!.slice(0, 5);
    for (const [i, cid] of ids.entries()) await act(pid, { type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 60 + i * 120, y: i < 3 ? 160 : 380 });
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${gameId}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(renderer === "3d" ? 7000 : 2500);
  return { act };
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/daynight-${name}.png` });

/**
 * A frame mid-change: the page's CSS motion (the moment, the 2D felt's fade) is held at 45% of the way while the frame is taken,
 * then let go; the 3D light runs on (slowed to 0.03×, a ~33 s turn, so the seconds a software-WebGL screenshot takes land in it).
 */
async function change(page: Page, renderer: "2d" | "3d", name: string) {
  const moment = page.getByTestId("daynight-moment");
  await expect(moment).toBeVisible({ timeout: 10_000 });
  if (renderer === "3d") await page.waitForTimeout(4000);
  await page.evaluate(() => {
    for (const a of document.getAnimations()) {
      const end = Number(a.effect?.getComputedTiming().endTime ?? 0);
      a.currentTime = end * 0.45;
      a.pause();
    }
  });
  await shot(page, `${name}-mid`);
  await moment.screenshot({ path: `${OUT}/daynight-${name}-moment.png`, timeout: 20_000 }).catch(() => {});
  await page.evaluate(() => { for (const a of document.getAnimations()) if (a.playState === "paused") a.play(); });
}

for (const renderer of ["2d", "3d"] as const) {
  test(`day and night (${renderer})`, async ({ page }) => {
    test.setTimeout(renderer === "3d" ? 600_000 : 240_000);
    const { act } = await setup(page, renderer);
    await shot(page, `${renderer}-0-neither`);
    // day begins
    await act("p1", { type: "set_day_night", value: "day" });
    await change(page, renderer, `${renderer}-1-day-begins`);
    await page.waitForTimeout(renderer === "3d" ? 40_000 : 3500);
    await shot(page, `${renderer}-2-day`);
    await page.getByTestId("day-night").screenshot({ path: `${OUT}/daynight-${renderer}-indicator-day.png` });
    // day → night
    await act("p1", { type: "set_day_night", value: "night" });
    await change(page, renderer, `${renderer}-3-to-night`);
    await page.waitForTimeout(renderer === "3d" ? 40_000 : 3500);
    await shot(page, `${renderer}-4-night`);
    await page.getByTestId("day-night").screenshot({ path: `${OUT}/daynight-${renderer}-indicator-night.png` });
    // night → day
    await act("p1", { type: "set_day_night", value: "day" });
    await change(page, renderer, `${renderer}-5-to-day`);
    await page.waitForTimeout(renderer === "3d" ? 40_000 : 3500);
    await shot(page, `${renderer}-6-day-again`);
    // a table that loads at night is simply night (no moment)
    await act("p1", { type: "set_day_night", value: "night" });
    await page.reload();
    await page.waitForTimeout(renderer === "3d" ? 7000 : 2500);
    await expect(page.getByTestId("daynight-moment")).toHaveCount(0);
    await shot(page, `${renderer}-7-loaded-at-night`);
  });
}
