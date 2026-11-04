import { expect, test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for the 3D table's framing, camera, seats and zones (1v1 at three window sizes, four players at
 * 1080p, a low orbit and the farthest zoom). Skipped unless SHOT_DIR is set; SHOT_PREFIX names the set ("before",
 * "after"); SHOT_REAL=1 uses decks whose printings have cached art in a real card database (the fixture database has
 * no art, so the default decks are the fixture's). Nothing is asserted beyond "it rendered" and the plaque checks.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "shot";
const REAL = !!process.env.SHOT_REAL;
const ONLY = process.env.SHOT_ONLY ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

const GOBLINS = `Commander
1x Krenko, Mob Boss (ddn) 15
Deck
1x Goblin Guide (2xm) 127
1x Goblin King (10e) 207
1x Legion Warboss (tdc) 220
1x Beetleback Chief (tdc) 205
1x Goblin Chieftain (jmp) 324
1x Siege-Gang Commander (tdc) 232
1x Mogg Fanatic (ema) 138
1x Goblin Rabblemaster (j25) 558
1x Sol Ring (cmm) 410
1x Lightning Bolt (fdc) 163
1x Impact Tremors (moc) 285
1x Goblin Bombardment (mh2) 279
1x Skullclamp (tdc) 103
1x Goblin Matron (dmr) 123
1x Goblin Warchief (j22) 548
14x Mountain (fra) 287
`;

const COUNTERS = `Commander
1x Atraxa, Praetors' Voice (c16) 28
Deck
1x Doubling Season (fdn) 216
1x Hardened Scales (lcc) 243
1x Winding Constrictor (aer) 140
1x Kalonian Hydra (blc) 226
1x Evolution Sage (ecc) 105
1x Birds of Paradise (fdc) 191
1x Swords to Plowshares (fdc) 53
1x Counterspell (dsc) 114
1x Rhystic Study (j22) 114
1x Sol Ring (fdc) 286
1x Arcane Signet (eoc) 53
1x Chromatic Lantern (tmc) 58
1x Master Biomancer (clu) 200
1x Corpsejack Menace (cm2) 152
1x Llanowar Elves (fdc) 213
4x Plains (fra) 281
4x Island (fra) 284
4x Forest (fra) 290
3x Swamp (fra) 286
`;

type View = { seat_order: string[]; zones: Record<string, string[]>; cards: Record<string, { zone: string; name?: string }> };

async function setup(page: Page, players: string[], perSeat: number, piles = true) {
  await page.addInitScript(() => {
    if (!localStorage.getItem("fyodor.renderer")) localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  const texts = REAL ? [GOBLINS, COUNTERS] : [ALICE_DECK, BOB_DECK];
  const ids: string[] = [];
  for (const text of texts) {
    const r = await page.request.post("/api/decks", { data: { text, name: text.split("\n")[1]!.replace(/^1x /, "").replace(/ \(.*/, "") } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: {
      name: "Shots", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: players.map((name, i) => ({ name, deck_id: ids[i % ids.length]! })),
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    if (!r.ok()) console.log("action refused", JSON.stringify(action).slice(0, 120), (await r.text()).slice(0, 200));
  };
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  const seats = (await view()).seat_order;
  for (const pid of seats) await act({ type: "draw", player: pid, count: perSeat + 9 });
  const at = (i: number) => ({ x: 30 + (i % 9) * 105, y: 40 + Math.floor(i / 9) * 150 });
  for (const pid of seats) {
    const hand = (await view(pid)).zones[`${pid}:hand`]!;
    for (const [i, cid] of hand.slice(0, perSeat).entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, ...at(i) });
    if (!piles) continue;
    await act({ type: "move", card_ids: [hand[perSeat]], to: { zone: "graveyard", player: pid } });
    await act({ type: "move", card_ids: [hand[perSeat + 1]], to: { zone: "exile", player: pid } });
  }
  await act({ type: "tap", card_ids: [(await view("p1")).zones["p1:battlefield"]![0]], tapped: true });
  return { gameId, act, view, seats };
}

async function open(page: Page, gameId: string, minCards: number) {
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(minCards);
  await page.mouse.move(2, 400); // off the table: no hover, no preview
  await page.waitForTimeout(3500); // art loads, the camera settles
}

async function shoot(page: Page, name: string) {
  await page.screenshot({ path: `${OUT}/${PREFIX}-${name}.png` });
  // how much of the screen the mats take (measured on the felt, across each mat's middle) and the chrome around them
  const m = await page.evaluate(() => {
    const f = window.__fyodor3d!;
    const box = (sel: string) => { const r = document.querySelector(sel)?.getBoundingClientRect(); return r ? [r.left, r.top, r.right, r.bottom].map(Math.round) : null; };
    const cv = document.querySelector(".table3d-canvas")!.getBoundingClientRect();
    const seats = [...document.querySelectorAll(".t3d-seat")].map((n) => n.getAttribute("data-player-id")!);
    // the felt's left and right edges across its middle (virtual: a card's top-left; the mat is 1000 × 600)
    const span = (p: string) => { const a = f.battlefieldAt(p, -42, 241), b = f.battlefieldAt(p, 958, 241); return a && b ? Math.abs(b.x - a.x) : 0; };
    return { framing: f.framing?.(), canvas: [cv.left, cv.top, cv.width, cv.height].map(Math.round), spans: seats.map((p) => [p, Math.round(span(p)), +(span(p) / cv.width).toFixed(3)]),
      dial: box(".turn-dial-wrap"), strip: box(".t3d-cams"), pill: box(".stack-pill") };
  });
  console.log(`MEASURE ${name} ${JSON.stringify(m)}`);
}

for (const [w, h] of [[1280, 640], [1920, 1080], [748, 851]] as const) {
  test(`1v1 at ${w}x${h}`, async ({ page }) => {
    test.skip(!!ONLY && !`1v1-${w}x${h}`.includes(ONLY), "SHOT_ONLY");
    test.setTimeout(240_000);
    await page.setViewportSize({ width: w, height: h });
    const { gameId } = await setup(page, ["Alice", "Bob"], 6);
    await open(page, gameId, 12);
    await shoot(page, `1v1-${w}x${h}`);
  });
}

test("4 players at 1920x1080", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "4p", "SHOT_ONLY");
  test.setTimeout(300_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { gameId } = await setup(page, ["Alice", "Bob", "Casey", "Jordan"], 5);
  await open(page, gameId, 20);
  await shoot(page, "4p-1920x1080");
});

test("1v1 camera: a low orbit and the farthest zoom, 1920x1080", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "camera", "SHOT_ONLY");
  test.setTimeout(480_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { gameId } = await setup(page, ["Alice", "Bob"], 6);
  await open(page, gameId, 12);
  const box = (await page.getByTestId("table-3d").boundingBox())!;
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height * 0.45;
  // the farthest zoom: wheel out over empty wood until it stops
  await page.mouse.move(cx, box.y + 20);
  for (let i = 0; i < 6; i++) await page.mouse.wheel(0, 600);
  await page.waitForTimeout(2500);
  await shoot(page, "1v1-zoomed-out");
  // back to the seat, then orbit low: right-drag up (pitch down toward the felt) and a little around
  await page.keyboard.press("Home");
  await page.waitForTimeout(2000);
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: "right" });
  for (let i = 1; i <= 10; i++) await page.mouse.move(cx + i * 12, cy - i * 6);
  await page.mouse.up({ button: "right" });
  await page.keyboard.press("Escape"); // a menu, if right-drag isn't an orbit here
  await page.waitForTimeout(2500);
  await shoot(page, "1v1-low-orbit");
});

test("hearts (each half hovered) and empty zones up close, 2x", async ({ browser }) => {
  test.skip(!!ONLY && ONLY !== "hearts", "SHOT_ONLY");
  test.setTimeout(400_000);
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const { gameId } = await setup(page, ["Alice", "Bob"], 4, false); // no graveyards or exile yet: their slots' labels show
  await open(page, gameId, 8);
  const mine = (await page.evaluate(() => window.__fyodor3d!.heartAt("p1")))!;
  for (const [side, tag] of [[-1, "minus"], [1, "plus"]] as const) {
    const half = (await page.evaluate((s) => window.__fyodor3d!.heartAt("p1", s), side))!;
    await page.mouse.move(half.x, half.y - 6);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${OUT}/${PREFIX}-heart-3d-${tag}-2x.png`, clip: { x: mine.x - 230, y: mine.y - 90, width: 360, height: 120 } });
  }
  await page.mouse.move(2, 400);
  await page.waitForTimeout(1500);
  // the far row (labels upright for me, piles mirrored to my right) and my own empty zones
  const far = (await page.evaluate(() => window.__fyodor3d!.heartAt("p2")))!;
  await page.screenshot({ path: `${OUT}/${PREFIX}-far-row-2x.png`, clip: { x: Math.max(0, far.x - 560), y: 46, width: 1100, height: 280 } });
  const vp = page.viewportSize()!;
  await page.screenshot({ path: `${OUT}/${PREFIX}-empty-zones-2x.png`, clip: { x: vp.width * 0.55, y: 46, width: vp.width * 0.45 - 4, height: vp.height * 0.62 } });
  // the 2D table's heart, each half hovered
  await page.evaluate(() => localStorage.setItem("fyodor.renderer", "2d"));
  await page.reload();
  await expect(page.getByTestId("heart-p1")).toBeVisible({ timeout: 60_000 });
  const box = (await page.getByTestId("heart-p1").boundingBox())!;
  for (const [fx, tag] of [[0.25, "minus"], [0.75, "plus"]] as const) {
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * 0.4);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/${PREFIX}-heart-2d-${tag}-2x.png`, clip: { x: box.x - 20, y: box.y - 14, width: box.width + 180, height: box.height + 28 } });
  }
  await context.close();
});

test("camera evidence, 1920x1080: a pan (middle-drag and arrows), and the farthest zoom with its frame-to-frame difference", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "evidence", "SHOT_ONLY");
  test.setTimeout(480_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { gameId } = await setup(page, ["Alice", "Bob"], 6);
  await open(page, gameId, 12);
  const box = (await page.getByTestId("table-3d").boundingBox())!;
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height * 0.45;
  // middle-drag: grab the table and slide it right and down, then two arrow steps left
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: "middle" });
  for (let i = 1; i <= 8; i++) await page.mouse.move(cx + i * 30, cy + i * 12);
  await page.mouse.up({ button: "middle" });
  await page.keyboard.press("ArrowUp");
  await page.waitForTimeout(3000);
  await shoot(page, "1v1-panned");
  // the farthest zoom, the room held still: frames 200 ms apart, compared pixel for pixel
  await page.keyboard.press("Home");
  await page.mouse.move(cx, box.y + 20);
  for (let i = 0; i < 6; i++) await page.mouse.wheel(0, 600);
  await page.evaluate(() => window.__fyodor3d!.still!(true));
  await expect.poll(async () => (await page.evaluate(() => window.__fyodor3d!.frameDiff!(100))).changed, { timeout: 120_000, intervals: [300] }).toBe(0);
  const diffs: { changed: number; total: number }[] = [];
  for (let i = 0; i < 5; i++) diffs.push(await page.evaluate(() => window.__fyodor3d!.frameDiff!(200)));
  const zoom = (await page.evaluate(() => window.__fyodor3d!.framing!())).adjust.zoom;
  writeFileSync(`${OUT}/${PREFIX}-flicker.json`, JSON.stringify({ zoom, frames200msApart: diffs }, null, 1));
  console.log("FLICKER", JSON.stringify({ zoom, diffs }));
  await shoot(page, "1v1-zoomed-out-still");
});
