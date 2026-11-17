import { expect, test, type Page } from "@playwright/test";

/**
 * -- Teach Fyodor -- review frames: building the "Dive N" example from pieces (docs/TEACH_FYODOR.md) and ▶ Try it at the table,
 * where the taught ability runs through the engine (mill, then the optional return as a choice). Skipped unless SHOT_DIR is set;
 * point E2E_PORT at a server with the real card database (Dive is invented: a stand-in creature plays as a card with Dive 2).
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(240_000);

async function prefs(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free" } }] }));
  });
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

test("build Dive N from pieces, then try it at the table", async ({ page }) => {
  await prefs(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/teach");
  await expect(page.getByTestId("teach-page")).toBeVisible();
  await expect(page.getByRole("button", { name: "Enters", exact: true })).toBeVisible();

  // the keyword: Dive, with a number
  await page.getByTestId("teach-name").fill("Dive");
  await page.getByTestId("teach-param").check();
  await page.getByPlaceholder("What the card says in brackets").fill("When this creature enters, mill N cards, then you may return a creature card with mana value N or less milled this way to your hand.");

  // click-to-add: the When hat, Mill cards (its number → N), You may … holding Keep one of the milled cards (its number → N)
  await page.getByRole("button", { name: "Enters", exact: true }).click();
  await page.getByRole("button", { name: "Mill cards", exact: true }).click();
  await page.getByRole("button", { name: /^n: 2\. Change$/ }).click();
  await page.getByRole("button", { name: "N", exact: true }).first().click();
  await page.getByRole("button", { name: "You may …", exact: true }).click();
  await page.getByRole("button", { name: "Keep one of the milled cards", exact: true }).click();
  // the chips inside: card kind stays "a creature card"; the number → N (drag the N value chip onto it)
  const nChip = page.locator(".t-palette .t-pill.t-n");
  await nChip.scrollIntoViewIfNeeded();
  const target = page.locator(".t-kids .t-chip").last();
  const a = await nChip.boundingBox();
  const b = await target.boundingBox();
  expect(a && b).toBeTruthy();
  await page.mouse.move(a!.x + a!.width / 2, a!.y + a!.height / 2);
  await page.mouse.down();
  await page.mouse.move(a!.x + 40, a!.y + 40, { steps: 6 });
  await page.mouse.move(b!.x + b!.width / 2, b!.y + b!.height / 2, { steps: 16 });
  await page.waitForTimeout(250);
  await shot(page, "teach-01-drag-n-onto-chip");
  await page.mouse.up();

  await expect(page.getByTestId("teach-sentence")).toHaveText(/^When this creature enters, mill N cards\. You may put a creature card with mana value N or less/);
  await expect(page.getByTestId("teach-verdict")).toHaveText(/Fyodor understands/, { timeout: 20_000 });
  await page.locator(".t-top").scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await shot(page, "teach-02-dive-built");

  // save it, then Try it
  await page.getByTestId("teach-save").click();
  await expect(page.locator(".t-rows li")).toHaveCount(1);
  await page.locator(".t-library").scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, "teach-03-taught");
  await page.getByTestId("teach-try").click();
  await page.waitForURL(/#\/game\//, { timeout: 30_000 });
  const id = page.url().split("#/game/")[1]!.split("?")[0]!;
  await page.waitForTimeout(3500);
  await shot(page, "teach-04-try-it-table");

  // cast the stand-in: the taught ability triggers, mills two, and asks whether to keep a creature card
  const token = await page.evaluate((gid) => localStorage.getItem(`fyodor.seat.${gid}`), id);
  const headers: Record<string, string> = token ? { "x-seat-token": token } : {};
  const view = (await (await page.request.get(`/api/games/${id}/view`, { headers })).json()) as { zones: Record<string, string[]>; cards: Record<string, { name?: string }> };
  const hand = view.zones["p1:hand"]!;
  expect(hand).toHaveLength(1);
  for (let i = 0; i < 3; i++) { // (into the main phase, should the table not be there yet)
    const t = (await (await page.request.get(`/api/games/${id}/view`, { headers })).json()) as { turn: { phase: string } };
    if (t.turn.phase.startsWith("main")) break;
    await page.request.post(`/api/games/${id}/actions`, { headers, data: { action: { type: "pass_priority" } } });
  }
  const cast = await page.request.post(`/api/games/${id}/actions`, { headers, data: { action: { type: "cast_spell", card_id: hand[0] } } });
  expect(cast.ok(), await cast.text()).toBeTruthy();
  // the table asks how to pay (tap the Forests): Pay, then the spell and its enters trigger resolve until Dive asks what to keep
  await page.locator(".pay-thumb").first().click({ timeout: 15_000 });
  await page.waitForTimeout(500);
  await page.locator(".pay-thumb").first().click();
  await page.waitForTimeout(500);
  const pay = page.getByRole("button", { name: "Pay", exact: true });
  if (await pay.isVisible().catch(() => false)) await pay.click(); // (two Forests cover {1}{G}: the table pays as soon as they do)
  for (let i = 0; i < 8; i++) {
    await page.waitForTimeout(700);
    const v = (await (await page.request.get(`/api/games/${id}/view`, { headers })).json()) as { stack: string[]; rules?: { decision?: unknown } | null };
    if (!v.stack.length || v.rules?.decision) break;
    const r = await page.request.post(`/api/games/${id}/actions`, { headers, data: { action: { type: "pass_priority" } } });
    if (!r.ok()) break;
  }
  await page.waitForTimeout(2500);
  await shot(page, "teach-05-try-it-dive-resolves");
});
