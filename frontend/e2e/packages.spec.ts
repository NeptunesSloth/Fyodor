import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { ALICE_DECK, BOB_DECK } from "./helpers";

test("a saved game exports as a portable package and imports back; diagnostics download without private data", async ({ page }) => {
  await page.goto("/#/play");
  const a = (await (await page.request.post("/api/decks", { data: { text: ALICE_DECK } })).json()).id as string;
  const b = (await (await page.request.post("/api/decks", { data: { text: BOB_DECK } })).json()).id as string;
  const created = await (await page.request.post("/api/games", {
    data: { name: "Package night", mode: "local", players: [{ name: "Alice", deck_id: a }, { name: "Bob", deck_id: b }] },
  })).json();
  const gid = created.game.id as string;
  await page.request.post(`/api/games/${gid}/actions`, { data: { action: { type: "draw", count: 4 }, viewer: "p1" } });
  await page.request.post(`/api/games/${gid}/save`, { data: { name: "Package night save" } });
  await page.reload();

  const row = page.locator(".list-row", { hasText: "Package night save" });
  const [download] = await Promise.all([page.waitForEvent("download"), row.getByTitle(/portable package/).click()]);
  expect(download.suggestedFilename()).toBe("Package night save.fyodor.zip");
  const zip = readFileSync((await download.path())!);

  await page.getByTestId("package-import").setInputFiles({ name: "game.fyodor.zip", mimeType: "application/zip", buffer: zip });
  await expect(page.locator(".list-row", { hasText: "Package night save (imported)" })).toBeVisible();
  await page.getByTestId("package-import").setInputFiles({ name: "evil.zip", mimeType: "application/zip", buffer: Buffer.from("MZ not a zip") });
  await expect(page.locator(".toast", { hasText: "not a zip" })).toBeVisible();

  await page.goto("/#/settings");
  const [diag] = await Promise.all([page.waitForEvent("download"), page.getByTestId("diag-download").click()]);
  const body = JSON.parse(readFileSync((await diag.path())!, "utf8"));
  expect(body.includes_private_information).toBe(false);
  expect(body.rooms.some((r: { id: string }) => r.id === gid)).toBe(true);
  expect(JSON.stringify(body)).not.toContain("\"hand\"");
});
