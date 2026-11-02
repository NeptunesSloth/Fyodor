import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Frames of the end-of-game table scene for review (game/motion/endScene.ts; the 3D table's table3d/endScene3d.ts and
 * the 2D table's EndScene2D.tsx): Victory, Defeat and Draw on both tables, and the eliminated player's own scene, held
 * mid-scene. Skipped unless SHOT_DIR is set. Headless software WebGL draws about a frame a second, so each scene is
 * frozen at a set scene time (window.__fyodorEndScene.freeze) before its frame is taken.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture end-scene screenshots");

type Renderer = "3d" | "2d";
type View = { zones: Record<string, string[] | { count: number }> };

async function setup(page: Page, renderer: Renderer, players = ["Alice", "Bob"], game: Record<string, unknown> = {}) {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.nightScenes", "1");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
  const decks: { id: string }[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) decks.push((await (await page.request.post("/api/decks", { data: { text } })).json()) as { id: string });
  const res = await page.request.post("/api/games", {
    data: {
      name: "End", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: players.map((name, i) => ({ name, deck_id: decks[i % 2]!.id })), ...game,
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const night = async (path: string, data: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/night/${path}`, { data });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  // a board in progress: a few cards and tokens on every battlefield (by hand: not at a rules-engine table)
  for (const pid of game.automation ? [] : players.map((_, i) => `p${i + 1}`)) {
    await act(pid, { type: "draw", player: pid, count: 6 });
    const v = (await (await page.request.get(`/api/games/${gameId}/view?viewer=${pid}`)).json()) as View;
    const ids = (v.zones[`${pid}:hand`] as string[]).slice(0, 3);
    for (const [i, cid] of ids.entries()) await act(pid, { type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 60 + i * 110, y: 380 });
    await act(pid, { type: "create_token", player: pid, token: { name: pid === "p1" ? "Soldier" : "Goblin", power: "2", toughness: "2", colors: [pid === "p1" ? "W" : "R"], type_line: "Token Creature" }, count: 2, stacked: false, x: 420, y: 120 });
  }
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  if (renderer === "3d") {
    await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
    await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? -1), { timeout: 60_000 }).toBeGreaterThanOrEqual(game.automation ? 0 : 8);
  } else {
    await expect(page.getByTestId("seat-p2")).toBeVisible();
  }
  // past the game's intro
  await expect(page.getByTestId("game-intro")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("game-intro")).toHaveCount(0);
  await page.waitForTimeout(renderer === "3d" ? 2500 : 800);
  return { gameId, act, night };
}

/** Wait until the table has drawn a few frames (a frame can take a second in software WebGL). */
async function frames(page: Page, n = 3) {
  for (let i = 0; i < n; i++) await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => done())));
}

/** The spotlight's own CSS fades run on real frames (a headless page draws one only when asked): draw until its word is in. */
async function settledText(page: Page) {
  for (let i = 0; i < 40; i++) {
    await frames(page, 1);
    const op = await page.evaluate(() => {
      const w = document.querySelector(".night-word");
      return w ? Number(getComputedStyle(w).opacity) : 1;
    });
    if (op >= 0.99) break;
    await page.waitForTimeout(100);
  }
}

async function freeze(page: Page, ms: number | null) {
  await page.evaluate((t) => window.__fyodorEndScene?.freeze(t), ms);
}

/** End the game with this result (proposed by Alice, agreed by Bob), held at ``times`` scene ms, one frame each. */
async function endAndShoot(page: Page, renderer: Renderer, end: () => Promise<void>, word: string, name: string, times: number[]) {
  await freeze(page, times[0]!);
  await end();
  await expect(page.getByTestId("result-spotlight")).toContainText(word, { timeout: 15_000 });
  await expect.poll(() => page.evaluate(() => window.__fyodorEndScene?.state()?.kind ?? null)).not.toBeNull();
  await settledText(page);
  for (const t of times) {
    await freeze(page, t);
    await frames(page, renderer === "3d" ? 4 : 2);
    await page.screenshot({ path: `${OUT}/${renderer}-${name}-${t}.png` });
  }
  // let it go: the spotlight ends, the table settles back and the result panel takes over
  await freeze(page, null);
  await expect(page.getByTestId("night-result")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => page.evaluate(() => window.__fyodorEndScene?.state() ?? null), { timeout: 10_000 }).toBeNull();
  await frames(page, renderer === "3d" ? 3 : 1);
  await page.screenshot({ path: `${OUT}/${renderer}-${name}-after.png` });
}

for (const renderer of ["3d", "2d"] as const) {
  test(`${renderer} table: victory, defeat and draw`, async ({ page }) => {
    test.setTimeout(600_000);
    // Victory: Alice (this screen) wins
    let g = await setup(page, renderer);
    await page.screenshot({ path: `${OUT}/${renderer}-board.png` });
    await endAndShoot(page, renderer, async () => {
      await g.night("propose", { result_type: "single", winners: ["p1"], as_player: "p1" });
      await g.night("answer", { agree: true, as_player: "p2" });
    }, "Victory", "victory", [650, 1400]);

    // Defeat: Bob wins
    g = await setup(page, renderer);
    await endAndShoot(page, renderer, async () => {
      await g.night("propose", { result_type: "single", winners: ["p2"], as_player: "p1" });
      await g.night("answer", { agree: true, as_player: "p2" });
    }, "Defeat", "defeat", [650, 1300]);

    // Draw
    g = await setup(page, renderer);
    await endAndShoot(page, renderer, async () => {
      await g.night("propose", { result_type: "draw", winners: [], as_player: "p1" });
      await g.night("answer", { agree: true, as_player: "p2" });
    }, "Draw", "draw", [600, 1200]);
  });
}

test("3d table: eliminated (only the player who is out)", async ({ page }) => {
  test.setTimeout(300_000);
  const g = await setup(page, "3d", ["Alice", "Bob", "Cara"], { automation: "full" });
  await freeze(page, 450);
  await g.act("p1", { type: "concede" });
  await expect(page.getByTestId("eliminated-scene")).toContainText("Eliminated", { timeout: 15_000 });
  await settledText(page);
  await frames(page, 4);
  await page.screenshot({ path: `${OUT}/3d-eliminated-450.png` });
  await freeze(page, null);
  await expect(page.getByTestId("eliminated-hub")).toBeVisible({ timeout: 15_000 });
});
