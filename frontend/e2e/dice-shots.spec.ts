import { expect, test, type Page } from "@playwright/test";
import { saveDecks } from "./helpers";

/**
 * Screenshots of the thrown dice for review (3D table, the 2D table's overlay and its drawn fallback), mid-throw and
 * at rest. Skipped unless SHOT_DIR is set: `SHOT_DIR=/some/dir npx playwright test e2e/dice-shots.spec.ts`.
 * Each throw is frozen at a set time (window.__fyodorDice.freeze): headless software WebGL draws about a frame a
 * second, so wall-clock timing can't pin a frame.
 */
const OUT = process.env.SHOT_DIR ?? "";
const ONLY = process.env.SHOT_ONLY ?? "";
test.skip(!OUT, "set SHOT_DIR to capture dice screenshots");

async function table(page: Page, renderer: "3d" | "2d", players = ["Alice", "Bob"], extra: Record<string, unknown> = {}, game: Record<string, unknown> = {}) {
  await page.addInitScript(([r, prefs]) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, ...prefs } }] }));
  }, [renderer, extra] as const);
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: { name: "Dice", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", players: players.map((name, i) => ({ name, deck_id: decks[i % decks.length]!.id })), ...game },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  if (renderer === "3d") await expect.poll(() => page.evaluate(() => !!window.__fyodor3d), { timeout: 60_000 }).toBe(true);
  else await expect(page.getByTestId("seat-p2")).toBeVisible();
  await page.waitForTimeout(1500);
  const roll = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok()).toBeTruthy();
  };
  return { gameId, roll };
}

/** Wait until the table has drawn two frames (a frame can take seconds in software WebGL). */
async function frames(page: Page) {
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done())))));
}

async function freezeAndShoot(page: Page, name: string, times: number[]) {
  for (const t of times) {
    await page.evaluate((ms) => window.__fyodorDice!.freeze(ms), t);
    await frames(page);
    await page.screenshot({ path: `${OUT}/${name}-${t}.png` });
  }
}

test("3D table: dice thrown, mid-air and at rest", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "3d", "SHOT_ONLY");
  test.setTimeout(300_000);
  const { roll } = await table(page, "3d", ["Alice", "Bob"], { diceLook: process.env.SHOT_LOOK ?? "resin" });
  await page.evaluate(() => window.__fyodorDice!.freeze(0));
  await roll("p1", { type: "roll", sides: 6, count: 2 });
  await roll("p2", { type: "roll", sides: 20, count: 1 });
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.diceState().length)).toBe(2);
  await freezeAndShoot(page, `3d-${process.env.SHOT_LOOK ?? "resin"}`, [350, 800, 4000]);
});

test("3D table: every kind of die, an ignored roll and a natural 20", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "3d-all", "SHOT_ONLY");
  test.setTimeout(300_000);
  await table(page, "3d", ["Alice", "Bob", "Casey", "Dana", "Eve", "Finn"], { diceLook: process.env.SHOT_LOOK ?? "resin" });
  await page.evaluate(() => window.__fyodorDice!.freeze(0));
  await page.evaluate(() => {
    const t = window.__fyodor3d!;
    t.throwDice({ key: "s1", actor: "p1", sides: 20, results: [20, 7], coin: false, ignored: [1] }); // Barbarian Class: one more, ignore the lowest
    t.throwDice({ key: "s2", actor: "p2", sides: 100, results: [37], coin: false });
    t.throwDice({ key: "s3", actor: "p3", sides: 4, results: [3, 1, 4], coin: false });
    t.throwDice({ key: "s4", actor: "p4", sides: 12, results: [11, 2], coin: false });
    t.throwDice({ key: "s5", actor: "p5", sides: 2, results: [1, 0], coin: true });
    t.throwDice({ key: "s6", actor: "p6", sides: 8, results: [6, 3], coin: false });
  });
  await freezeAndShoot(page, `3d-all-${process.env.SHOT_LOOK ?? "resin"}`, [4000]);
  await page.evaluate(() => window.__fyodor3d!.camera("overview"));
  await freezeAndShoot(page, `3d-all-overview-${process.env.SHOT_LOOK ?? "resin"}`, [4000]);
});

test("2D table: the same dice in an overlay, mid-air and at rest", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "2d", "SHOT_ONLY");
  test.setTimeout(300_000);
  const { roll } = await table(page, "2d", ["Alice", "Bob"]);
  await page.evaluate(() => window.__fyodorDice!.freeze(0));
  await roll("p1", { type: "roll", sides: 6, count: 2 });
  await expect.poll(() => page.evaluate(() => window.__fyodorDice2d?.state().length ?? 0), { timeout: 30_000 }).toBe(1);
  await roll("p2", { type: "roll", sides: 20, count: 1 });
  await expect.poll(() => page.evaluate(() => window.__fyodorDice2d?.state().length ?? 0), { timeout: 30_000 }).toBe(2);
  await freezeAndShoot(page, "2d-overlay", [350, 800, 4000]);
});

test("2D table without WebGL: drawn dice", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "2d-drawn", "SHOT_ONLY");
  test.setTimeout(200_000);
  await page.addInitScript(() => {
    const get = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, id: string, ...rest: unknown[]) {
      return /webgl/.test(id) ? null : (get as (...a: unknown[]) => RenderingContext | null).call(this, id, ...rest);
    } as typeof get;
  });
  const { roll } = await table(page, "2d", ["Alice", "Bob"]);
  await roll("p1", { type: "roll", sides: 20, count: 2 });
  await roll("p2", { type: "roll", sides: 6, count: 3 });
  await expect(page.getByTestId("dice-die")).toHaveCount(5);
  // mid-tumble, then at rest
  await page.evaluate(() => document.getAnimations().forEach((a) => { a.pause(); a.currentTime = 380; }));
  await page.screenshot({ path: `${OUT}/2d-drawn-380.png` });
  await page.evaluate(() => document.getAnimations().forEach((a) => a.finish()));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/2d-drawn-rest.png` });
});

test("the roll panel", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "panel", "SHOT_ONLY");
  test.setTimeout(200_000);
  const { roll } = await table(page, "2d", ["Alice", "Bob"]);
  await roll("p2", { type: "roll", sides: 6, count: 2 });
  await roll("p1", { type: "coin", count: 1 });
  await page.keyboard.press("Shift+R");
  await expect(page.getByTestId("dice-panel")).toBeVisible();
  await page.getByTestId("dice-kind-d6").click();
  await page.getByRole("button", { name: "One more" }).click();
  await page.getByTestId("dice-panel").screenshot({ path: `${OUT}/panel.png` });
  await page.screenshot({ path: `${OUT}/panel-table.png` });
});

test("the elimination hub's toy tray throws the same dice", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "toys", "SHOT_ONLY");
  test.setTimeout(300_000);
  const { gameId } = await table(page, "3d", ["Alice", "Bob", "Cara"], {}, { automation: "full" });
  const conceded = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "concede" }, as: "p1" } });
  expect(conceded.ok(), await conceded.text()).toBeTruthy();
  await expect(page.getByTestId("eliminated-hub")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("eliminated-hub").getByTestId("open-toys").click();
  for (const k of ["d6", "d6", "d20", "d8", "coin"]) await page.getByTestId(`toys-add-${k}`).click();
  await page.evaluate(() => window.__fyodorDice!.freeze(5000));
  await page.getByTestId("toys-roll").click();
  await expect(page.getByTestId("toys-total")).toContainText(/\d/);
  await page.waitForTimeout(4000);
  await frames(page);
  await page.getByTestId("toys").screenshot({ path: `${OUT}/toys.png` });
});

test("dice cost: draw calls, triangles and frame time before and after a big roll", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "perf", "SHOT_ONLY");
  test.setTimeout(300_000);
  await table(page, "3d", ["Alice", "Bob", "Casey", "Dana"]);
  const sample = async () => {
    await page.waitForTimeout(6000); // stats refresh once a second; frames take ~1 s in software WebGL
    return page.evaluate(() => window.__fyodor3d!.stats());
  };
  const before = await sample();
  await page.evaluate(() => window.__fyodorDice!.freeze(6000));
  const first = await page.evaluate(() => {
    const t = window.__fyodor3d!;
    const t0 = performance.now();
    t.throwDice({ key: "perf1", actor: "p1", sides: 20, results: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], coin: false });
    const a = performance.now() - t0;
    const t1 = performance.now();
    t.throwDice({ key: "perf2", actor: "p2", sides: 6, results: [3, 4], coin: false });
    const b = performance.now() - t1;
    const t2 = performance.now();
    t.throwDice({ key: "perf3", actor: "p3", sides: 20, results: [17], coin: false });
    return { twelveD20: a, twoD6: b, oneD20: performance.now() - t2 };
  });
  const after = await sample();
  const out = { before, after, throwMs: first, diceState: await page.evaluate(() => window.__fyodor3d!.diceState().map((t) => ({ key: t.key, ms: t.ms, dice: t.dice.length }))) };
  console.log(JSON.stringify(out));
  const fs = await import("node:fs");
  fs.writeFileSync(`${OUT}/perf.json`, JSON.stringify(out, null, 2));
});
