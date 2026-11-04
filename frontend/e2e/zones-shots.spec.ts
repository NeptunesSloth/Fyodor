import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for the 3D table's zone wells and commander tax: the seat view with the tax paid a few times (the coin
 * column and its tag), close-ups of my command corner and my piles at 2x, and the far row's. Skipped unless SHOT_DIR is
 * set; SHOT_PREFIX names the set. SHOT_SIZE (e.g. 1280x720) picks the window; SHOT_SEATS 2 or 4.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "zones";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

type View = { seat_order: string[]; zones: Record<string, string[]>; players: { id: string; commanders: { key: string; tax: number }[] }[] };

async function setup(page: Page, players: string[]) {
  await page.addInitScript(() => {
    if (!localStorage.getItem("fyodor.renderer")) localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  const ids: string[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) {
    const r = await page.request.post("/api/decks", { data: { text, name: text.split("\n")[1]!.replace(/^1x /, "").replace(/ \(.*/, "") } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Zones", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", players: players.map((name, i) => ({ name, deck_id: ids[i % 2]! })) },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  return { gameId, act, view };
}

test("zone wells and the commander tax, seat view and close-ups", async ({ browser }) => {
  test.setTimeout(300_000);
  const [w, h] = (process.env.SHOT_SIZE ?? "1920x1080").split("x").map(Number) as [number, number];
  const n = Number(process.env.SHOT_SEATS ?? 2);
  const context = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: Number(process.env.SHOT_DPR ?? 1) });
  const page = await context.newPage();
  const { gameId, act, view } = await setup(page, ["Alice", "Bob", "Casey", "Jordan"].slice(0, n));
  const v = await view();
  // a few cards in each graveyard and exile; Alice's commander cast from the command zone twice (tax +4), Bob's once
  for (const pid of v.seat_order) {
    await act({ type: "draw", player: pid, count: 12 });
    const hand = (await view(pid)).zones[`${pid}:hand`]!;
    await act({ type: "move", card_ids: hand.slice(0, 3), to: { zone: "graveyard", player: pid } });
    await act({ type: "move", card_ids: hand.slice(3, 4), to: { zone: "exile", player: pid } });
    await act({ type: "move", card_ids: hand.slice(4, 6), to: { zone: "battlefield", player: pid }, x: 300, y: 200 });
  }
  const key = (pid: string) => v.players.find((p) => p.id === pid)!.commanders[0]!.key;
  await act({ type: "commander_tax", commander: key("p1"), delta: 2 });
  await act({ type: "commander_tax", commander: key("p1"), delta: 2 });
  await act({ type: "commander_tax", commander: key("p2"), delta: 2 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(4);
  await page.mouse.move(2, 400);
  await page.waitForTimeout(3500);
  const tag = `${n}p-${w}x${h}`;
  await page.screenshot({ path: `${OUT}/${PREFIX}-tax-${tag}.png` });
  // one more cast while watching: a coin drops onto the stack
  await act({ type: "commander_tax", commander: key("p1"), delta: 2 });
  await page.waitForTimeout(80);
  const at = (await page.evaluate((k) => window.__fyodor3d!.taxAt(k), key("p1")))!;
  await page.screenshot({ path: `${OUT}/${PREFIX}-tax-dropping-${tag}.png`, clip: { x: Math.max(0, at.x - 160), y: Math.max(0, at.y - 160), width: 320, height: 240 } });
  await page.waitForTimeout(1200);
  // hovered: the tooltip names the tax and the casts
  await page.mouse.move(at.x, at.y);
  await page.waitForTimeout(600);
  const title = await page.locator(".table3d-canvas").getAttribute("title");
  console.log("TAX TITLE", JSON.stringify(title));
  expect(title).toContain("Commander tax: +6 (cast 3 times from the command zone)");
  await page.screenshot({ path: `${OUT}/${PREFIX}-tax-closeup-${tag}.png`, clip: { x: Math.max(0, at.x - 200), y: Math.max(0, at.y - 220), width: 420, height: 300 } });
  await page.mouse.move(2, 400);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${PREFIX}-piles-closeup-${tag}.png`, clip: { x: w * 0.6, y: h * 0.45, width: w * 0.4, height: h * 0.45 } });
  await page.screenshot({ path: `${OUT}/${PREFIX}-far-row-${tag}.png`, clip: { x: 0, y: 46, width: w, height: h * 0.32 } });
  // the 2D table's tax coin (the same language): my command zone, and the whole table
  if (process.env.SHOT_2D) {
    await page.evaluate(() => localStorage.setItem("fyodor.renderer", "2d"));
    await page.reload();
    const coin = page.locator(".player-area.mine").getByTestId(`tax-${key("p1")}`);
    await expect(coin).toBeVisible({ timeout: 60_000 });
    if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
    await page.waitForTimeout(800);
    const b = (await page.locator(".player-area.mine .command-zone").boundingBox())!;
    await page.screenshot({ path: `${OUT}/${PREFIX}-2d-command-${tag}.png`, clip: { x: b.x - 20, y: b.y - 20, width: b.width + 40, height: b.height + 40 } });
    await page.screenshot({ path: `${OUT}/${PREFIX}-2d-table-${tag}.png` });
  }
  await context.close();
});
