import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, saveDecks } from "./helpers";

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
      await page.locator(".pg-toggle").click(); // the host's own decks to the seats: no lobby
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
    const decks = await saveDecks(page, [ALICE_DECK]);
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
