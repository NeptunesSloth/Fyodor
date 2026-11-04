import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Frames for review of the linked Scryfall assets: the Magic card back on every face-down surface (launcher, deck pages,
 * both tables) and the mana symbols (the deck list, the deck editor, a card's text). Skipped unless SHOT_DIR is set;
 * SHOT_PREFIX names the set (before / after / fallback), SHOT_ONLY picks one frame. Point it at a server with real card
 * art for the review pictures (E2E_PORT, outside CI it reuses a running server); it also runs on the fixture server.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "shot";
const ONLY = process.env.SHOT_ONLY ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

const only = (name: string) => test.skip(!!ONLY && !ONLY.split(",").includes(name), "SHOT_ONLY");

async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
}

type DeckRow = { id: string; name: string; commanders: string[] };

/** Two decks to play: the server's own (real art) when it has any, else the fixture decks. */
async function decks(page: Page): Promise<string[]> {
  let rows = (await (await page.request.get("/api/decks")).json()) as DeckRow[];
  if (rows.length < 2) {
    for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
    rows = (await (await page.request.get("/api/decks")).json()) as DeckRow[];
  }
  const pick = (name: string) => rows.find((d) => d.commanders.some((c) => c.startsWith(name)));
  return [pick("Atraxa") ?? rows[0]!, pick("Krenko") ?? rows[1]!].map((d) => d.id);
}

async function game(page: Page) {
  const [a, b] = await decks(page);
  const res = await page.request.post("/api/games", {
    data: { name: "Friday Night", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: a }, { name: "Bob", deck_id: b }] },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const hand = async (pid: string) => ((await (await page.request.get(`/api/games/${gameId}/view?viewer=${pid}`)).json()) as { zones: Record<string, string[]> }).zones[`${pid}:hand`]!;
  for (const pid of ["p1", "p2"]) {
    await act({ type: "draw", player: pid, count: 11 });
    const ids = await hand(pid);
    for (const [i, cid] of ids.slice(0, 3).entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 40 + i * 110, y: 40 });
    // a face-down permanent (a morph) and a face-down exiled card: both show the card back
    await act({ type: "move", card_ids: [ids[3]], to: { zone: "battlefield", player: pid }, x: 400, y: 40, face_down: true, face_down_kind: "morph" });
    await act({ type: "move", card_ids: [ids[4]], to: { zone: "exile", player: pid }, face_down: true });
  }
  return gameId;
}

async function pastIntro(page: Page) {
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect(intro).toHaveCount(0);
}

/** Until the art has loaded and nothing is still moving (the arranged boards glide cards into place). */
async function settle(page: Page) {
  await page.waitForFunction(() => [...document.images].every((i) => i.complete)
    && document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getTiming().iterations === Infinity), null, { timeout: 15_000 })
    .catch(() => undefined);
  await page.waitForTimeout(300);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${PREFIX}-${name}.png` });

for (const [w, h] of [[1280, 720], [1920, 1080]] as const) {
  test(`decks page, ${w}x${h}`, async ({ page }) => {
    only("decks");
    await prefs(page, "2d");
    await decks(page);
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/#/decks");
    await expect(page.locator(".pips").first()).toBeVisible();
    await settle(page);
    await shot(page, `decks-${w}`);
  });
}

test("decks page pips at 2x", async ({ browser }) => {
  only("decks");
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await prefs(page, "2d");
  await decks(page);
  await page.goto("/#/decks");
  await expect(page.locator(".pips").first()).toBeVisible();
  await page.waitForTimeout(1200);
  const row = page.locator(".dk-facts").first();
  await row.screenshot({ path: `${OUT}/${PREFIX}-decks-pips-2x.png` });
  await ctx.close();
});

test("deck editor: the preview's card back and the costs", async ({ page }) => {
  only("editor");
  await prefs(page, "2d");
  const [a] = await decks(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/decks/${a}`);
  await expect(page.locator(".de-preview")).toBeVisible();
  await settle(page);
  await shot(page, "editor-1920");
  await page.setViewportSize({ width: 1280, height: 720 });
  await settle(page);
  await shot(page, "editor-1280");
  // every row's cost ends on the same column, the commander's included
  const ends = await page.evaluate(() => [...document.querySelectorAll(".de-row")].slice(0, 6).map((r) => {
    const c = r.querySelector(".de-cost")!.getBoundingClientRect();
    return Math.round(c.right - r.getBoundingClientRect().left);
  }));
  console.log("cost column ends (commander row first):", ends.join(" "));
});

test("a card's text: rules text and a cost with symbols", async ({ browser }) => {
  only("text");
  test.setTimeout(180_000);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await prefs(page, "2d");
  await page.goto("/#/cards");
  for (const [q, name] of [["Sol Ring", "sol-ring"], ["Kitchen Finks", "finks"], ["Atraxa, Praetors' Voice", "atraxa"]] as const) {
    await page.locator("input.search").fill(q);
    await page.waitForTimeout(700);
    await page.locator(".grid-card").first().click();
    await expect(page.locator(".card-details")).toBeVisible();
    await page.waitForTimeout(900);
    await shot(page, `text-${name}`);
    await page.locator(".details-text").first().screenshot({ path: `${OUT}/${PREFIX}-text-${name}-crop.png` });
    await page.keyboard.press("Escape");
  }
  await ctx.close();
});

test("launcher: the 3D showcase and the 2D scene", async ({ page }) => {
  only("home");
  test.setTimeout(120_000);
  await prefs(page, "3d");
  await game(page); // the table the launcher offers to continue
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/");
  await expect(page.locator(".showcase-canvas")).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(4000);
  await settle(page);
  await shot(page, "home-3d");
  await page.evaluate(() => localStorage.setItem("fyodor.renderer", "2d"));
  await page.addInitScript(() => localStorage.setItem("fyodor.renderer", "2d"));
  await page.reload();
  await expect(page.locator(".home-scene")).toBeVisible();
  await settle(page);
  await shot(page, "home-2d");
});

for (const [w, h] of [[1280, 720], [1920, 1080]] as const) {
  test(`2D table: library piles, a face-down permanent and exile, ${w}x${h}`, async ({ page }) => {
    only("table2d");
    test.setTimeout(120_000);
    await prefs(page, "2d");
    const gameId = await game(page);
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`/#/game/${gameId}`);
    await expect(page.getByTestId("seat-p2")).toBeVisible();
    await pastIntro(page);
    await page.waitForTimeout(1000);
    await settle(page);
    await shot(page, `table2d-${w}`);
  });

  test(`3D table: library piles, the other hand's backs and a face-down permanent, ${w}x${h}`, async ({ page }) => {
    only("table3d");
    test.setTimeout(120_000);
    page.on("pageerror", (e) => console.log("pageerror:", e.message));
    page.on("console", (m) => m.type() === "error" && console.log("console:", m.text().slice(0, 300)));
    await prefs(page, "3d");
    const gameId = await game(page);
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`/#/game/${gameId}`);
    await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 40_000 });
    await pastIntro(page);
    await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(8);
    await page.waitForTimeout(3000);
    await shot(page, `table3d-${w}`);
  });
}
