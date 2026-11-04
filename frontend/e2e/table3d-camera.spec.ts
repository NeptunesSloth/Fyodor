import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, menuPath } from "./helpers";

/**
 * The 3D table's camera (Tabletop Simulator style: right-drag orbits, middle-drag pans, the wheel zooms toward the
 * cursor, the arrow keys pan, Home and 1 come back to the seat) and its picture (nothing flickers, however far out).
 */
async function duel(page: Page, reducedMotion = false, graphics = "medium") {
  await page.addInitScript(([reduced, gfx]) => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, reducedMotion: reduced, graphics: gfx } }] }));
  }, [reducedMotion, graphics] as const);
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
  // the camera eases out and stops; then nothing on screen changes from frame to frame
  await expect.poll(async () => (await page.evaluate(() => window.__fyodor3d!.frameDiff!(100))).changed, { timeout: 90_000, intervals: [200] }).toBe(0);
  expect((await page.evaluate(() => window.__fyodor3d!.framing!())).adjust.zoom).toBeCloseTo(2.5, 3); // (as far as it goes)
  const diffs: number[] = [];
  for (let i = 0; i < 3; i++) {
    diffs.push((await page.evaluate(() => window.__fyodor3d!.frameDiff!(200))).changed);
  }
  console.log("frame diffs at the farthest zoom", JSON.stringify(diffs));
  expect(diffs).toEqual([0, 0, 0]);
});

type Pt = { x: number; y: number };
/** Where a card is on screen once the camera has stopped (read after frames have been drawn, twice, agreeing). */
async function steady(page: Page, id: string): Promise<Pt> {
  const read = () => page.evaluate(async (c) => {
    const f = window.__fyodor3d!;
    await f.nextFrame!();
    await f.nextFrame!();
    return f.cardAt(c);
  }, id);
  let last = await read();
  for (let i = 0; i < 20; i++) {
    const p = await read();
    if (p && last && Math.hypot(p.x - last.x, p.y - last.y) < 0.5) return p;
    last = p;
  }
  throw new Error("the camera never came to rest");
}

test("3D camera, as in Tabletop Simulator: right-drag orbits, a still right-click opens the menu, middle-drag pans, the wheel zooms to the pointer, arrows pan, Home and 1 come back", async ({ page }) => {
  test.slow();
  await page.setViewportSize({ width: 1280, height: 720 });
  const { view } = await duel(page, true, "low"); // reduced motion: the camera goes straight where it's sent
  const card = (await view()).zones["p1:battlefield"]![1]!;
  // framed clear of the turn dial once it has been measured
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.framing!().keepOut.length), { timeout: 30_000 }).toBe(3);
  const home = await steady(page, card);
  const life = async () => ((await view()) as unknown as { players: { id: string; life: number }[] }).players.find((p) => p.id === "p2")!.life;

  // right-drag: the view turns around the table (the card moves on screen) and no menu opens
  const box = (await page.getByTestId("table-3d").boundingBox())!;
  const mid = { x: box.x + box.width / 2, y: box.y + box.height * 0.45 };
  await page.mouse.move(mid.x, mid.y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(mid.x + 140, mid.y + 30, { steps: 8 });
  await page.mouse.up({ button: "right" });
  const turned = await steady(page, card);
  expect(Math.hypot(turned.x - home.x, turned.y - home.y)).toBeGreaterThan(20);
  await expect(page.locator(".ctx-menu")).toHaveCount(0);

  // Home: back to the seat as it was framed
  await page.keyboard.press("Home");
  const back = await steady(page, card);
  expect(Math.hypot(back.x - home.x, back.y - home.y)).toBeLessThan(2);

  // a right-click that doesn't move: the card's menu, as before
  await page.mouse.click(home.x, home.y, { button: "right" });
  await expect(page.locator(".ctx-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".ctx-menu")).toHaveCount(0);

  // middle-drag: the table slides under the pointer (the card follows it)
  await page.mouse.move(home.x, home.y);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(home.x + 90, home.y - 50, { steps: 8 });
  await page.mouse.up({ button: "middle" });
  const panned = await steady(page, card);
  expect(Math.abs(panned.x - (home.x + 90))).toBeLessThan(14);
  expect(Math.abs(panned.y - (home.y - 50))).toBeLessThan(14);

  // the wheel zooms toward the pointer: the card under it stays under it, and comes closer (an arrow pans first, so
  // the zoom isn't about the middle of the screen)
  await page.keyboard.press("1");
  await steady(page, card);
  await page.keyboard.press("ArrowLeft");
  const before = await steady(page, card);
  await page.mouse.move(before.x, before.y);
  for (let i = 0; i < 3; i++) await page.mouse.wheel(0, -120);
  const zoomed = await steady(page, card);
  expect(Math.hypot(zoomed.x - before.x, zoomed.y - before.y)).toBeLessThan(6);
  const a = (await page.evaluate((c) => window.__fyodor3d!.cardAt(c), card))!;
  expect(a).not.toBeNull();

  // arrows pan (Shift: three times as far)
  await page.keyboard.press("1");
  const one = await steady(page, card);
  await page.keyboard.press("ArrowRight");
  const step1 = await steady(page, card);
  await page.keyboard.press("1");
  await steady(page, card);
  await page.keyboard.press("Shift+ArrowRight");
  const step3 = await steady(page, card);
  expect(one.x - step1.x).toBeGreaterThan(8); // the view moved right: the card moved left
  expect((one.x - step3.x) / (one.x - step1.x)).toBeGreaterThan(2.5);

  // the wheel over a life heart still changes life (and doesn't zoom)
  await page.keyboard.press("1");
  await steady(page, card);
  const heart = (await page.evaluate(() => window.__fyodor3d!.heartAt("p2")))!;
  const lifeBefore = await life();
  await page.mouse.move(heart.x, heart.y);
  await page.mouse.wheel(0, -100);
  await expect.poll(life, { timeout: 15_000 }).toBe(lifeBefore + 1);
  expect((await page.evaluate(() => window.__fyodor3d!.framing!())).adjust).toEqual({ yaw: 0, pitch: 0, zoom: 1, panX: 0, panZ: 0 });

  // 0 looks over the whole table; 1 comes back
  const seat = await steady(page, card);
  await page.keyboard.press("0");
  const over = await steady(page, card);
  expect(Math.hypot(over.x - seat.x, over.y - seat.y)).toBeGreaterThan(10);
  await page.keyboard.press("1");
  const again = await steady(page, card);
  expect(Math.hypot(again.x - seat.x, again.y - seat.y)).toBeLessThan(2);

  // and a right-click on a card picks from its menu as before (Tap)
  await page.mouse.click(again.x, again.y, { button: "right" });
  await menuPath(page, "Tap");
  await expect.poll(async () => ((await view()) as unknown as { cards: Record<string, { tapped?: boolean }> }).cards[card]!.tapped, { timeout: 15_000 }).toBe(true);
});
