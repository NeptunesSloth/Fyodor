import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, hostTable } from "./helpers";

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
  await expect(page.getByTestId("menu-lan")).toBeVisible();
  await page.waitForTimeout(1500); // the plane showcase, fonts
  await page.goto("/#/settings");
  await expect(page.getByTestId("plane-ravnica")).toBeVisible();
  await page.getByTestId("plane-ravnica").click();
  await hostTable(page, { mulligan: "none" }); // a LAN night: the host's seat and one open for the pod
  // the 3D chunk and the WebGL scene: slower on a CI runner without a GPU (software rendering)
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  expect(outside).toEqual([]);
});
