import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/** Game night works without Internet: nothing the app loads may come from another host. */
test("offline: the launcher, 3D table and a game load nothing from outside the host", async ({ page, baseURL }) => {
  const host = new URL(baseURL!).host;
  const outside: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol.startsWith("http") && u.host !== host) outside.push(r.url());
    if (u.protocol.startsWith("ws") && u.host !== host) outside.push(r.url());
  });
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
  });
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  await page.goto("/#/");
  await expect(page.getByTestId("menu-new")).toBeVisible();
  await page.waitForTimeout(1500); // the plane showcase, fonts
  await page.goto("/#/settings");
  await expect(page.getByTestId("plane-ravnica")).toBeVisible();
  await page.getByTestId("plane-ravnica").click();
  await page.goto("/#/play");
  await page.getByTestId("mulligan-rule").selectOption("none");
  await page.getByTestId("create-game").click();
  await expect(page.getByTestId("table-3d")).toBeVisible();
  await page.waitForTimeout(1500);
  expect(outside).toEqual([]);
});
