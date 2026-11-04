import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for the rooms around the 3D table (one per plane): a 1v1 game at 1920×1080 from the seat, the farthest
 * zoom and a low orbit, 2× close-ups of the table's props, and the renderer's counts at each graphics setting. Skipped
 * unless SHOT_DIR is set; SHOT_PREFIX names the set ("before", "after"); SHOT_PLANES picks the planes (comma separated);
 * SHOT_REAL=1 uses decks with cached art in a real card database. Nothing is asserted beyond "it rendered".
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "shot";
const REAL = !!process.env.SHOT_REAL;
const ONLY = process.env.SHOT_ONLY ?? "";
const PLANES = (process.env.SHOT_PLANES ?? "dominaria,ravnica,innistrad,kamigawa").split(",").filter(Boolean);
const QUALITY = process.env.SHOT_QUALITY ?? "high";
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

type View = { seat_order: string[]; zones: Record<string, string[]> };

async function setup(page: Page, planeId: string, graphics: string, players: string[], perSeat: number, origin = "") {
  await page.addInitScript(([pl, gx]) => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, plane: pl, graphics: gx } }] }));
  }, [planeId, graphics] as const);
  const texts = REAL ? [GOBLINS, COUNTERS] : [ALICE_DECK, BOB_DECK];
  const ids: string[] = [];
  for (const text of texts) {
    const r = await page.request.post(`${origin}/api/decks`, { data: { text, name: text.split("\n")[1]!.replace(/^1x /, "").replace(/ \(.*/, "") } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post(`${origin}/api/games`, {
    data: {
      name: "World", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: players.map((name, i) => ({ name, deck_id: ids[i % ids.length]! })),
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    await page.request.post(`${origin}/api/games/${gameId}/actions`, { data: { action } });
  };
  const view = async (v = "p1") => (await (await page.request.get(`${origin}/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  const seats = (await view()).seat_order;
  for (const pid of seats) await act({ type: "draw", player: pid, count: perSeat + 9 });
  const at = (i: number) => ({ x: 30 + (i % 9) * 105, y: 40 + Math.floor(i / 9) * 150 });
  for (const pid of seats) {
    const hand = (await view(pid)).zones[`${pid}:hand`]!;
    for (const [i, cid] of hand.slice(0, perSeat).entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, ...at(i) });
    await act({ type: "move", card_ids: [hand[perSeat]], to: { zone: "graveyard", player: pid } });
    await act({ type: "move", card_ids: [hand[perSeat + 1]], to: { zone: "exile", player: pid } });
  }
  return gameId;
}

async function open(page: Page, gameId: string, minCards: number, origin = "") {
  await page.goto(`${origin}/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 60_000 }).toBeGreaterThanOrEqual(minCards);
  await page.mouse.move(2, 400); // off the table: no hover, no preview
  await page.waitForTimeout(4000); // art loads, the camera settles
}

async function stats(page: Page, label: string) {
  await page.waitForTimeout(2200); // a fresh one-second sample
  const s = await page.evaluate(() => window.__fyodor3d!.stats());
  console.log(`STATS ${label} ${JSON.stringify(s)}`);
}

for (const planeId of PLANES) {
  test(`room: ${planeId}`, async ({ page }) => {
    test.skip(!!ONLY && ONLY !== "rooms", "SHOT_ONLY");
    test.setTimeout(480_000);
    await page.setViewportSize({ width: 1920, height: 1080 });
    const gameId = await setup(page, planeId, QUALITY, ["Alice", "Bob"], 6);
    await open(page, gameId, 12);
    await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-seat.png` });
    await stats(page, `${planeId} seat ${QUALITY}`);
    const box = (await page.getByTestId("table-3d").boundingBox())!;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height * 0.45;
    // a low orbit: right-drag up (pitch down toward the felt) and a little around
    await page.mouse.move(cx, cy);
    await page.mouse.down({ button: "right" });
    for (let i = 1; i <= 10; i++) await page.mouse.move(cx + i * 12, cy - i * 6);
    await page.mouse.up({ button: "right" });
    await page.keyboard.press("Escape");
    await page.mouse.move(2, 400);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-orbit.png` });
    // the farthest zoom: wheel out over empty wood until it stops
    await page.keyboard.press("Home");
    await page.waitForTimeout(1500);
    await page.mouse.move(cx, box.y + 20);
    for (let i = 0; i < 6; i++) await page.mouse.wheel(0, 600);
    await page.mouse.move(2, 400);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-zoomed-out.png` });
    await stats(page, `${planeId} zoomed-out ${QUALITY}`);
  });
}

/** Quick look while building: one game, each plane in turn (SHOT_VIEWS: seat, out, orbit). */
test("iterate", async ({ page }) => {
  test.skip(ONLY !== "iterate", "SHOT_ONLY");
  test.setTimeout(4_000_000);
  const views = (process.env.SHOT_VIEWS ?? "seat,out").split(",");
  await page.setViewportSize({ width: 1920, height: 1080 });
  const gameId = await setup(page, PLANES[0]!, QUALITY, ["Alice", "Bob"], 6);
  for (const planeId of PLANES) {
    await page.goto("about:blank"); // (a new page load: the same game's URL alone only changes the hash)
    await page.addInitScript(([pl, gx]) => localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, plane: pl, graphics: gx } }] })), [planeId, QUALITY] as const);
    await open(page, gameId, 12);
    const errors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    const box = (await page.getByTestId("table-3d").boundingBox())!;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height * 0.45;
    if (views.includes("seat")) {
      await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-seat.png` });
      await stats(page, `${planeId} seat ${QUALITY}`);
    }
    if (views.includes("orbit")) {
      await page.mouse.move(cx, cy);
      await page.mouse.down({ button: "right" });
      for (let i = 1; i <= 10; i++) await page.mouse.move(cx + i * 12, cy - i * 6);
      await page.mouse.up({ button: "right" });
      await page.keyboard.press("Escape");
      await page.mouse.move(2, 400);
      await page.waitForTimeout(3000);
      await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-orbit.png` });
      await page.keyboard.press("Home");
      await page.waitForTimeout(1500);
    }
    if (views.includes("out")) {
      await page.mouse.move(cx, box.y + 20);
      for (let i = 0; i < 6; i++) await page.mouse.wheel(0, 600);
      await page.mouse.move(2, 400);
      await page.waitForTimeout(3000);
      await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-zoomed-out.png` });
      await stats(page, `${planeId} zoomed-out ${QUALITY}`);
    }
    if (errors.length) console.log(`ERRORS ${planeId}`, errors.slice(0, 5).join(" | "));
  }
});

test("props up close, 2x", async ({ browser }) => {
  test.skip(!!ONLY && ONLY !== "props", "SHOT_ONLY");
  test.setTimeout(480_000);
  for (const planeId of PLANES) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
    const page = await context.newPage();
    const gameId = await setup(page, planeId, QUALITY, ["Alice", "Bob"], 6);
    await open(page, gameId, 12);
    // the table's prop spots: the two ends of the aisle past the far mat's edge (framing.ts propSpots), found as
    // battlefield points of the far seat (virtual units, off its mat)
    for (const [vx, tag] of [[1098, "left"], [-182, "right"]] as const) {
      const p = (await page.evaluate((x) => window.__fyodor3d!.battlefieldAt("p2", x, 636), vx))!;
      await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-prop-${tag}-2x.png`, clip: { x: Math.max(0, p.x - 130), y: Math.max(46, p.y - 165), width: 260, height: 200 } });
    }
    await context.close();
  }
});

for (const q of ["low", "medium", "high"]) {
  test(`perf at ${q}: the 4-player board of the perf check and a 1v1`, async ({ page }) => {
    test.skip(!!ONLY && ONLY !== "perf", "SHOT_ONLY");
    test.setTimeout(480_000);
    const planeId = PLANES[0]!;
    const gameId = await setup(page, planeId, q, ["Alice", "Bob", "Casey", "Jordan"], 10);
    await open(page, gameId, 40);
    await stats(page, `perf 4p ${planeId} ${q}`);
    await stats(page, `perf 4p ${planeId} ${q} (again)`);
    await page.screenshot({ path: `${OUT}/${PREFIX}-${planeId}-4p-${q}.png` });
  });
}

/** Wall-clock time per frame (the software renderer's whole frame, not just the script's part), the perf check's board. */
for (const q of ["low", "medium", "high"]) {
  test(`frame time at ${q}: the 4-player board of the perf check`, async ({ page }) => {
    test.skip(!!ONLY && ONLY !== "frames", "SHOT_ONLY");
    test.setTimeout(600_000);
    const gameId = await setup(page, PLANES[0]!, q, ["Alice", "Bob", "Casey", "Jordan"], 10);
    await open(page, gameId, 40);
    const samples: number[] = [];
    for (let k = 0; k < 3; k++) {
      samples.push(await page.evaluate(async () => {
        const f = window.__fyodor3d!;
        await f.nextFrame!();
        const t0 = performance.now();
        for (let i = 0; i < 8; i++) await f.nextFrame!();
        return (performance.now() - t0) / 8;
      }));
    }
    const s = await page.evaluate(() => window.__fyodor3d!.stats());
    console.log(`FRAMES ${q} ${JSON.stringify({ msPerFrame: samples.map((v) => Math.round(v)), calls: s.calls, triangles: s.triangles, cards: s.cards })}`);
  });
}


/**
 * Frame time against the build before the rooms, interleaved (load on a shared machine drifts): SHOT_BASE is that
 * build's server. Each measurement is a fresh page on the perf check's board.
 */
test("frame time, before and after, interleaved", async ({ browser }) => {
  test.skip(ONLY !== "ab", "SHOT_ONLY");
  test.setTimeout(3_000_000);
  const base = process.env.SHOT_BASE ?? "http://127.0.0.1:8815";
  const measure = async (origin: string, q: string) => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    const gameId = await setup(page, PLANES[0]!, q, ["Alice", "Bob", "Casey", "Jordan"], 10, origin);
    await open(page, gameId, 40, origin);
    const ms: number[] = [];
    for (let k = 0; k < 3; k++) {
      ms.push(await page.evaluate(async () => {
        const f = window.__fyodor3d!;
        await f.nextFrame!();
        const t0 = performance.now();
        for (let i = 0; i < 6; i++) await f.nextFrame!();
        return Math.round((performance.now() - t0) / 6);
      }));
    }
    const s = await page.evaluate(() => window.__fyodor3d!.stats());
    await context.close();
    return { ms, calls: s.calls };
  };
  for (const q of (process.env.SHOT_QS ?? "medium,high,low").split(",")) {
    for (let round = 0; round < 2; round++) {
      const order = round % 2 ? [["after", ""], ["before", base]] : [["before", base], ["after", ""]];
      for (const [tag, origin] of order) console.log(`AB ${q} ${tag} ${JSON.stringify(await measure(origin!, q))}`);
    }
  }
});
