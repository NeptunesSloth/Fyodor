import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Frames for review of the front door: the launcher, the Play page's New game form, and the LAN lobby with its Table
 * settings (the Format choice: Commander or Sandbox), plus a Sandbox table's top bar. Skipped unless SHOT_DIR is set;
 * SHOT_PREFIX names the set ("before" / "after"). Best against a server with the real card database and art.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "after";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

const SIZES = [[1280, 720], [1920, 1080]] as const;

async function prefs(page: Page, renderer: "2d" | "3d" = "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
}

const shot = (page: Page, name: string, w: number, h: number) => page.screenshot({ path: `${OUT}/${PREFIX}-${name}-${w}x${h}.png` });

/** Commander art and fonts in: every image on the page loaded (or failed), then a moment for the paint. */
async function settled(page: Page, ms = 800) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete), undefined, { timeout: 15_000 }).catch(() => undefined);
  await page.waitForTimeout(ms);
}

/** Open a LAN lobby from the Play page (the old page had a mode choice first; the new one opens on the LAN night). */
async function hostLobby(page: Page, format?: "sandbox"): Promise<string> {
  await page.goto("/#/play?mode=lan");
  const lan = page.getByTestId("table-mode-lan");
  if (await lan.count()) await lan.check();
  await page.getByTestId("host-name").fill("Alice");
  if (format) await page.getByTestId("table-format").getByTestId(`format-${format}`).check();
  await page.getByTestId("create-game").click();
  await expect(page.getByTestId("lobby")).toBeVisible();
  return page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
}

test.beforeAll(async ({ request }) => {
  const have = (await (await request.get("/api/decks")).json()) as unknown[];
  if (have.length < 2) for (const text of [ALICE_DECK, BOB_DECK]) await request.post("/api/decks", { data: { text } });
});

for (const [w, h] of SIZES) {
  test(`home ${w}x${h}`, async ({ page }) => {
    test.setTimeout(120_000);
    await prefs(page);
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/#/");
    await expect(page.getByTestId("menu-new").or(page.getByTestId("menu-lan")).first()).toBeVisible();
    await page.locator(".home-art .card-face > img").first().waitFor({ timeout: 15_000 }).catch(() => undefined); // the decks' art
    await settled(page, 2500); // the plane showcase, fonts, commander art
    await shot(page, "home", w, h);
  });

  test(`play ${w}x${h}`, async ({ page }) => {
    await prefs(page);
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/#/play");
    await expect(page.getByTestId("create-game")).toBeVisible();
    await settled(page, 1200);
    await shot(page, "play", w, h);
    const sandbox = page.getByTestId("format-sandbox");
    if (await sandbox.count()) {
      await sandbox.check();
      await settled(page, 300);
      await shot(page, "play-sandbox", w, h);
      await page.getByTestId("decks-dealt").check(); // the host deals decks to the seats: no lobby
      await settled(page, 600);
      await shot(page, "play-nolobby", w, h);
    }
  });

  test(`lobby ${w}x${h}`, async ({ page }) => {
    await prefs(page);
    await page.setViewportSize({ width: w, height: h });
    await hostLobby(page);
    await settled(page);
    await shot(page, "lobby", w, h);
    await page.getByRole("button", { name: "Table settings" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.waitForTimeout(400);
    await shot(page, "lobby-settings", w, h);
  });

  test(`sandbox lobby and table ${w}x${h}`, async ({ page }) => {
    test.skip(PREFIX === "before", "no Sandbox before");
    test.setTimeout(240_000); // the 3D table on a software renderer
    await prefs(page, "3d");
    await page.setViewportSize({ width: w, height: h });
    const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
    const gameId = await hostLobby(page, "sandbox");
    await page.request.post(`/api/games/${gameId}/lobby/deck`, {
      data: { deck_id: decks[0]!.id },
      headers: { "X-Seat-Token": (await page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId))! },
    });
    await page.reload();
    await expect(page.getByTestId("lobby")).toBeVisible();
    await settled(page);
    await shot(page, "lobby-sandbox", w, h);
    await page.getByRole("button", { name: "Table settings" }).click();
    await settled(page, 400);
    await shot(page, "lobby-settings-sandbox", w, h);
    await page.keyboard.press("Escape");
    await page.getByTestId("ready").click();
    await page.getByTestId("start-game").click();
    await expect(page.locator(".game-screen")).toBeVisible();
    const intro = page.getByTestId("game-intro");
    if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
    const keep = page.getByTestId("mull-keep");
    if (await keep.isVisible({ timeout: 4000 }).catch(() => false)) await keep.click();
    await settled(page, 3000);
    await shot(page, "table-sandbox", w, h);
    await page.getByTestId("table-format").click();
    await settled(page, 400);
    await shot(page, "table-sandbox-automation", w, h);
  });
}

test("2x crops: the format placards, the lobby's Format choice, the table's Sandbox tag", async ({ browser }) => {
  test.skip(PREFIX === "before", "no Sandbox before");
  test.setTimeout(240_000);
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await prefs(page, "2d"); // (the top bar is the same over either table; the 2D one is light at 2x)
  await page.goto("/#/");
  await expect(page.getByTestId("menu-lan")).toBeVisible();
  await settled(page, 600);
  await page.locator(".home-menu").screenshot({ path: `${OUT}/${PREFIX}-crop2x-home-menu.png` }); // the LAN glyph, the plaques
  await page.goto("/#/play");
  await settled(page, 600);
  await page.locator(".pg-formats").screenshot({ path: `${OUT}/${PREFIX}-crop2x-formats.png` });
  await page.locator(".pg-chairs").screenshot({ path: `${OUT}/${PREFIX}-crop2x-chairs.png` }); // the table glyph by each open seat
  await page.getByTestId("format-sandbox").focus(); // the keyboard focus ring on a placard
  await page.keyboard.press("ArrowLeft");
  await settled(page, 200);
  await page.locator(".pg-formats").screenshot({ path: `${OUT}/${PREFIX}-crop2x-formats-focus.png` });
  await page.locator(".pg-rail").screenshot({ path: `${OUT}/${PREFIX}-crop2x-rail.png` });
  const gameId = await hostLobby(page, "sandbox");
  await page.getByRole("button", { name: "Table settings" }).click();
  await settled(page, 400);
  await page.getByTestId("lobby-format-choice").screenshot({ path: `${OUT}/${PREFIX}-crop2x-lobby-format.png` });
  await page.keyboard.press("Escape");
  const token = await page.evaluate((id) => localStorage.getItem(`fyodor.seat.${id}`), gameId);
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  await page.request.post(`/api/games/${gameId}/lobby/deck`, { data: { deck_id: decks[0]!.id }, headers: { "X-Seat-Token": token! } });
  await page.request.post(`/api/games/${gameId}/lobby/ready`, { data: { ready: true }, headers: { "X-Seat-Token": token! } });
  await page.request.post(`/api/games/${gameId}/lobby/start`, { data: {}, headers: { "X-Seat-Token": token! } });
  await page.reload();
  await expect(page.getByTestId("table-format")).toBeVisible({ timeout: 30_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  const keep = page.getByTestId("mull-keep");
  if (await keep.isVisible({ timeout: 5000 }).catch(() => false)) await keep.click();
  await expect(page.getByTestId("mulligan")).toHaveCount(0);
  await settled(page, 1500);
  await page.locator(".game-top").screenshot({ path: `${OUT}/${PREFIX}-crop2x-topbar.png` });
  await page.getByTestId("table-format").hover();
  await settled(page, 300);
  await page.getByTestId("table-format").screenshot({ path: `${OUT}/${PREFIX}-crop2x-sandbox-tag-hover.png` });
  await context.close();
});

for (const [w, h] of SIZES) {
  test(`hover and focus states ${w}x${h}`, async ({ page }) => {
    test.skip(PREFIX === "before", "states of the new front door");
    test.setTimeout(120_000);
    await prefs(page, "3d");
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/#/");
    await page.locator(".home-art .card-face > img").first().waitFor({ timeout: 15_000 }).catch(() => undefined);
    await settled(page, 2000);
    await page.getByTestId("menu-resume").hover(); // a secondary item lit by the pointer
    await settled(page, 300);
    await shot(page, "home-hover", w, h);
    await page.mouse.move(w - 5, h / 2);
    await page.keyboard.press("Shift"); // keyboard modality, so focus shows its ring
    await page.getByTestId("menu-lan").focus();
    await settled(page, 300);
    await shot(page, "home-focus", w, h);

    await page.goto("/#/play");
    await expect(page.getByTestId("create-game")).toBeVisible();
    await settled(page, 800);
    await page.locator(".pg-format", { hasText: "Sandbox" }).hover();
    await settled(page, 300);
    await shot(page, "play-hover", w, h);
    await page.mouse.move(w - 5, h - 5);
    await page.keyboard.press("Shift");
    await page.getByTestId("decks-dealt").focus();
    await settled(page, 300);
    await shot(page, "play-focus", w, h);
    await page.getByTestId("create-game").focus();
    await settled(page, 200);
    await page.locator(".pg-rail").screenshot({ path: `${OUT}/${PREFIX}-play-focus-start-${w}x${h}.png` });
  });
}
